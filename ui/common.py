"""
Κομμάτια οθόνης που χρησιμοποιούν πολλά tabs: κουμπί αναίρεσης, επεξεργάσιμοι πίνακες
με «Επιλογή» και τα κουμπιά Επαναφορά/Διαγραφή, λήψεις CSV/Excel, Update/Where/Set,
επιλογή στηλών και φίλτρα WHERE.
"""
import io

import pandas as pd
import streamlit as st

from modules import cleaning_pipeline as cp
from modules import query_builder as qb
from ui import state


def undo_button(dataset_name: str, widget_key: str):
    """Κουμπί 'Αναίρεση τελευταίας αλλαγής' — σε κάθε καρτέλα εκτός από το View."""
    stack = st.session_state.undo_stack.get(dataset_name) or []
    label = "Αναίρεση τελευταίας αλλαγής"
    if stack:
        label += f" — {stack[-1]['description']}"
    if st.button(label, key=widget_key, disabled=not stack):
        if state.undo_last_change(dataset_name):
            st.toast("Η αλλαγή αναιρέθηκε.")
            st.rerun()


def filterable_editor(display_df: pd.DataFrame, widget_prefix: str, show_filter: bool = True):
    """
    Κοινό UI pattern για τους 3 quarantine πίνακες: προαιρετικό dropdown φίλτρου
    στήλης (δείχνει μόνο γραμμές όπου η επιλεγμένη στήλη είναι NULL — αφορά κυρίως
    το Missing Values), inline-editable πίνακας (st.data_editor) με στήλη επιλογής
    "Επιλογή" ανά γραμμή, και checkbox "Επιλογή όλων".
    Επιστρέφει (edited_df, selected_idx) ή (None, None) αν δεν υπάρχουν γραμμές.
    """
    if display_df.empty:
        st.info("Δεν βρέθηκαν γραμμές.")
        return None, None

    view = display_df
    if show_filter:
        data_cols = [c for c in display_df.columns if c != "Αιτία"]
        filter_col = st.selectbox(
            "Φίλτρο: δείξε μόνο γραμμές με NULL σε",
            ["(όλες)"] + data_cols, key=f"{widget_prefix}_filter",
        )
        if filter_col != "(όλες)":
            view = display_df[display_df[filter_col].isna()]
        if view.empty:
            st.info("Καμία γραμμή με τα τρέχοντα φίλτρα.")
            return None, None

    select_all = st.checkbox("Επιλογή όλων", key=f"{widget_prefix}_select_all")
    edit_df = view.copy()
    edit_df.insert(0, "Επιλογή", False)
    edited = st.data_editor(edit_df, width="stretch", height=280, key=f"{widget_prefix}_editor")
    selected_idx = list(edited.index) if select_all else edited.index[edited["Επιλογή"] == True].tolist()
    return edited, selected_idx


def restore_delete_actions(
    dataset_name: str, edited, selected_idx, widget_prefix: str,
    restore_label: str = "Επαναφορά στο dataset", delete_label: str = "Διαγραφή",
):
    """Τα δύο κοινά κουμπιά ενεργειών: restore (commit τυχόν inline edits +
    αφαίρεση από το quarantine table) και delete (αφαίρεση εντελώς από το
    dataset). Γράφουν ΑΠΕΥΘΕΙΑΣ στο st.session_state.datasets (single source
    of truth) και κάνουν rerun, ώστε όλες οι καρτέλες (και τα άλλα quarantine
    tables) να ενημερωθούν αυτόματα. Τα labels είναι παραμετροποιήσιμα ώστε το
    ίδιο pattern να καλύπτει και την Ενότητα Β (Ενεργό σύνολο δεδομένων)."""
    if edited is None:
        return
    ac1, ac2 = st.columns(2)
    with ac1:
        if st.button(restore_label, key=f"{widget_prefix}_restore"):
            if not selected_idx:
                st.warning("Δεν έχεις επιλέξει γραμμές.")
            else:
                state.push_undo(dataset_name, f"{restore_label} ({len(selected_idx)} γραμμές, {widget_prefix})")
                st.session_state.datasets[dataset_name] = cp.apply_row_edits(
                    st.session_state.datasets[dataset_name], edited, selected_idx,
                )
                st.success(f"Ενημερώθηκαν {len(selected_idx)} γραμμές.")
                st.rerun()
    with ac2:
        if st.button(delete_label, key=f"{widget_prefix}_delete"):
            if not selected_idx:
                st.warning("Δεν έχεις επιλέξει γραμμές.")
            else:
                state.push_undo(dataset_name, f"{delete_label} ({len(selected_idx)} γραμμές, {widget_prefix})")
                st.session_state.datasets[dataset_name] = st.session_state.datasets[dataset_name].drop(index=selected_idx)
                st.success(f"Διαγράφηκαν {len(selected_idx)} γραμμές.")
                st.rerun()


def export_buttons(export_df: pd.DataFrame, base_filename: str, widget_prefix: str):
    """Κοινό ζευγάρι κουμπιών λήψης (CSV + Excel) για οποιοδήποτε DataFrame αποτέλεσμα
    (Pipeline > Export, Analysis > Ομαδοποίηση & Ανάλυση). Το Excel γράφεται σε μνήμη
    (io.BytesIO) με openpyxl — καμία προσωρινή εγγραφή σε δίσκο."""
    ec1, ec2 = st.columns(2)
    with ec1:
        st.download_button(
            "Λήψη ως CSV",
            export_df.to_csv(index=False).encode("utf-8-sig"),
            file_name=f"{base_filename}.csv",
            key=f"{widget_prefix}csv",
        )
    with ec2:
        excel_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
            export_df.to_excel(writer, index=False, sheet_name="Sheet1")
        st.download_button(
            "Λήψη ως Excel",
            excel_buffer.getvalue(),
            file_name=f"{base_filename}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"{widget_prefix}xlsx",
        )


def update_where_set(dataset_name: str, widget_prefix: str):
    """
    Κοινό εργαλείο "Update / Where / Set" (στο Pipeline και αυτούσιο στο Analysis >
    Ομαδοποίηση & Ανάλυση). Διαβάζει/γράφει ΠΑΝΤΑ απευθείας το
    st.session_state.datasets[dataset_name] (single source of truth).
    widget_prefix μοναδικό ανά σημείο εμφάνισης, ώστε τα
    keys να μη συγκρούονται μεταξύ Pipeline και Ομαδοποίησης & Ανάλυσης (και τα
    δύο render-άρονται σε κάθε script run, ανεξάρτητα από ποιο tab βλέπει ο χρήστης).
    """
    cdf = st.session_state.datasets[dataset_name]
    wc1, wc2, wc3 = st.columns([2, 3, 1])
    with wc1:
        where_col = st.selectbox("WHERE — Στήλη", cdf.columns.tolist(), key=f"{widget_prefix}where_col")
    with wc2:
        where_val = st.text_input("WHERE — Συνθήκη", key=f"{widget_prefix}where_val")
        st.caption(
            "(υποστηρίζει: =, !=, >, <, >=, <=, BETWEEN x AND y, καθώς και AND/OR "
            "για συνδυασμό δύο συνθηκών στην ίδια στήλη)"
        )
    with wc3:
        where_null = st.checkbox("Είναι NULL", key=f"{widget_prefix}where_null")

    sc1, sc2, sc3 = st.columns([2, 3, 1])
    with sc1:
        set_col = st.selectbox("SET — Στήλη", cdf.columns.tolist(), key=f"{widget_prefix}set_col")
    with sc2:
        set_val = st.text_input("SET — Τιμή / Πράξη", key=f"{widget_prefix}set_val")
        st.caption(
            "(μπορείς να γράψεις σταθερή τιμή, π.χ. Παλτά, ή πράξη πάνω στην τρέχουσα τιμή "
            "ή άλλες στήλες, π.χ. * 0.9, + 10, - [Έκπτωση])"
        )
    with sc3:
        set_null = st.checkbox("Είναι NULL", key=f"{widget_prefix}set_null")

    if st.button("Εφαρμογή", key=f"{widget_prefix}apply"):
        try:
            new_df, n_affected = cp.apply_update_set(
                cdf, where_col, where_null, where_val, set_col, set_null, set_val
            )
            state.push_undo(dataset_name, f"Update/Where/Set: SET {set_col} WHERE {where_col} ({n_affected} γραμμές)")
            st.session_state.datasets[dataset_name] = new_df
            st.success(f"Ενημερώθηκαν {n_affected} γραμμές.")
            st.rerun()
        except ValueError as e:
            st.toast(str(e))


def column_checkboxes(all_cols: list, kp: str) -> list:
    """Select All/Καμία + checkbox ανά στήλη (4 ανά γραμμή). Το Select All/None
    γράφει ΑΠΕΥΘΕΙΑΣ στο st.session_state πριν το render, γιατί το value= ενός
    checkbox σεβαστεί μόνο στην πρώτη-ποτέ instantiation του, όχι σε επόμενα reruns."""
    sa1, sa2 = st.columns(2)
    with sa1:
        if st.button("Επιλογή όλων", key=f"{kp}selectall"):
            for c in all_cols:
                st.session_state[f"{kp}colcb_{c}"] = True
    with sa2:
        if st.button("Καμία", key=f"{kp}selectnone"):
            for c in all_cols:
                st.session_state[f"{kp}colcb_{c}"] = False

    selected = []
    cols_per_row = 4
    for i in range(0, len(all_cols), cols_per_row):
        row_widgets = st.columns(cols_per_row)
        for j, col_name in enumerate(all_cols[i:i + cols_per_row]):
            with row_widgets[j]:
                checked = st.checkbox(col_name, value=True, key=f"{kp}colcb_{col_name}")
            if checked:
                selected.append(col_name)
    return selected


def where_filters(df: pd.DataFrame, cols: list, filters_in: list, kp: str) -> list:
    """Κοινό WHERE-φίλτρο builder: ίδιοι τελεστές ανά τύπο στήλης (=,!=,>,<,>=,<=,
    BETWEEN,IN,CONTAINS,BEFORE,AFTER), ίδιοι λογικοί σύνδεσμοι AND/OR, dropdown
    πραγματικών τιμών όπου έχει νόημα (=,!=,IN σε κατηγορικές). Χρησιμοποιείται
    αυτούσιο στο 'Προσθήκη Table'. Μεταλλάσσει το filters_in (add/remove) και
    επιστρέφει τη φρέσκια λίστα μετά το render των γραμμών."""
    fc_add, fc_rm = st.columns(2)
    with fc_add:
        if st.button("Προσθήκη φίλτρου", key=f"{kp}addf"):
            default_col = cols[0]
            filters_in.append({
                "col": default_col, "op": qb.get_column_operators(df, default_col)[0],
                "val": "", "val2": None, "combine": "AND",
            })
    with fc_rm:
        if filters_in and st.button("Αφαίρεση τελευταίου φίλτρου", key=f"{kp}rmf"):
            filters_in.pop()

    filters = []
    for i, prev in enumerate(filters_in):
        row = st.columns([1, 2, 1.4, 3])
        with row[0]:
            if i == 0:
                st.caption("—")
                combine = "AND"
            else:
                combine_options = ["AND", "OR"]
                default_combine = prev.get("combine") if prev.get("combine") in combine_options else "AND"
                combine = st.selectbox(
                    "​", combine_options, index=combine_options.index(default_combine),
                    key=f"{kp}f_combine_{i}", label_visibility="collapsed",
                )
        with row[1]:
            default_col = prev.get("col") if prev.get("col") in cols else cols[0]
            col = st.selectbox(
                "Στήλη", cols, index=cols.index(default_col),
                key=f"{kp}f_col_{i}", label_visibility="collapsed" if i > 0 else "visible",
            )
        ops = qb.get_column_operators(df, col)
        with row[2]:
            default_op = prev.get("op") if prev.get("op") in ops else ops[0]
            op = st.selectbox(
                "Τελεστής", ops, index=ops.index(default_op),
                key=f"{kp}f_op_{i}", label_visibility="collapsed" if i > 0 else "visible",
            )
        val, val2 = None, None
        is_categorical = not (pd.api.types.is_numeric_dtype(df[col].dtype) or pd.api.types.is_datetime64_any_dtype(df[col].dtype))
        unique_vals = qb.get_unique_values(df, col) if is_categorical else None
        with row[3]:
            if op == "BETWEEN":
                bc1, bc2 = st.columns(2)
                with bc1:
                    val = st.text_input(
                        "Από", value=str(prev.get("val") or ""), key=f"{kp}f_val_{i}",
                        label_visibility="collapsed" if i > 0 else "visible",
                    )
                with bc2:
                    val2 = st.text_input(
                        "Έως", value=str(prev.get("val2") or ""), key=f"{kp}f_val2_{i}",
                        label_visibility="collapsed" if i > 0 else "visible",
                    )
            elif op in ("=", "!=") and unique_vals:
                default_val = prev.get("val") if prev.get("val") in unique_vals else unique_vals[0]
                val = st.selectbox(
                    "Τιμή", unique_vals, index=unique_vals.index(default_val),
                    key=f"{kp}f_val_{i}", label_visibility="collapsed" if i > 0 else "visible",
                )
            elif op == "IN" and unique_vals:
                default_vals = [v for v in (prev.get("val") or []) if v in unique_vals]
                val = st.multiselect(
                    "Τιμές", unique_vals, default=default_vals,
                    key=f"{kp}f_val_{i}", label_visibility="collapsed" if i > 0 else "visible",
                )
            else:
                val = st.text_input(
                    "Τιμή" + (" (CONTAINS)" if op == "CONTAINS" else ""),
                    value=str(prev.get("val") or ""), key=f"{kp}f_val_{i}",
                    label_visibility="collapsed" if i > 0 else "visible",
                )
        filters.append({"col": col, "op": op, "val": val, "val2": val2, "combine": combine})
    return filters
