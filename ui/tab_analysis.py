"""Tab Analysis: ενεργό σύνολο, περιγραφικά στατιστικά και Ομαδοποίηση & Ανάλυση (tables)."""
import pandas as pd
import streamlit as st

from modules import analysis as an
from modules import query_builder as qb
from ui import common
from ui import state


def _render_group_analysis(df: pd.DataFrame, container: dict, dataset_name: str):
    """
    "Ομαδοποίηση & Ανάλυση" (tab Analysis).
    - "Προσθήκη Table": builder (επιλογή στηλών + WHERE — το ήδη υπάρχον WHERE
      εργαλείο αυτούσιο, χωρίς primary key) -> το κουμπί "Προσθήκη Table"
      παγώνει στήλες+WHERE σε ένα νέο table (έως qb.MAX_TABLES συνολικά).
    - Dropdown επιλέγει ποιο table είναι το "ενεργό". Η εναλλαγή ΔΕΝ διαγράφει
      ούτε κάνει reset τα υπόλοιπα tables — καθένα κρατά την πλήρη διαμόρφωσή του.
    - Steps 2-4 (Window Functions / τελικό ORDER BY / προαιρετικό GROUP BY)
      δουλεύουν πάνω στο ΕΝΕΡΓΟ table.
    Το container['tables'] είναι η ίδια δομή που διαβάζει και το Workshop (προβολή,
    tables[...]) και όπου γράφει το save_table() του — καμία ξεχωριστή αντιγραφή.
    """
    all_cols = df.columns.tolist()
    kp = f"ga_{dataset_name}_"

    # -------------------------------------------------- Προσθήκη Table
    st.markdown("**Προσθήκη Table**")
    builder_kp = f"{kp}builder_"
    container["builder_cols"] = common.column_checkboxes(all_cols, builder_kp)

    if not container["builder_cols"]:
        st.info("Επίλεξε τουλάχιστον μία στήλη για το νέο table.")
    else:
        container["builder_filters"] = common.where_filters(
            df, container["builder_cols"], container["builder_filters"], builder_kp
        )

    tables = container["tables"]
    at_limit = len(tables) >= qb.MAX_TABLES
    if at_limit:
        st.warning(f"Έχεις ήδη {qb.MAX_TABLES} tables (το μέγιστο). Διάγραψε ένα για να προσθέσεις νέο.")
    if st.button("Προσθήκη Table", key=f"{kp}add_table_btn", disabled=(at_limit or not container["builder_cols"])):
        table_num = container["next_num"]
        created = qb.new_table(
            table_id=table_num, name=f"Πίνακας {table_num}",
            selected_cols=container["builder_cols"], filters=container["builder_filters"],
        )
        tables.append(created)
        container["active_id"] = created["id"]
        # Γράφουμε ΑΠΕΥΘΕΙΑΣ στο session_state του selectbox (όχι μόνο στο container) γιατί
        # το index= ενός widget σεβαστεί μόνο στην πρώτη-ποτέ instantiation του — σε επόμενα
        # reruns το ήδη-υπάρχον session_state του widget υπερισχύει του index=.
        st.session_state[f"{kp}active_table_sel"] = created["name"]
        container["next_num"] += 1
        container["builder_cols"] = []
        container["builder_filters"] = []
        st.rerun()

    st.divider()

    if not tables:
        st.info("Δεν έχει δημιουργηθεί ακόμα κανένα table. Χρησιμοποίησε το 'Προσθήκη Table' παραπάνω.")
        return

    # -------------------------------------------------- Επιλογή ενεργού table
    id_to_table = {t["id"]: t for t in tables}
    if container["active_id"] not in id_to_table:
        container["active_id"] = tables[0]["id"]
    names = [t["name"] for t in tables]
    ids = [t["id"] for t in tables]
    active_pos = ids.index(container["active_id"])

    sel1, sel2 = st.columns([4, 1])
    # Το κουμπί διαγραφής ΠΡΕΠΕΙ να render-άρεται (και να τρέξει το st.rerun() του)
    # ΠΡΙΝ την instantiation του selectbox παρακάτω: η Session State API απαγορεύει
    # να γράψεις σε key widget που έχει ήδη render-αριστεί ΣΕ ΑΥΤΟ το run. Η σειρά
    # στο layout (sel2 δεξιά, sel1 αριστερά) καθορίζεται από τη στήλη, όχι από τη
    # σειρά εκτέλεσης του κώδικα.
    with sel2:
        st.write("")
        if st.button("Διαγραφή", key=f"{kp}del_table_btn"):
            del_id = container["active_id"]
            tables[:] = [t for t in tables if t["id"] != del_id]
            container["active_id"] = tables[0]["id"] if tables else None
            if tables:
                st.session_state[f"{kp}active_table_sel"] = tables[0]["name"]
            else:
                st.session_state.pop(f"{kp}active_table_sel", None)
            st.rerun()

    with sel1:
        chosen_name = st.selectbox("Ενεργό table", names, index=active_pos, key=f"{kp}active_table_sel")
    container["active_id"] = ids[names.index(chosen_name)]
    active_table = id_to_table[container["active_id"]]

    if qb.is_snapshot(active_table):
        # Table από το save_table() του Workshop: σταθερό αποτέλεσμα, μόνο προβολή/λήψη/διαγραφή.
        snapshot = active_table["result_df"]
        st.caption(
            f"**{active_table['name']}** — table από το Workshop ({snapshot.shape[0]} γραμμές × "
            f"{snapshot.shape[1]} στήλες). Μόνο για προβολή: για αλλαγές, ξανατρέξε τον κώδικα στο Workshop."
        )
        st.dataframe(snapshot, width="stretch")
        common.export_buttons(snapshot, active_table["name"], f"{kp}t{active_table['id']}_export_")
        return

    # Αμυντικός καθαρισμός: αν το table αναφέρεται σε στήλη που δεν υπάρχει πια στο
    # ενεργό dataset (κανονικά προλαμβάνεται ήδη στο state.undo_last_change, αλλά το
    # κρατάμε κι εδώ ως δεύτερη γραμμή άμυνας), αφαίρεσέ την πριν σκάσει οτιδήποτε
    # παρακάτω διαβάζει df[col] απευθείας για κάθε selected_cols.
    stale_cols = [c for c in active_table["selected_cols"] if c not in df.columns]
    if stale_cols:
        active_table["selected_cols"] = [c for c in active_table["selected_cols"] if c in df.columns]
        st.warning(
            f"Οι στήλες {', '.join(stale_cols)} δεν υπάρχουν πια στο ενεργό dataset "
            f"(πιθανόν λόγω αναίρεσης) και αφαιρέθηκαν από το table '{active_table['name']}'."
        )

    where_summary = f"{len(active_table['filters'])} συνθήκη/ες WHERE" if active_table["filters"] else "χωρίς WHERE"
    st.caption(f"**{active_table['name']}** — στήλες: {', '.join(active_table['selected_cols'])} · {where_summary}")

    st.divider()

    tkp = f"{kp}t{active_table['id']}_"   # key prefix scoped στο σταθερό id του table (όχι στη θέση στη λίστα)
    selected_cols = active_table["selected_cols"]

    # -------------------------------------------------- Step 2: Window Functions
    st.markdown("**Window Functions**")
    for i, wf in enumerate(active_table["window_functions"]):
        wr1, wr2 = st.columns([5, 1])
        with wr1:
            over_bits = []
            if wf.get("partition_col"):
                gran_suffix = f' ({wf["partition_date_part"]})' if wf.get("partition_date_part") else ""
                over_bits.append(f'PARTITION BY {wf["partition_col"]}{gran_suffix}')
            if wf.get("order_col"):
                over_bits.append(f'ORDER BY {wf["order_col"]} {wf.get("order_dir", "ASC")}')
            over_txt = " ".join(over_bits) if over_bits else "(χωρίς PARTITION/ORDER)"
            st.write(f'**{wf["new_name"]}** = {wf["agg_func"]}("{wf["target_col"]}") OVER ({over_txt})')
        with wr2:
            if st.button("Αφαίρεση", key=f"{tkp}wf_rm_{i}"):
                active_table["window_functions"].pop(i)
                st.rerun()

    # Οι widget keys της φόρμας ενσωματώνουν το wf_form_seq: μετά από κάθε επιτυχή
    # προσθήκη αυξάνεται, ώστε η ΕΠΟΜΕΝΗ φόρμα να πάρει εντελώς ΝΕΑ keys (καθαρά
    # defaults) αντί να κληρονομήσει τιμές (π.χ. ORDER BY) από την προηγούμενη.
    wfkp = f"{tkp}wf{active_table.setdefault('wf_form_seq', 0)}_"
    with st.expander("Προσθήκη νέας window function", expanded=len(active_table["window_functions"]) == 0):
        wf1, wf2 = st.columns(2)
        with wf1:
            agg_func = st.selectbox("Aggregate function", qb.AGG_FUNCS, key=f"{wfkp}new_func")
        numeric_needed = agg_func in qb.NUMERIC_REQUIRED_FUNCS
        target_options = [c for c in selected_cols if not numeric_needed or pd.api.types.is_numeric_dtype(df[c].dtype)]
        if not target_options:
            st.info("Δεν υπάρχουν κατάλληλες (αριθμητικές) στήλες για αυτή τη συνάρτηση.")
        else:
            with wf2:
                target_col = st.selectbox("Στήλη-στόχος", target_options, key=f"{wfkp}new_target")
            st.caption("OVER")
            wp1, wp2 = st.columns(2)
            with wp1:
                partition_choice = st.selectbox("PARTITION BY", ["(κενό)"] + selected_cols, key=f"{wfkp}new_partition")
            partition_col = None if partition_choice == "(κενό)" else partition_choice
            partition_date_part = None
            if partition_col and pd.api.types.is_datetime64_any_dtype(df[partition_col].dtype):
                with wp1:
                    part_gran_options = ["(πλήρης ημερομηνία/ώρα)"] + qb.DATE_GRANULARITIES
                    part_gran_choice = st.selectbox(
                        "PARTITION BY ημερομηνίας ανά", part_gran_options, key=f"{wfkp}new_partition_datepart",
                    )
                    partition_date_part = None if part_gran_choice == part_gran_options[0] else part_gran_choice
            with wp2:
                order_choice = st.selectbox("ORDER BY", ["(κενό)"] + selected_cols, key=f"{wfkp}new_order")
            order_col = None if order_choice == "(κενό)" else order_choice
            order_dir = "ASC"
            if order_col:
                order_dir = st.radio("Κατεύθυνση", ["ASC", "DESC"], key=f"{wfkp}new_orderdir", horizontal=True)
            new_name = st.text_input("Όνομα νέας στήλης", key=f"{wfkp}new_name")
            if st.button("Προσθήκη στον πίνακα", key=f"{wfkp}add_btn"):
                try:
                    existing = set(selected_cols) | {w["new_name"] for w in active_table["window_functions"]}
                    qb.validate_new_column_name(new_name, existing)
                    active_table["window_functions"].append({
                        "agg_func": agg_func, "target_col": target_col,
                        "partition_col": partition_col, "partition_date_part": partition_date_part,
                        "order_col": order_col, "order_dir": order_dir, "new_name": new_name,
                    })
                    active_table["wf_form_seq"] += 1
                    st.rerun()
                except ValueError as e:
                    st.toast(str(e))

    st.divider()

    # -------------------------------------------------- Step 3: Τελική ταξινόμηση (έως 3 επίπεδα)
    st.markdown("**Τελική ταξινόμηση (ORDER BY)**")
    st.caption(
        "Έως 3 επίπεδα ταξινόμησης, το καθένα μέσα στο προηγούμενο — π.χ. 1ο: Προϊόν, "
        "2ο: Ημερομηνία (μέσα σε κάθε προϊόν), 3ο: Τιμή (μέσα σε κάθε προϊόν+ημερομηνία)."
    )
    prev_gb = active_table.get("group_by")
    if prev_gb and prev_gb.get("group_col") and prev_gb.get("value_col"):
        final_order_options = [prev_gb["group_col"], qb.group_by_alias(prev_gb)]
    else:
        final_order_options = selected_cols + [w["new_name"] for w in active_table["window_functions"]]

    prev_ob_list = active_table.get("final_order_by") or []
    ob_options = ["(καμία)"] + final_order_options
    dir_options = ["ASC", "DESC"]
    level_labels = ["1η ταξινόμηση", "2η ταξινόμηση (μέσα στην 1η)", "3η ταξινόμηση (μέσα στη 2η)"]

    new_order_by = []
    for i, level_label in enumerate(level_labels):
        prev_ob = prev_ob_list[i] if i < len(prev_ob_list) else {}
        default_ob_col = prev_ob.get("col") if prev_ob.get("col") in final_order_options else "(καμία)"
        default_dir = prev_ob.get("dir") if prev_ob.get("dir") in dir_options else "ASC"
        ob1, ob2 = st.columns(2)
        with ob1:
            order_choice = st.selectbox(
                level_label, ob_options, index=ob_options.index(default_ob_col), key=f"{tkp}orderby_{i}",
            )
        with ob2:
            order_dir = st.radio(
                "Κατεύθυνση", dir_options, index=dir_options.index(default_dir),
                key=f"{tkp}orderdir_{i}", horizontal=True,
            )
        new_order_by.append({"col": None if order_choice == "(καμία)" else order_choice, "dir": order_dir})
    active_table["final_order_by"] = new_order_by

    st.divider()

    # -------------------------------------------------- Step 4: Group By (προαιρετικό)
    st.markdown("**Group By (προαιρετικό)**")
    enable_groupby = st.checkbox("Ενεργοποίηση Group By", value=bool(active_table.get("group_by")), key=f"{tkp}gb_enable")
    if enable_groupby:
        prev_gb2 = active_table.get("group_by") or {}
        gb1, gb2, gb3 = st.columns(3)
        with gb1:
            default_gcol = prev_gb2.get("group_col") if prev_gb2.get("group_col") in selected_cols else selected_cols[0]
            group_col = st.selectbox("Ομαδοποίηση κατά", selected_cols, index=selected_cols.index(default_gcol), key=f"{tkp}gb_col")

            date_part = None
            if pd.api.types.is_datetime64_any_dtype(df[group_col].dtype):
                gran_options = ["(πλήρης ημερομηνία/ώρα)"] + qb.DATE_GRANULARITIES
                default_gran = prev_gb2.get("date_part") if prev_gb2.get("date_part") in qb.DATE_GRANULARITIES else gran_options[0]
                gran_choice = st.selectbox(
                    "Ομαδοποίηση ημερομηνίας ανά", gran_options,
                    index=gran_options.index(default_gran), key=f"{tkp}gb_datepart",
                )
                date_part = None if gran_choice == gran_options[0] else gran_choice

        value_options = [c for c in selected_cols if pd.api.types.is_numeric_dtype(df[c].dtype)] + [
            w["new_name"] for w in active_table["window_functions"]
        ]
        if not value_options:
            st.info("Δεν υπάρχουν αριθμητικές στήλες (ή window functions) για στήλη τιμής.")
            active_table["group_by"] = None
        else:
            with gb2:
                default_vcol = prev_gb2.get("value_col") if prev_gb2.get("value_col") in value_options else value_options[0]
                value_col = st.selectbox("Στήλη τιμής", value_options, index=value_options.index(default_vcol), key=f"{tkp}gb_value")
            with gb3:
                default_gfunc = prev_gb2.get("func") if prev_gb2.get("func") in qb.AGG_FUNCS else qb.AGG_FUNCS[0]
                gfunc = st.selectbox("Συνάρτηση", qb.AGG_FUNCS, index=qb.AGG_FUNCS.index(default_gfunc), key=f"{tkp}gb_func")
            active_table["group_by"] = {"group_col": group_col, "value_col": value_col, "func": gfunc, "date_part": date_part}
    else:
        active_table["group_by"] = None

    st.divider()

    # -------------------------------------------------- Update / Where / Set
    # Ίδιο εργαλείο με το Pipeline — ενημερώνει απευθείας το ενεργό
    # σύνολο δεδομένων (single source of truth), οπότε η αλλαγή φαίνεται αμέσως
    # και στο αποτέλεσμα παρακάτω.
    st.markdown("**Update / Where / Set**")
    common.update_where_set(dataset_name, f"{kp}us_")

    st.divider()

    # -------------------------------------------------- Άμεση εμφάνιση αποτελέσματος
    qb.execute(df, active_table)
    st.markdown("**Αποτέλεσμα**")
    if active_table["error"]:
        st.error(active_table["error"])
    else:
        if active_table["result_message"]:
            st.info(active_table["result_message"])
        if active_table["result_df"] is not None and not active_table["result_df"].empty:
            st.dataframe(active_table["result_df"], width="stretch")
            common.export_buttons(active_table["result_df"], active_table["name"], f"{tkp}export_")


def render(df: pd.DataFrame, name: str) -> None:
    common.undo_button(name, "undo_analysis")

    # ---------------------------------------------------------- Ενότητα 1
    st.subheader("Ενεργό σύνολο δεδομένων")
    st.caption(f"**{name}** — {df.shape[0]} γραμμές × {df.shape[1]} στήλες")
    st.dataframe(df, width="stretch", height=400)

    st.divider()

    # ---------------------------------------------------------- Ενότητα 2
    st.subheader("Περιγραφικά στατιστικά")
    numeric_df = df.select_dtypes(include="number")
    non_numeric_df = df.select_dtypes(exclude="number")

    st.markdown("**Αριθμητικές στήλες**")
    if numeric_df.empty:
        st.info("Δεν βρέθηκαν αριθμητικές στήλες.")
    else:
        st.dataframe(an.describe_numeric(df), width="stretch")

    st.markdown("**Κατηγορικές / Text στήλες**")
    if non_numeric_df.empty:
        st.info("Δεν βρέθηκαν μη αριθμητικές στήλες.")
    else:
        st.dataframe(an.describe_non_numeric(df), width="stretch")

    st.divider()

    # ---------------------------------------------------------- Ενότητα 3
    st.subheader("Ομαδοποίηση & Ανάλυση")
    ga_state = state.group_analysis_state(name)
    _render_group_analysis(df, ga_state, name)
