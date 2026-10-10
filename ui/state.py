"""
Η «μνήμη» της εφαρμογής (st.session_state): τι κρατά ανάμεσα στα reruns, με ποια αρχική
τιμή και τι μηδενίζει ο «Καθαρισμός όλων» — όλα από τον ίδιο πίνακα STATE — καθώς και η
αναίρεση (undo) αλλαγών στα datasets.
"""
from datetime import datetime

import streamlit as st

from modules import query_builder as qb

UNDO_STACK_LIMIT = 20   # μέγιστες αναιρέσιμες αλλαγές ανά dataset (όριο μνήμης — παλιότερες αποβάλλονται)

# όνομα -> (αρχική τιμή, μηδενίζεται από τον «Καθαρισμό όλων»;)
STATE = {
    "datasets": (dict, True),                 # {όνομα: DataFrame}
    "active": (lambda: None, True),           # όνομα του ενεργού dataset
    "pending_uploads": (dict, True),          # {αρχείο: bytes} — csv/xls/xlsx που περιμένουν «Φόρτωση»
    "excel_loaded_sheets": (dict, True),      # {αρχείο: set(sheets που έχουν ήδη φορτωθεί)}
    "zip_loaded_members": (dict, True),       # {zip: set(αρχεία του που έχουν ήδη φορτωθεί)}
    "codebooks": (dict, True),                # {.dat: {"pdf", "catalogue": κατάλογος μεταβλητών, "picked": {όνομα: τύπος}}}
    "fixed_width_specs": (dict, True),        # {.dat: πίνακας θέσεων (Όνομα, Από, Έως, Τύπος) — η αρχή του editor}
    "fixed_width_filters": (dict, True),      # {.dat: κανόνες γραμμών (Στήλη, Τελεστής, Τιμή) — η αρχή του editor}
    "done_uploads": (set, True),              # αρχεία που ολοκληρώθηκαν, να μην ξαναμπούν στη λίστα
    "sql_result": (lambda: None, True),       # τελευταίο αποτέλεσμα του Advanced (SQL)
    "batch": (lambda: None, True),            # συνδυασμός σε εξέλιξη: {"names": σειρά, "ready": {αρχείο: DataFrame}}
    "combine_order": (list, True),            # αρχεία τικαρισμένα για συνδυασμό, με τη σειρά των κλικ
    "uploader_reset_counter": (lambda: 0, False),  # αυξάνεται (όχι μηδενισμός) — βλ. reset_state
    "cleaning": (dict, True),                 # {dataset: ρυθμίσεις Pipeline (outlier rules, duplicates)}
    "group_analysis": (dict, True),           # {dataset: query_builder.new_container_state()} — tables του Analysis/Workshop
    "undo_stack": (dict, True),               # {dataset: [{"df", "description", "timestamp"}, ...]} παλαιότερο -> νεότερο
    "workshop_result": (lambda: None, True),  # τελευταία «Εκτέλεση» του Workshop: έξοδος, show(), σφάλμα, save_table
    # Αντίγραφο του κώδικα του Workshop: η Streamlit ξεχνά την τιμή ενός πλαισίου που δεν
    # σχεδιάστηκε σε ένα run (π.χ. μετά τον «Καθαρισμό όλων», όταν δεν υπάρχουν δεδομένα).
    "workshop_code_saved": (lambda: None, False),
    # Γλώσσα εμφάνισης (διακόπτης ΕΛ/EN πάνω δεξιά): ανοίγει στα ελληνικά, μένει όλη τη συνεδρία.
    "language": (lambda: "el", False),
}


def init_state() -> None:
    """Δημιουργεί όσα δεν υπάρχουν ακόμα, με την αρχική τους τιμή."""
    for key, (default, _) in STATE.items():
        if key not in st.session_state:
            st.session_state[key] = default()


def reset_state() -> None:
    """«Καθαρισμός όλων»: μηδενίζει ό,τι σημειώνεται στο STATE. Ο μετρητής του πλαισίου
    ανεβάσματος αυξάνεται, ώστε να αδειάσει και το ίδιο το widget (νέο key)."""
    for key, (default, cleared) in STATE.items():
        if cleared:
            st.session_state[key] = default()
    st.session_state.uploader_reset_counter += 1


def push_undo(dataset_name: str, description: str) -> None:
    """Αποθηκεύει την ΤΡΕΧΟΥΣΑ κατάσταση του dataset στο undo stack, ΠΡΙΝ από μια
    αλλαγή — κάθε καταγεγραμμένη αλλαγή γίνεται ένα βήμα αναίρεσης. Καλείται πάντα
    ΠΡΙΝ την ίδια τη μετάλλαξη του st.session_state.datasets[dataset_name]."""
    if dataset_name not in st.session_state.datasets:
        return
    stack = st.session_state.undo_stack.setdefault(dataset_name, [])
    stack.append({
        "df": st.session_state.datasets[dataset_name].copy(),
        "description": description,
        "timestamp": datetime.now(),
    })
    if len(stack) > UNDO_STACK_LIMIT:
        stack.pop(0)


def undo_last_change(dataset_name: str) -> bool:
    """Αναιρεί την τελευταία καταγεγραμμένη αλλαγή στο dataset. True αν έγινε."""
    stack = st.session_state.undo_stack.get(dataset_name) or []
    if not stack:
        return False
    entry = stack.pop()
    restored_df = entry["df"]
    st.session_state.datasets[dataset_name] = restored_df

    # Αν η αλλαγή που αναιρείται είχε προσθέσει στήλη που ήταν καταχωρημένη σε κάποιο
    # table, η αναίρεση την αφαιρεί από το dataset αλλά όχι αυτόματα από το table· χωρίς
    # αυτόν τον καθαρισμό το table θα έσκαγε (KeyError/ValueError) στην επόμενη εκτέλεσή
    # του, αφού θα αναφερόταν σε στήλη που δεν υπάρχει πια.
    valid_cols = set(restored_df.columns)
    for t in st.session_state.group_analysis.get(dataset_name, {}).get("tables", []):
        t["selected_cols"] = [c for c in t["selected_cols"] if c in valid_cols]
    return True


def cleaning_state(dataset_name: str) -> dict:
    """
    Επιστρέφει (δημιουργώντας αν χρειάζεται) τις ΡΥΘΜΙΣΕΙΣ του Pipeline για το
    δοσμένο dataset (ενεργοί outlier rules, επιλογές duplicates) — ΟΧΙ τα ίδια τα
    δεδομένα. Single source of truth: τα δεδομένα ζουν αποκλειστικά στο
    st.session_state.datasets[dataset_name], το οποίο διαβάζουν/γράφουν και οι
    4 καρτέλες άμεσα, χωρίς κανένα tab (ούτε το Pipeline) να κρατά δικό του
    τοπικό αντίγραφο.
    """
    if dataset_name not in st.session_state.cleaning:
        st.session_state.cleaning[dataset_name] = {
            "outlier_rules": [],
            "dup_key_col": None,
        }
    return st.session_state.cleaning[dataset_name]


def group_analysis_state(dataset_name: str) -> dict:
    """Επιστρέφει (δημιουργώντας αν χρειάζεται) το container της Ενότητας 5
    (Ομαδοποίηση & Ανάλυση) για το dataset: έως qb.MAX_TABLES tables + builder."""
    if dataset_name not in st.session_state.group_analysis:
        st.session_state.group_analysis[dataset_name] = qb.new_container_state()
    return st.session_state.group_analysis[dataset_name]
