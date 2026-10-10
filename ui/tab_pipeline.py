"""Tab Pipeline: ενεργό σύνολο (επεξεργάσιμο), Update/Where/Set, Casting & String Functions,
Missing Values, Duplicates, Outliers, Export."""
import pandas as pd
import streamlit as st

from modules import cleaning_pipeline as cp
from ui import common
from ui import state


def render(name: str) -> None:
    common.undo_button(name, "undo_pipeline")
    cs = state.cleaning_state(name)

    # ---------------------------------------------------------- Ενότητα Β
    st.subheader("Ενεργό σύνολο δεδομένων")
    st.caption(
        "Single source of truth: αυτό ΕΙΝΑΙ το st.session_state.datasets[...] που διαβάζουν "
        "και γράφουν και οι 4 καρτέλες. Επεξεργάσιμο εδώ — επίλεξε γραμμές, edit inline, "
        "και πάτησε 'Αποθήκευση αλλαγών' ή 'Διαγραφή επιλεγμένων'."
    )
    cdf = st.session_state.datasets[name]
    st.markdown(f"**{cdf.shape[0]} γραμμές × {cdf.shape[1]} στηλών**")
    edited_active, selected_active_idx = common.filterable_editor(cdf, "active", show_filter=False)
    common.restore_delete_actions(
        name, edited_active, selected_active_idx, "active",
        restore_label="Αποθήκευση αλλαγών", delete_label="Διαγραφή επιλεγμένων",
    )

    st.divider()

    # ---------------------------------------------------------- Ενότητα 1
    st.subheader("Update / Where / Set")
    common.update_where_set(name, "us_")

    st.divider()

    # ---------------------------------------------------------- Ενότητα 2
    st.subheader("Casting & Manipulation")
    tc1, tc2 = st.columns(2)
    with tc1:
        cast_col_name = st.selectbox("Στήλη", cdf.columns.tolist(), key="cast_col")
    with tc2:
        cast_target = st.selectbox("Νέος τύπος", ["string", "int", "float", "datetime"], key="cast_target")
    st.caption("Για int/float: αφαιρούνται αυτόματα σύμβολα νομίσματος (€ $ £ ¥) και διαχωριστικά χιλιάδων/δεκαδικών. Τιμές που δεν μετατρέπονται γίνονται NULL (όχι σφάλμα).")
    if st.button("Εφαρμογή", key="cast_apply"):
        new_df, n_fail = cp.cast_column(cdf, cast_col_name, cast_target)
        state.push_undo(name, f"Casting: '{cast_col_name}' -> {cast_target}")
        st.session_state.datasets[name] = new_df
        if n_fail > 0:
            st.warning(f"{n_fail} τιμές δεν μετατράπηκαν και έγιναν NULL.")
        else:
            st.success("Όλες οι τιμές μετατράπηκαν επιτυχώς.")
        st.rerun()

    st.markdown("**String Functions**")

    # TRIM
    trim1, trim2 = st.columns([3, 1])
    with trim1:
        trim_col = st.selectbox("Στήλη-στόχος", cdf.columns.tolist(), key="trim_col")
    with trim2:
        st.write("")
        if st.button("Εφαρμογή TRIM", key="trim_apply"):
            state.push_undo(name, f"TRIM: '{trim_col}'")
            st.session_state.datasets[name] = cp.trim_column(cdf, trim_col)
            st.success(f"Έγινε TRIM στη στήλη '{trim_col}'.")
            st.rerun()

    # CONCAT
    cc1, cc2, cc3, cc4 = st.columns([2, 2, 2, 2])
    with cc1:
        concat_col1 = st.selectbox("Στήλη 1", cdf.columns.tolist(), key="concat_col1")
    with cc2:
        concat_col2 = st.selectbox("Στήλη 2", cdf.columns.tolist(), key="concat_col2")
    with cc3:
        concat_sep = st.text_input("Διαχωριστικό (κενό = ένα κενό)", key="concat_sep")
    with cc4:
        concat_new_name = st.text_input("Όνομα νέας στήλης", key="concat_new_name")
    if st.button("Εφαρμογή CONCAT", key="concat_apply"):
        if not concat_new_name:
            st.toast("Το 'Όνομα νέας στήλης' είναι υποχρεωτικό.")
        else:
            try:
                new_df = cp.concat_columns(cdf, concat_col1, concat_col2, concat_sep, concat_new_name)
                state.push_undo(name, f"CONCAT: '{concat_col1}' + '{concat_col2}' -> '{concat_new_name}'")
                st.session_state.datasets[name] = new_df
                st.success(f"Δημιουργήθηκε η στήλη '{concat_new_name}'.")
                st.rerun()
            except ValueError as e:
                st.toast(str(e))

    # UPPER / LOWER ανά θέση χαρακτήρα
    uc1, uc2, uc3, uc4 = st.columns([2, 2, 1, 1])
    with uc1:
        case_col = st.selectbox("Στήλη-στόχος", cdf.columns.tolist(), key="case_col")
    with uc2:
        case_pos = st.text_input("Θέση ή εύρος (π.χ. 3 ή 1-3)", key="case_pos")
    with uc3:
        case_mode_label = st.radio("Λειτουργία", ["UPPER", "LOWER"], key="case_mode", horizontal=True)
    with uc4:
        st.write("")
        if st.button("Εφαρμογή", key="case_apply"):
            try:
                new_df = cp.apply_case_by_position(cdf, case_col, case_pos, case_mode_label.lower())
                state.push_undo(name, f"{case_mode_label}: '{case_col}' θέση {case_pos}")
                st.session_state.datasets[name] = new_df
                st.success(f"Εφαρμόστηκε {case_mode_label} στη στήλη '{case_col}'.")
                st.rerun()
            except ValueError as e:
                st.toast(str(e))

    st.divider()

    # ---------------------------------------------------------- Ενότητα 3
    st.subheader("Missing Values")
    missing_df = cp.detect_missing_values(cdf)
    st.caption(f"Εντοπίστηκαν {missing_df.shape[0]} γραμμές με τουλάχιστον μία κενή τιμή.")

    edited_mv, selected_mv_idx = common.filterable_editor(missing_df, "mv")
    common.restore_delete_actions(name, edited_mv, selected_mv_idx, "mv")

    st.divider()

    # ---------------------------------------------------------- Ενότητα 4
    st.subheader("Duplicates")
    dup_key_col = st.selectbox("Key column", cdf.columns.tolist(), key="dup_key_col_sel")
    st.caption(
        "(Επίλεξε στήλη που αναμένεται να έχει μοναδικές τιμές, π.χ. κωδικός/αναγνωριστικό — "
        "σε στήλη με λίγες, επαναλαμβανόμενες κατηγορίες θα εμφανιστούν ως duplicate σχεδόν όλες οι γραμμές)"
    )
    cs["dup_key_col"] = dup_key_col

    dup_df = cp.detect_key_duplicates(cdf, dup_key_col)
    st.caption(f"Εντοπίστηκαν {dup_df.shape[0]} γραμμές.")
    edited_dup, selected_dup_idx = common.filterable_editor(dup_df, "dup", show_filter=False)
    common.restore_delete_actions(name, edited_dup, selected_dup_idx, "dup")

    st.divider()

    # ---------------------------------------------------------- Ενότητα 5
    st.subheader("Outliers Detection")
    st.caption("Μόνο για numeric και date/datetime στήλες.")

    for i, rule in enumerate(cs["outlier_rules"]):
        rc1, rc2, rc3, rc4 = st.columns([2, 1, 1, 1])
        with rc1:
            st.write(f"**{rule['col']}**")
        with rc2:
            st.write(f"Min: {rule['min']}")
        with rc3:
            st.write(f"Max: {rule['max']}")
        with rc4:
            if st.button("Αφαίρεση", key=f"outlier_rule_remove_{i}"):
                cs["outlier_rules"].pop(i)
                st.rerun()

    with st.expander("Προσθήκη κανόνα", expanded=len(cs["outlier_rules"]) == 0):
        numeric_date_cols = [
            c for c in cdf.columns
            if pd.api.types.is_numeric_dtype(cdf[c]) or pd.api.types.is_datetime64_any_dtype(cdf[c])
        ]
        if not numeric_date_cols:
            st.info("Δεν υπάρχουν στήλες τύπου αριθμού ή ημερομηνίας.")
        else:
            nrc1, nrc2, nrc3 = st.columns(3)
            with nrc1:
                nr_col = st.selectbox("Στήλη", numeric_date_cols, key="outlier_new_col")
            with nrc2:
                nr_min_txt = st.text_input("Min (κενό = χωρίς κάτω όριο)", key="outlier_new_min")
            with nrc3:
                nr_max_txt = st.text_input("Max (κενό = χωρίς άνω όριο)", key="outlier_new_max")
            if st.button("Προσθήκη κανόνα", key="outlier_add_rule_btn"):
                is_date = pd.api.types.is_datetime64_any_dtype(cdf[nr_col])
                try:
                    min_v = (pd.to_datetime(nr_min_txt) if is_date else float(nr_min_txt)) if nr_min_txt.strip() else None
                    max_v = (pd.to_datetime(nr_max_txt) if is_date else float(nr_max_txt)) if nr_max_txt.strip() else None
                    if min_v is None and max_v is None:
                        st.warning("Όρισε τουλάχιστον ένα από τα δύο όρια.")
                    else:
                        cs["outlier_rules"].append({"col": nr_col, "min": min_v, "max": max_v})
                        st.rerun()
                except ValueError:
                    st.toast("Μη έγκυρη τιμή ορίου.")

    outlier_df = cp.detect_outliers(cdf, cs["outlier_rules"])
    st.caption(f"Εντοπίστηκαν {outlier_df.shape[0]} γραμμές.")
    edited_out, selected_out_idx = common.filterable_editor(outlier_df, "outlier", show_filter=False)
    common.restore_delete_actions(name, edited_out, selected_out_idx, "outlier")

    st.divider()

    # ---------------------------------------------------------- Ενότητα 6
    st.subheader("Export")
    st.caption(
        "Οι αλλαγές είναι ήδη ζωντανές στο ενεργό dataset (βλ. Ενότητα Β) — αυτό εδώ είναι "
        "μόνο για λήψη CSV/Excel ή για να κρατήσεις ένα ξεχωριστό αντίγραφο με άλλο όνομα."
    )
    current = st.session_state.datasets[name]
    new_name = st.text_input("Όνομα αντιγράφου (προαιρετικό)", value=f"{name} (αντίγραφο)", key="clean_export_name")
    if st.button("Αποθήκευση ως αντίγραφο", key="clean_export_save"):
        st.session_state.datasets[new_name] = current.copy()
        st.success(f"Αποθηκεύτηκε ως '{new_name}'.")
        st.rerun()

    common.export_buttons(current, "καθαρισμένα_δεδομένα", "clean_export_")
