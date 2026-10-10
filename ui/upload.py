"""
Φόρτωση αρχείων: η ενότητα «1. Φόρτωση δεδομένων» του sidebar, οι «Ρυθμίσεις φόρτωσης»
με το κουμπί «Φόρτωση», και ο συνδυασμός αρχείων (Join, Set Operator, Chain,
Hub-and-Spoke). Οι κανόνες (όριο, σειρά, τι συνδυάζεται) ζουν στο modules/upload_plan.py.
"""
import pandas as pd
import streamlit as st

from modules import codebook as cbk
from modules import combiner as cb
from modules import data_loader as dl
from modules import fixed_width as fw
from modules import upload_plan as up
from ui import state


def sidebar_section():
    """Ενότητα «1. Φόρτωση δεδομένων» του sidebar. Επιστρέφει τα αρχεία του πλαισίου ανεβάσματος."""
    st.sidebar.header("1. Φόρτωση δεδομένων")
    uploaded = st.sidebar.file_uploader(
        "Αρχεία (.csv, .xls, .xlsx, .px, .pdf, .sql, .zip, .dat)",
        type=["csv", "xls", "xlsx", "px", "pdf", "sql", "zip", "dat"],
        accept_multiple_files=True,
        key=f"file_uploader_{st.session_state.uploader_reset_counter}",
    )
    st.sidebar.caption("Όριο: 10MB ανά αρχείο και συνολικά· .zip και .dat έως 200MB (από ένα zip: "
                       "CSV/Excel έως 10MB, .dat έως 200MB αποσυμπιεσμένο).")


    if st.sidebar.button("Καθαρισμός όλων (νέα ανάλυση)"):
        state.reset_state()
        st.rerun()
    return uploaded


def _already_tracked(fname: str) -> bool:
    if fname in st.session_state.done_uploads or fname in st.session_state.pending_uploads:
        return True
    if st.session_state.batch and fname in st.session_state.batch["names"]:
        return True
    return False


def _forget_pending(fname: str) -> None:
    """Βγάζει ένα αρχείο από τη λίστα «Ρυθμίσεις φόρτωσης» και από τη σειρά συνδυασμού."""
    st.session_state.pending_uploads.pop(fname, None)
    st.session_state.combine_order = [f for f in st.session_state.combine_order if f != fname]


def receive_files(uploaded) -> None:
    """Συγχρονίζει τη λίστα φόρτωσης με το πλαίσιο ανεβάσματος: τα νέα CSV/Excel/ZIP/DAT μπαίνουν
    στη λίστα, τα PX/PDF/SQL φορτώνονται αμέσως, όσα αφαιρέθηκαν από το πλαίσιο φεύγουν."""
    # Αρχείο που αφαιρέθηκε από το πλαίσιο ανεβάσματος φεύγει και από τη λίστα φόρτωσης· το
    # checkbox «Συνδυασμός» του μηδενίζεται εδώ, πριν σχεδιαστεί, όπως επιτρέπει η Streamlit.
    uploaded_names = {f.name for f in uploaded or []}
    for fname in [n for n in st.session_state.pending_uploads if n not in uploaded_names]:
        _forget_pending(fname)
        st.session_state.pop(f"combine_{fname}", None)

    if uploaded:
        # Το πλαίσιο ανεβάσματος δέχεται έως 200MB ανά αρχείο (για .zip/.dat)· το όριο κάθε
        # τύπου ελέγχεται εδώ, πριν διαβαστεί το αρχείο.
        new_files = []
        for file in uploaded:
            if _already_tracked(file.name):
                continue
            too_large = up.file_too_large(file.name, file.size)
            if too_large:
                st.sidebar.error(too_large)
            else:
                new_files.append(file)
        # CSV/Excel περιμένουν στις «Ρυθμίσεις φόρτωσης» το κουμπί «Φόρτωση»· τα px/pdf/sql
        # φορτώνονται αμέσως, ανεξάρτητα.
        for file in new_files:
            if up.is_combinable(file.name):
                st.session_state.pending_uploads[file.name] = file.read()
        new_other = [f for f in new_files if not up.is_combinable(f.name)]

        for file in new_other:
            ext = file.name.split(".")[-1].lower()
            try:
                if ext == "px":
                    st.session_state.datasets[file.name] = dl.load_px(file)
                    st.session_state.done_uploads.add(file.name)
                elif ext == "pdf":
                    tables = dl.load_pdf_tables(file)
                    for i, tdf in enumerate(tables):
                        st.session_state.datasets[f"{file.name} [πίνακας {i+1}]"] = tdf
                    st.session_state.done_uploads.add(file.name)
                elif ext == "sql":
                    sql_text = file.read().decode("utf-8", errors="ignore")
                    results = dl.run_sql_script(sql_text, st.session_state.datasets)
                    for name, rdf in results.items():
                        st.session_state.datasets[f"{file.name} [{name}]"] = rdf
                    st.session_state.done_uploads.add(file.name)
            except Exception as e:
                st.sidebar.error(f"Σφάλμα στο {file.name}: {e}")


def _upload_config_widget(widget_key: str, raw_df: pd.DataFrame):
    """Preview + ρυθμίσεις φόρτωσης (skip rows / skip columns / privacy symbols).
    Επιστρέφει το DataFrame όπως θα φορτωθεί με τις τρέχουσες ρυθμίσεις."""
    st.caption("Προεπισκόπηση πρώτων 15 γραμμών (ακατέργαστα, χωρίς επεξεργασία):")
    preview = raw_df.head(15).copy()
    preview.index = [f"γραμμή {i}" for i in preview.index]
    st.dataframe(preview, width="stretch", height=280)

    c1, c2, c3 = st.columns(3)
    with c1:
        skip_rows = st.number_input(
            "Παράλειψη γραμμών στην αρχή", min_value=0,
            max_value=max(0, len(raw_df) - 1), value=0, key=f"skip_{widget_key}",
        )
    with c2:
        skip_cols = st.number_input(
            "Παράλειψη στηλών στην αρχή", min_value=0,
            max_value=max(0, raw_df.shape[1] - 1), value=0, key=f"skipcols_{widget_key}",
        )
    with c3:
        ffill_header = st.checkbox(
            "Forward-fill συγχωνευμένων κελιών επικεφαλίδας",
            value=True, key=f"ffill_{widget_key}",
        )

    convert_privacy = st.checkbox(
        "Μετατροπή συμβόλων απορρήτου σε κενό (NaN)", value=True, key=f"priv_on_{widget_key}",
    )
    symbols_text = st.text_input(
        "Σύμβολα προς μετατροπή (χωρισμένα με κόμμα)",
        value=", ".join(dl.DEFAULT_PRIVACY_SYMBOLS), key=f"priv_syms_{widget_key}",
        disabled=not convert_privacy,
    )
    privacy_symbols = [s.strip() for s in symbols_text.split(",") if s.strip()] if convert_privacy else []

    final_preview = dl.build_dataframe_from_raw(raw_df, skip_rows, skip_cols, ffill_header, privacy_symbols)
    st.caption("Προεπισκόπηση τελικού αποτελέσματος:")
    st.dataframe(final_preview.head(10), width="stretch", height=220)
    return final_preview


def _finalize_batch(label: str, result_df: pd.DataFrame):
    """Μόνο το τελικό combined αποτέλεσμα μπαίνει στα datasets."""
    st.session_state.datasets[label] = result_df
    for nm in st.session_state.batch["names"]:
        st.session_state.done_uploads.add(nm)
    st.session_state.batch = None
    st.success(f"Το συνδυασμένο dataset αποθηκεύτηκε ως '{label}'.")
    st.rerun()


def _render_pair_combination(names, ready):
    n1, n2 = names
    df1, df2 = ready[n1], ready[n2]

    combo_type = st.radio("Τύπος συνδυασμού", ["Join", "Set Operator"], key="combine2_type", horizontal=True)

    if combo_type == "Join":
        technique = st.selectbox("Τεχνική Join", cb.JOIN_TECHNIQUES, key="combine2_join_technique")
        key1 = key2 = None
        if technique != "Cross":
            c1, c2 = st.columns(2)
            with c1:
                key1 = st.selectbox(f"Κλειδί από '{n1}'", df1.columns.tolist(), key="combine2_key1")
            with c2:
                key2 = st.selectbox(f"Κλειδί από '{n2}'", df2.columns.tolist(), key="combine2_key2")
        if st.button("Εφαρμογή Join", key="combine2_join_apply"):
            if technique != "Cross":
                ok, err = cb.validate_join_key_types(df1, key1, df2, key2)
                if not ok:
                    st.toast(err)
                    st.stop()
            result = cb.apply_join(df1, key1, df2, key2, technique, 1, 2)
            label = cb.build_combined_label(
                [cb.strip_extension(n1), cb.strip_extension(n2)], technique, is_structure=False
            )
            _finalize_batch(label, result)
    else:
        technique = st.selectbox("Set Operator", cb.SET_OPERATORS, key="combine2_setop_technique")
        if st.button("Εφαρμογή", key="combine2_setop_apply"):
            ok, err = cb.validate_set_operator_compatibility([df1, df2], [n1, n2])
            if not ok:
                st.toast(err)
                st.stop()
            result = cb.apply_set_operator([df1, df2], technique)
            label = cb.build_combined_label(
                [cb.strip_extension(n1), cb.strip_extension(n2)], technique, is_structure=False
            )
            _finalize_batch(label, result)


def _render_join_wizard(names, ready, base_names, structure):
    wiz = st.session_state.batch["wizard"]
    order = wiz["order"]
    n = len(order)
    step = wiz["step"]

    if step >= n:
        structure_label = "Chain" if structure == "chain" else "Hub-and-Spoke"
        label = cb.build_combined_label(base_names, structure_label, is_structure=True)
        _finalize_batch(label, wiz["current_df"])
        return

    current_df = wiz["current_df"]
    origin = wiz["origin"]
    next_name = order[step]
    next_df = ready[next_name]
    next_table_num = wiz["table_numbers"][step]

    st.markdown(f"**Βήμα {step}/{n - 1}: σύνδεση τρέχοντος αποτελέσματος με '{next_name}'**")
    st.caption(f"Τρέχουσες στήλες αποτελέσματος: {', '.join(current_df.columns)}")
    technique = st.selectbox("Τεχνική Join", cb.JOIN_TECHNIQUES, key=f"wizard_technique_{step}")

    if structure == "hubspoke":
        hub_num = wiz["table_numbers"][0]
        left_choices = [c for c in current_df.columns if origin[c] == hub_num]
        st.caption("Το κλειδί από την πλευρά του Hub περιορίζεται σε στήλες που προέρχονται από το Hub.")
    else:
        left_choices = current_df.columns.tolist()

    key_left = key_right = None
    if technique != "Cross":
        c1, c2 = st.columns(2)
        with c1:
            key_left = st.selectbox("Κλειδί από τρέχον αποτέλεσμα", left_choices, key=f"wizard_keyleft_{step}")
        with c2:
            key_right = st.selectbox(f"Κλειδί από '{next_name}'", next_df.columns.tolist(), key=f"wizard_keyright_{step}")

    btn_label = "Ολοκλήρωση συνδυασμού" if step == n - 1 else "Επόμενο βήμα"
    if st.button(btn_label, key=f"wizard_confirm_{step}"):
        if technique != "Cross":
            ok, err = cb.validate_join_key_types(current_df, key_left, next_df, key_right)
            if not ok:
                st.toast(err)
                st.stop()
        merged, new_origin = cb.apply_join_step(
            current_df, origin, next_df, next_table_num, key_left, key_right, technique
        )
        wiz["current_df"] = merged
        wiz["origin"] = new_origin
        wiz["step"] += 1
        st.rerun()


def _render_chain_join(names, ready, base_names):
    wiz = st.session_state.batch.get("wizard")
    if wiz is None:
        st.markdown("**Σειρά σύνδεσης** (η σειρά με την οποία τικάρισες τα αρχεία):")
        st.caption(" → ".join(f"{i}. {nm}" for i, nm in enumerate(names, start=1)))
        if st.button("Έναρξη Chain", key="chain_start"):
            st.session_state.batch["wizard"] = {
                "order": list(names),
                "table_numbers": list(range(1, len(names) + 1)),
                "step": 1,
                "current_df": ready[names[0]].copy(),
                "origin": {c: 1 for c in ready[names[0]].columns},
            }
            st.rerun()
        return
    _render_join_wizard(names, ready, base_names, "chain")


def _render_hub_spoke_join(names, ready, base_names):
    wiz = st.session_state.batch.get("wizard")
    if wiz is None:
        hub = st.selectbox("Ποιο αρχείο είναι το Hub;", names, key="hub_pick")
        if st.button("Έναρξη Hub-and-Spoke", key="hub_start"):
            spokes = [nm for nm in names if nm != hub]
            order = [hub] + spokes
            table_numbers = [names.index(nm) + 1 for nm in order]
            st.session_state.batch["wizard"] = {
                "order": order,
                "table_numbers": table_numbers,
                "step": 1,
                "current_df": ready[hub].copy(),
                "origin": {c: table_numbers[0] for c in ready[hub].columns},
            }
            st.rerun()
        return
    _render_join_wizard(names, ready, base_names, "hubspoke")


def _render_multi_combination(names, ready):
    dfs = [ready[nm] for nm in names]
    base_names = [cb.strip_extension(nm) for nm in names]
    scope = st.radio(
        "Τεχνική συνδυασμού", ["Set Operator (διαδοχικά σε όλα)", "Join"],
        key="combineN_scope", horizontal=True,
    )
    if scope.startswith("Set Operator"):
        technique = st.selectbox("Set Operator", cb.SET_OPERATORS, key="combineN_setop_technique")
        if st.button("Εφαρμογή", key="combineN_setop_apply"):
            ok, err = cb.validate_set_operator_compatibility(dfs, names)
            if not ok:
                st.toast(err)
                st.stop()
            result = cb.apply_set_operator(dfs, technique)
            label = cb.build_combined_label(base_names, technique, is_structure=False)
            _finalize_batch(label, result)
        return

    structure = st.radio("Δομή Join", ["Chain", "Hub-and-Spoke"], key="combineN_structure", horizontal=True)
    if structure == "Chain":
        _render_chain_join(names, ready, base_names)
    else:
        _render_hub_spoke_join(names, ready, base_names)


def _render_combination():
    batch = st.session_state.batch
    names = batch["names"]
    ready = batch["ready"]

    st.header("Συνδυασμός αρχείων")
    st.caption(
        f"Επέλεξες {len(names)} αρχεία για συνδυασμό, με αυτή τη σειρά: "
        + ", ".join(f"{i}. {nm}" for i, nm in enumerate(names, start=1)) + "."
    )
    with st.expander("Προεπισκόπηση φορτωμένων αρχείων", expanded=False):
        for nm in names:
            st.caption(f"**{nm}** — {ready[nm].shape[0]} γραμμές × {ready[nm].shape[1]} στήλες")
            st.dataframe(ready[nm].head(5), width="stretch")

    if len(names) == 2:
        _render_pair_combination(names, ready)
    else:
        _render_multi_combination(names, ready)


def _drop_from_list(fname: str, message: str) -> None:
    st.toast(message)
    st.session_state.done_uploads.add(fname)
    _forget_pending(fname)


def _prepare_file(fname: str, ext: str, raw_bytes: bytes, in_combination: bool, source: str = None,
                  codebooks: dict = None):
    """Ρυθμίσεις και προεπισκόπηση ενός CSV/Excel της λίστας. Επιστρέφει {"name": όνομα
    dataset ή None για συνδυασμό, "df", "sheet", "n_sheets", "size"}, ή None αν το αρχείο
    βγήκε από τη λίστα (σφάλμα ανάγνωσης ή Excel με όλα τα sheets ήδη φορτωμένα).
    source: το όνομα του αρχείου που διαβάζεται, αν διαφέρει από το fname της λίστας (αρχείο
    μέσα σε zip: "αρχείο.zip/μέσα.csv") — δίνει όνομα στο dataset και στα widgets.
    codebooks: PDF του ίδιου zip που μπορούν να δώσουν τις στήλες ενός .dat."""
    source = source or fname
    if ext == "dat":
        return _prepare_fixed_width(source, raw_bytes, codebooks)
    if ext == "csv":
        try:
            raw_df, sep, enc = dl.read_raw_csv(raw_bytes)
        except Exception as e:
            _drop_from_list(fname, f"Σφάλμα ανάγνωσης: {e}")
            return None
        sep_label = {",": ",", ";": ";", "\t": "TAB"}.get(sep, sep)
        st.caption(f"Ανιχνεύτηκε διαχωριστικό `{sep_label}` και encoding `{enc}`.")
        return {"name": source, "df": _upload_config_widget(source, raw_df), "sheet": None, "n_sheets": None,
                "size": len(raw_bytes)}

    try:
        sheet_names = dl.get_excel_sheet_names(raw_bytes)
    except Exception as e:
        _drop_from_list(fname, f"Σφάλμα ανάγνωσης: {e}")
        return None

    if in_combination:
        # Στον συνδυασμό κάθε Excel συμμετέχει με ΕΝΑ μόνο sheet.
        sheet = st.selectbox(
            "Διάλεξε sheet για τον συνδυασμό", sheet_names, key=f"batchsheet_{source}"
        )
        raw_df = dl.read_raw_excel(raw_bytes, sheet)
        return {"name": None, "df": _upload_config_widget(f"{source}::{sheet}", raw_df), "sheet": sheet,
                "n_sheets": len(sheet_names), "size": len(raw_bytes)}

    # Χωρίς συνδυασμό: ένα sheet ανά «Φόρτωση»· το αρχείο μένει στη λίστα
    # όσο υπάρχουν sheets που δεν έχουν φορτωθεί ακόμα.
    loaded = st.session_state.excel_loaded_sheets.setdefault(source, set())
    remaining = [s for s in sheet_names if s not in loaded]
    if not remaining:
        st.session_state.done_uploads.add(fname)
        _forget_pending(fname)
        return None
    sheet = st.selectbox("Φύλλο (sheet)", remaining, key=f"sheet_sel_{source}")
    raw_df = dl.read_raw_excel(raw_bytes, sheet)
    return {"name": f"{source} [{sheet}]", "df": _upload_config_widget(f"{source}::{sheet}", raw_df),
            "sheet": sheet, "n_sheets": len(sheet_names), "size": len(raw_bytes)}


def _not_ready(source: str, problem: str) -> dict:
    return {"name": source, "df": None, "problem": problem, "sheet": None, "n_sheets": None, "size": 0}


MANUAL_COLUMNS = "Χειροκίνητα (πίνακας θέσεων)"


def _manual_spec(source: str) -> pd.DataFrame:
    """Πίνακας θέσεων που γράφει ο χρήστης (Όνομα, Από, Έως, Τύπος)."""
    st.caption(
        "Για κάθε στήλη που θέλεις: όνομα και θέσεις «Από»–«Έως» όπως τις δίνει το codebook (ο πρώτος "
        "χαρακτήρας της γραμμής είναι η θέση 1). «Αυτόματο»: αριθμός αν όλες οι τιμές είναι αριθμοί — "
        "κωδικούς (π.χ. αναγνωριστικό ατόμου) κράτα τους ως «Κείμενο»."
    )
    base = st.session_state.fixed_width_specs.setdefault(source, fw.empty_spec())
    return st.data_editor(
        base, num_rows="dynamic", hide_index=True, width="stretch", key=f"fwf_spec_{source}",
        column_config={
            "Όνομα": st.column_config.TextColumn("Όνομα", required=True),
            "Από": st.column_config.NumberColumn("Από", min_value=1, step=1, format="%d", required=True),
            "Έως": st.column_config.NumberColumn("Έως", min_value=1, step=1, format="%d", required=True),
            "Τύπος": st.column_config.SelectboxColumn("Τύπος", options=list(fw.TYPES), default=fw.TYPE_AUTO,
                                                      required=True),
        },
    )


def _codebook_spec(source: str, pdf_name: str, read_pdf, line_length: int):
    """Μεταβλητές από τον κατάλογο του codebook, με αναζήτηση και τικ. Επιστρέφει πίνακα θέσεων
    (όπως ο χειροκίνητος) ή None αν το PDF δεν έχει κατάλογο. Το PDF διαβάζεται μία φορά."""
    book = st.session_state.codebooks.get(source)
    if book is None or book["pdf"] != pdf_name:
        with st.spinner(f"Ανάγνωση του {pdf_name}…"):
            try:
                catalogue = cbk.read_variable_list(read_pdf())
            except Exception as e:
                st.warning(f"Το {pdf_name} δεν διαβάστηκε ({e}) — γράψε τις στήλες χειροκίνητα.")
                return None
        book = {"pdf": pdf_name, "catalogue": catalogue, "picked": {}}
        st.session_state.codebooks[source] = book
    catalogue, picked = book["catalogue"], book["picked"]
    if catalogue.empty:
        st.warning(f"Στο {pdf_name} δεν βρέθηκε κατάλογος μεταβλητών με στήλες «Start End Name "
                   "Description» — γράψε τις στήλες χειροκίνητα.")
        return None

    problems = cbk.coverage_problems(catalogue, line_length)
    if problems:
        st.warning("Ο κατάλογος δεν ταιριάζει πλήρως με το αρχείο — έλεγξε ότι το codebook είναι αυτού "
                   "του αρχείου και τις θέσεις στην προεπισκόπηση:\n\n" + "\n\n".join(problems))
    else:
        st.success(f"{len(catalogue):,} μεταβλητές· καλύπτουν τις θέσεις 1–{line_length:,} χωρίς κενά "
                   "και επικαλύψεις.")

    query = st.text_input("Αναζήτηση (όνομα ή περιγραφή)", key=f"cb_search_{source}")
    shown = cbk.search(catalogue, query)
    view = shown.assign(
        Επιλογή=shown["Όνομα"].isin(picked),
        Τύπος=[picked.get(name, fw.TYPE_AUTO) for name in shown["Όνομα"]],
    )[["Επιλογή", "Όνομα", "Περιγραφή", "Από", "Έως", "Τύπος"]]
    st.caption(f"{len(shown):,} από {len(catalogue):,} μεταβλητές. Τίκαρε όσες θέλεις — οι επιλογές "
               "μένουν όταν αλλάζεις αναζήτηση. Κωδικούς (π.χ. αναγνωριστικό ατόμου) κράτα τους ως «Κείμενο».")
    edited = st.data_editor(
        view, hide_index=True, width="stretch", height=320, key=f"cb_table_{source}_{query}",
        disabled=["Όνομα", "Περιγραφή", "Από", "Έως"],
        column_config={
            "Επιλογή": st.column_config.CheckboxColumn("Επιλογή"),
            "Τύπος": st.column_config.SelectboxColumn("Τύπος", options=list(fw.TYPES), required=True),
        },
    )
    for name, ticked, kind in zip(edited["Όνομα"], edited["Επιλογή"], edited["Τύπος"]):
        if ticked:
            picked[name] = kind
        else:
            picked.pop(name, None)

    if picked:
        st.caption(f"Επιλεγμένες ({len(picked)}): "
                   + ", ".join(name if kind == fw.TYPE_AUTO else f"{name} ({kind})" for name, kind in picked.items()))
    positions = catalogue.drop_duplicates("Όνομα").set_index("Όνομα")
    return pd.DataFrame({
        "Όνομα": list(picked),
        "Από": pd.array([positions.at[name, "Από"] for name in picked], dtype="Int64"),
        "Έως": pd.array([positions.at[name, "Έως"] for name in picked], dtype="Int64"),
        "Τύπος": list(picked.values()),
    })


def _prepare_fixed_width(source: str, raw_bytes: bytes, codebooks: dict = None) -> dict:
    """Ένα .dat σταθερού πλάτους: οι στήλες έρχονται από το codebook (PDF στο ίδιο zip, με
    αναζήτηση και τικ) ή από πίνακα θέσεων που γράφει ο χρήστης· φορτώνονται μόνο αυτές.
    codebooks: {όνομα PDF: συνάρτηση που επιστρέφει τα bytes του}. Μετρά 0 στο όριο των 10MB,
    γιατί δεν φορτώνεται ολόκληρο."""
    lines = fw.split_lines(fw.decode(raw_bytes))
    if not lines:
        st.warning("Το αρχείο είναι άδειο.")
        return _not_ready(source, "το αρχείο είναι άδειο.")
    lengths = [len(line) for line in lines]
    line_length = max(lengths)
    st.caption(f"Αρχείο σταθερού πλάτους: {len(lines):,} γραμμές, {line_length:,} χαρακτήρες ανά γραμμή.")
    if min(lengths) != line_length:
        st.warning(f"Οι γραμμές δεν έχουν όλες το ίδιο μήκος ({min(lengths):,}–{line_length:,} χαρακτήρες) — "
                   "έλεγξε ότι το αρχείο είναι πράγματι σταθερού πλάτους.")
    st.caption("Πρώτες γραμμές (ακατέργαστες):")
    st.code("\n".join(lines[:5]), language=None)

    st.markdown("**Στήλες**")
    codebooks = codebooks or {}
    spec_df = None
    if codebooks:
        options = [f"Codebook: {name}" for name in codebooks] + [MANUAL_COLUMNS]
        choice = st.radio("Στήλες από", options, key=f"fwf_columns_from_{source}", horizontal=True)
        if choice != MANUAL_COLUMNS:
            pdf_name = choice.removeprefix("Codebook: ")
            spec_df = _codebook_spec(source, pdf_name, codebooks[pdf_name], line_length)
    from_codebook = spec_df is not None
    if not from_codebook:
        spec_df = _manual_spec(source)
    columns, errors = fw.clean_spec(spec_df, line_length)
    if errors:
        st.warning("\n\n".join(errors))
        return _not_ready(source, "διόρθωσε τον πίνακα στηλών.")
    if not columns:
        if from_codebook:
            st.info("Τίκαρε τουλάχιστον μία μεταβλητή στον πίνακα.")
            return _not_ready(source, "δεν έχεις τικάρει καμία μεταβλητή.")
        st.info("Πρόσθεσε τουλάχιστον μία στήλη στον πίνακα.")
        return _not_ready(source, "ο πίνακας στηλών είναι άδειος.")

    result, chosen, errors = fw.apply_types(fw.cut_columns(lines, columns), columns)
    if errors:
        st.warning("\n\n".join(errors))
        return _not_ready(source, "κάποια στήλη «Αριθμός» έχει τιμές που δεν είναι αριθμοί.")

    result = _row_filters(source, result, chosen)
    if result is None:
        return _not_ready(source, "διόρθωσε τα φίλτρα γραμμών.")
    if result.empty:
        st.warning("Τα φίλτρα δεν αφήνουν καμία γραμμή.")
        return _not_ready(source, "τα φίλτρα δεν αφήνουν καμία γραμμή.")
    st.caption("Προεπισκόπηση τελικού αποτελέσματος — τύποι: "
               + ", ".join(f"{name}: {kind}" for name, kind in chosen.items()))
    st.dataframe(result.head(10), width="stretch", height=220)
    return {"name": source, "df": result, "sheet": None, "n_sheets": None, "size": 0}


def _row_filters(source: str, df: pd.DataFrame, chosen: dict):
    """Προαιρετικοί κανόνες γραμμών (όλοι μαζί) πάνω στις στήλες που φορτώνονται. Επιστρέφει
    τις γραμμές που περνούν, ή None αν κάποιος κανόνας έχει λάθος."""
    st.markdown("**Γραμμές (προαιρετικό)**")
    st.caption(
        "Κράτα μόνο τις γραμμές που περνούν ΟΛΟΥΣ τους κανόνες, π.χ. «AGE24X ≥ 18». Κενή τιμή δεν περνά "
        "κανέναν κανόνα. Ό,τι κοπεί εδώ δεν φορτώνεται — για να το πάρεις πίσω, ξαναφορτώνεις το αρχείο."
    )
    st.caption(
        "Έρευνες με στάθμιση (π.χ. MEPS): για σωστά τυπικά σφάλματα υποομάδας (π.χ. μόνο ενήλικες) φόρτωσε "
        "όλες τις γραμμές, μαζί με τις στήλες σχεδίου δείγματος (στο MEPS: VARSTR, VARPSU), και φίλτραρε "
        "στην ανάλυση. Για σταθμισμένα σύνολα και μέσους όρους, το φίλτρο εδώ αρκεί."
    )
    base = st.session_state.fixed_width_filters.setdefault(source, fw.empty_filters())
    filter_df = st.data_editor(
        base, num_rows="dynamic", hide_index=True, width="stretch", key=f"fwf_filters_{source}",
        column_config={
            "Στήλη": st.column_config.SelectboxColumn("Στήλη", options=list(chosen), required=True),
            "Τελεστής": st.column_config.SelectboxColumn("Τελεστής", options=list(fw.OPERATORS), required=True),
            "Τιμή": st.column_config.TextColumn("Τιμή", required=True),
        },
    )
    rules, errors = fw.clean_filters(filter_df, chosen)
    if errors:
        st.warning("\n\n".join(errors))
        return None
    if not rules:
        return df
    kept = fw.apply_filters(df, rules)
    st.caption(f"Μετά τα φίλτρα: {len(kept):,} από {len(df):,} γραμμές.")
    return kept


def _prepare_zip(fname: str, raw_bytes: bytes, in_combination: bool):
    """Ένα zip της λίστας: διαλέγεις ένα αρχείο από μέσα του, που περνά από τις ίδιες
    ρυθμίσεις με ένα CSV/Excel. Ένα αρχείο ανά «Φόρτωση»· το zip μένει στη λίστα όσο
    έχει αρχεία που δεν φορτώθηκαν."""
    try:
        members = dl.zip_members(raw_bytes)
    except Exception as e:
        _drop_from_list(fname, f"Σφάλμα ανάγνωσης του {fname}: {e}")
        return None
    loadable, skipped = up.zip_choices(members)
    loaded = st.session_state.zip_loaded_members.setdefault(fname, set())
    remaining = [m for m in loadable if m not in loaded]
    if not remaining:
        if loadable:
            st.session_state.done_uploads.add(fname)
            _forget_pending(fname)
        else:
            types = ", ".join(f".{ext}" for ext in up.ZIP_LOADABLE_EXTENSIONS)
            reasons = "; ".join(f"{n} ({why})" for n, why in skipped)
            _drop_from_list(fname, f"Το {fname} δεν περιέχει αρχείο που μπορεί να φορτωθεί ({types}): {reasons}")
        return None
    if skipped:
        st.caption("Δεν φορτώνονται από αυτό το zip: " + "; ".join(f"{n} ({why})" for n, why in skipped))
    member = st.selectbox("Αρχείο μέσα στο zip", remaining, key=f"zipmember_{fname}")
    try:
        member_bytes = dl.read_zip_member(raw_bytes, member)
    except Exception as e:   # π.χ. zip με κωδικό ή αλλοιωμένο αρχείο
        _drop_from_list(fname, f"Σφάλμα ανάγνωσης του {member}: {e}")
        return None
    codebooks = {name: (lambda name=name: dl.read_zip_member(raw_bytes, name))
                 for name in up.codebook_candidates(members)}
    entry = _prepare_file(fname, member.rsplit(".", 1)[-1].lower(), member_bytes, in_combination,
                          source=f"{fname}/{member}", codebooks=codebooks)
    if entry is not None:
        entry["member"] = member
        entry["other_members"] = len(remaining) - 1
    return entry


def _mark_loaded(fname: str, entry: dict) -> bool:
    """Σημειώνει ό,τι φορτώθηκε. True αν το αρχείο της λίστας τελείωσε (φεύγει από τη λίστα)."""
    member = entry.get("member")
    source = f"{fname}/{member}" if member else fname
    finished = True
    if entry["sheet"] is not None:
        loaded = st.session_state.excel_loaded_sheets.setdefault(source, set())
        loaded.add(entry["sheet"])
        finished = len(loaded) >= entry["n_sheets"]
    if finished and member:
        st.session_state.zip_loaded_members.setdefault(fname, set()).add(member)
        finished = entry["other_members"] == 0
    return finished


def load_settings() -> None:
    """Η λίστα «Ρυθμίσεις φόρτωσης»: ρυθμίσεις ανά αρχείο, «Συνδυασμός» και κουμπί «Φόρτωση»."""
    if st.session_state.pending_uploads:
        st.header("Ρυθμίσεις φόρτωσης")
        st.caption(
            "Όρισε τις ρυθμίσεις κάθε αρχείου. Τίκαρε «Συνδυασμός» σε όσα θέλεις να συνδυαστούν "
            "(η σειρά συνδυασμού είναι η σειρά με την οποία τα τικάρεις) και πάτησε «Φόρτωση». "
            "Τα υπόλοιπα φορτώνονται ως ξεχωριστά datasets."
        )
        pending_names = list(st.session_state.pending_uploads)
        # Η τιμή κάθε checkbox είναι ήδη στο session_state από την αρχή του run, οπότε η σειρά
        # ενημερώνεται ΠΡΙΝ σχεδιαστούν οι ετικέτες και δείχνουν αμέσως τη σωστή θέση.
        st.session_state.combine_order = up.update_combine_order(
            st.session_state.combine_order,
            [f for f in pending_names if st.session_state.get(f"combine_{f}", False)],
        )
        order = st.session_state.combine_order
        prepared = {}   # αρχείο της λίστας -> ό,τι επιστρέφει το _prepare_file
        for fname in pending_names:
            raw_bytes = st.session_state.pending_uploads[fname]
            ext = fname.rsplit(".", 1)[-1].lower()
            position = order.index(fname) + 1 if fname in order else None
            with st.expander(f"{fname} — συνδυασμός: {position}ο" if position else fname, expanded=True):
                in_combination = st.checkbox("Συνδυασμός", key=f"combine_{fname}")
                if ext == "zip":
                    entry = _prepare_zip(fname, raw_bytes, in_combination)
                else:
                    entry = _prepare_file(fname, ext, raw_bytes, in_combination)
                if entry is not None:
                    prepared[fname] = entry

        # Για ένα zip μετρά το αρχείο που φορτώνεται από μέσα του (αποσυμπιεσμένο), όχι το zip.
        plan = up.plan_load(
            {f: prepared[f]["size"] if f in prepared else len(b) for f, b in st.session_state.pending_uploads.items()},
            st.session_state.combine_order,
            combination_in_progress=st.session_state.batch is not None,
            not_ready={f: entry["problem"] for f, entry in prepared.items() if entry["df"] is None},
        )
        st.caption(
            f"Συνολικό μέγεθος αρχείων: {plan['total_bytes'] / (1024 * 1024):.1f}MB "
            f"(όριο {up.MAX_TOTAL_UPLOAD_BYTES / (1024 * 1024):.0f}MB)."
        )
        single_ticked = len(plan["combine"]) == 1
        if single_ticked:
            st.info("Τίκαρε τουλάχιστον 2 αρχεία για συνδυασμό ή κανένα.")
        if st.button("Φόρτωση", key="load_all", disabled=single_ticked):
            if plan["error"]:
                st.toast(plan["error"])
            else:
                for fname in plan["separate"]:
                    entry = prepared[fname]
                    st.session_state.datasets[entry["name"]] = entry["df"]
                    if _mark_loaded(fname, entry):
                        st.session_state.done_uploads.add(fname)
                        _forget_pending(fname)
                if plan["combine"]:
                    st.session_state.batch = {
                        "names": list(plan["combine"]),
                        "ready": {f: prepared[f]["df"] for f in plan["combine"]},
                    }
                    for fname in plan["combine"]:
                        _forget_pending(fname)
                st.rerun()


def combination_screen() -> None:
    """Η οθόνη «Συνδυασμός αρχείων», όταν όλα τα τικαρισμένα αρχεία έχουν φορτωθεί."""
    if st.session_state.batch and len(st.session_state.batch["ready"]) == len(st.session_state.batch["names"]):
        _render_combination()
