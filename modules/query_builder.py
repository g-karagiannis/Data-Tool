"""
Καρτέλα Analysis: "Ομαδοποίηση & Ανάλυση".
Ένας ενεργός πίνακας (χωρίς slots, χωρίς pivot). Ροή: Step 0 (επιλογή
στηλών) -> Step 1 (WHERE) -> Step 2 (window functions, επαναλαμβανόμενο) ->
Step 3 (τελικό ORDER BY) -> Step 4 (προαιρετικό GROUP BY).

Αρχιτεκτονική (SQL-first μέσω DuckDB): κάθε βήμα υλοποιείται ως parameterized
SQL πάνω στο ΗΔΗ υλοποιημένο (materialized) αποτέλεσμα του προηγούμενου
βήματος — μία σειρά διαδοχικών queries, όχι python-side filtering/grouping.
Ονόματα στηλών επικυρώνονται πάντα έναντι λίστας πραγματικών στηλών
(whitelist), τιμές φίλτρων περνάνε πάντα ως παράμετροι.
"""
import re

import duckdb
import pandas as pd

NUMERIC_OPERATORS = ["=", "!=", ">", ">=", "<", "<=", "BETWEEN"]
TEXT_OPERATORS = ["=", "!=", "IN", "CONTAINS"]
DATE_OPERATORS = ["BETWEEN", "BEFORE", "AFTER"]

AGG_FUNCS = ["SUM", "AVG", "COUNT", "MEDIAN", "MIN", "MAX"]
NUMERIC_REQUIRED_FUNCS = {"SUM", "AVG", "MEDIAN"}   # MIN/MAX/COUNT επιτρέπονται σε οποιαδήποτε στήλη

MAX_UNIQUE_VALUES_FOR_DROPDOWN = 500
MAX_TABLES = 10   # μέγιστος αριθμός tables ανά dataset (του Analysis και του Workshop μαζί)
WORKSHOP_SOURCE = "workshop"   # table-«στιγμιότυπο» από το save_table() του Workshop
ANALYSIS_TABLE_PREFIX = "Πίνακας"   # αυτόματο όνομα των tables του Analysis: "Πίνακας 1", "Πίνακας 2", ...
ANALYSIS_TABLE_NAME = re.compile(rf"{ANALYSIS_TABLE_PREFIX} \d+")
MAX_ORDER_BY_LEVELS = 3   # επίπεδα τελικής ταξινόμησης (Step 3) — π.χ. Προϊόν -> Ημερομηνία -> Τιμή

DATE_GRANULARITIES = ["YEAR", "MONTH", "DAY", "HOUR", "MINUTE"]   # GROUP BY ημερομηνίας/ώρας, βλ. date_trunc_expr


# ------------------------------------------------------------------ state

def new_state() -> dict:
    """Αρχική κατάσταση ΕΝΟΣ table (στήλες+WHERE παγωμένα στη δημιουργία,
    window functions/τελικό ORDER BY/GROUP BY επεξεργάσιμα όσο είναι ενεργό)."""
    return {
        "id": None,
        "name": None,
        "selected_cols": [],
        "filters": [],           # [{"col","op","val","val2","combine"}] — παγωμένο μετά τη δημιουργία
        "window_functions": [],  # [{"agg_func","target_col","partition_col","partition_date_part","order_col","order_dir","new_name"}]
        # Έως MAX_ORDER_BY_LEVELS επίπεδα, εφαρμόζονται το ένα μέσα στο άλλο (SQL
        # ORDER BY col1 dir1, col2 dir2, col3 dir3) — π.χ. 1ο: Προϊόν, 2ο: Ημερομηνία
        # (μέσα σε κάθε προϊόν), 3ο: Τιμή (μέσα σε κάθε προϊόν+ημερομηνία).
        "final_order_by": [{"col": None, "dir": "ASC"} for _ in range(MAX_ORDER_BY_LEVELS)],
        "group_by": None,        # {"group_col","value_col","func"} ή None
        "result_df": None,
        "result_message": None,
        "error": None,
        # Αυξάνεται μετά από κάθε επιτυχή προσθήκη window function ώστε η φόρμα
        # "Προσθήκη νέας window function" να παίρνει ΝΕΑ (ποτέ ξαναχρησιμοποιημένα)
        # widget keys στο επόμενο render — αλλιώς π.χ. ένα ORDER BY από την
        # προηγούμενη προσθήκη θα επιβίωνε σιωπηλά, μετατρέποντας μια σκόπιμη
        # "σύνολο ομάδας" aggregate σε cumulative/running.
        "wf_form_seq": 0,
    }


def new_table(table_id: int, name: str, selected_cols: list, filters: list) -> dict:
    """Δημιουργεί ένα νέο table (μέσω 'Προσθήκη Table'): στήλες + WHERE παγώνουν
    εδώ· τα Steps 2-4 (window functions/ORDER BY/GROUP BY) γεμίζουν αργότερα ενώ
    το table είναι ενεργό."""
    t = new_state()
    t["id"] = table_id
    t["name"] = name
    t["selected_cols"] = list(selected_cols)
    t["filters"] = [dict(f) for f in filters]
    return t


def is_snapshot(table: dict) -> bool:
    """True για table του Workshop: σταθερό αποτέλεσμα (result_df), όχι «συνταγή» που
    ξαναϋπολογίζεται από το dataset — δεν περνά ποτέ από το execute()."""
    return table.get("source") == WORKSHOP_SOURCE


def save_snapshot_table(container: dict, name: str, frame: pd.DataFrame) -> str | None:
    """
    save_table() του Workshop: αποθηκεύει το `frame` ως table-στιγμιότυπο στη λίστα tables
    του container. Ίδιο όνομα με παλιότερο table του Workshop -> το αντικαθιστά. Επιστρέφει
    None αν έγινε, αλλιώς το μήνυμα σφάλματος (όνομα table του Analysis, κενό όνομα, όριο).
    """
    name = str(name).strip()
    if not name:
        return "Δώσε όνομα για το table."
    if ANALYSIS_TABLE_NAME.fullmatch(name):
        return f"Τα ονόματα της μορφής «{ANALYSIS_TABLE_PREFIX} N» δίνονται αυτόματα στα tables του Analysis — διάλεξε άλλο όνομα."
    if not isinstance(frame, pd.DataFrame):
        return "Το save_table() δέχεται μόνο πίνακα (pandas DataFrame)."
    for table in container["tables"]:
        if table["name"] != name:
            continue
        if not is_snapshot(table):
            return f"Υπάρχει ήδη table του Analysis με όνομα '{name}' — διάλεξε άλλο όνομα."
        table["result_df"] = frame.copy()
        return None
    if len(container["tables"]) >= MAX_TABLES:
        return f"Έχεις ήδη {MAX_TABLES} tables (το μέγιστο) — διάγραψε ένα από το Analysis."
    table = new_table(table_id=container["next_num"], name=name, selected_cols=[], filters=[])
    table["source"] = WORKSHOP_SOURCE
    table["result_df"] = frame.copy()
    container["tables"].append(table)
    container["next_num"] += 1
    return None


def new_container_state() -> dict:
    """
    Κατάσταση όλης της Ενότητας 5 (Ομαδοποίηση & Ανάλυση) για ένα dataset.
    - "tables": έως MAX_TABLES ανεξάρτητα tables (δικές τους στήλες/WHERE), το
      καθένα με δική του συνέχεια Window Functions/ORDER BY/GROUP BY· εδώ μπαίνουν
      και τα tables-στιγμιότυπα του Workshop (βλ. save_snapshot_table).
    - "active_id": ποιο table είναι το "ενεργό" (πάνω σε αυτό δουλεύουν τα
      Steps 2-4). Η εναλλαγή ΔΕΝ διαγράφει/κάνει reset τα υπόλοιπα tables.
    - "builder_cols"/"builder_filters": προσωρινή επιλογή στηλών/WHERE για το
      ΕΠΟΜΕΝΟ table, πριν πατηθεί "Προσθήκη Table".
    - "next_num": αύξων μετρητής για αυτόματη ονομασία νέων tables· δεν
      ξαναχρησιμοποιείται μετά από διαγραφή, ώστε ονόματα/ids να μένουν μοναδικά.
    """
    return {
        "tables": [],
        "active_id": None,
        "builder_cols": [],
        "builder_filters": [],
        "next_num": 1,
    }


# ------------------------------------------------------------------ helpers

def get_column_operators(df: pd.DataFrame, col: str) -> list:
    dtype = df[col].dtype
    if pd.api.types.is_datetime64_any_dtype(dtype):
        return DATE_OPERATORS
    if pd.api.types.is_numeric_dtype(dtype):
        return NUMERIC_OPERATORS
    return TEXT_OPERATORS


def get_unique_values(df: pd.DataFrame, col: str):
    """Πραγματικές μοναδικές τιμές μιας στήλης, για dropdowns =, !=, IN σε
    κατηγορικές/text στήλες. None αν η στήλη έχει πάρα πολλές μοναδικές τιμές
    (το UI πέφτει τότε σε ελεύθερο text input)."""
    vals = df[col].dropna().unique().tolist()
    if len(vals) > MAX_UNIQUE_VALUES_FOR_DROPDOWN:
        return None
    return sorted(vals, key=lambda v: str(v))


def _quote_ident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def date_trunc_expr(col: str, granularity: str | None) -> str:
    """
    SQL έκφραση αναφοράς σε μια στήλη, με προαιρετική στρογγυλοποίηση ημερομηνίας/ώρας
    (GROUP BY ανά έτος/μήνα/ημέρα/ώρα/λεπτό) μέσω DATE_TRUNC. granularity=None -> απλή,
    ρητά quoted αναφορά στήλης. Το granularity ελέγχεται πάντα έναντι της λίστας
    DATE_GRANULARITIES (whitelist) πριν μπει στο SQL.
    """
    qcol = _quote_ident(col)
    if not granularity:
        return qcol
    part = str(granularity).upper()
    if part not in DATE_GRANULARITIES:
        raise ValueError(f"Μη έγκυρη ομαδοποίηση ημερομηνίας: '{granularity}'.")
    return f"DATE_TRUNC('{part.lower()}', {qcol})"


def validate_columns(df: pd.DataFrame, cols) -> None:
    for c in cols:
        if c and c not in df.columns:
            raise ValueError(f"Η στήλη '{c}' δεν υπάρχει στο τρέχον αποτέλεσμα.")


def validate_new_column_name(name: str, existing_names) -> None:
    """Ελέγχει το custom όνομα νέας στήλης (window function ή group-by alias):
    μη κενό, χωρίς εισαγωγικά (θα έσπαγαν το SQL), χωρίς σύγκρουση ονόματος."""
    if not name or not name.strip():
        raise ValueError("Το όνομα της νέας στήλης είναι υποχρεωτικό.")
    if '"' in name:
        raise ValueError("Το όνομα της νέας στήλης δεν επιτρέπεται να περιέχει διπλά εισαγωγικά (\").")
    if name in existing_names:
        raise ValueError(f"Η στήλη '{name}' υπάρχει ήδη — διάλεξε άλλο όνομα.")


def _parse_value(df: pd.DataFrame, col: str, raw):
    """Αν η τιμή είναι ήδη σε φυσικό τύπο (π.χ. από dropdown πραγματικών τιμών),
    περνάει ως έχει. Αν είναι string (ελεύθερο text input), μετατρέπεται ανάλογα
    με τον τύπο της στήλης."""
    if not isinstance(raw, str):
        return raw
    dtype = df[col].dtype
    if pd.api.types.is_numeric_dtype(dtype):
        try:
            v = float(raw)
            if pd.api.types.is_integer_dtype(dtype) and v.is_integer():
                return int(v)
            return v
        except (TypeError, ValueError):
            raise ValueError(f"Η τιμή '{raw}' δεν είναι έγκυρος αριθμός για τη στήλη '{col}'.")
    if pd.api.types.is_datetime64_any_dtype(dtype):
        try:
            return pd.to_datetime(raw)
        except Exception:
            raise ValueError(f"Η τιμή '{raw}' δεν είναι έγκυρη ημερομηνία για τη στήλη '{col}'.")
    return raw


# ------------------------------------------------------------------ Step 1: WHERE

def build_where(df: pd.DataFrame, filters: list):
    """Ασφαλές, parameterized WHERE. Επιστρέφει (sql_or_empty, params)."""
    if not filters:
        return "", []
    parts, params = [], []
    for i, f in enumerate(filters):
        col, op = f["col"], f["op"]
        validate_columns(df, [col])
        qcol = _quote_ident(col)

        if op == "BETWEEN":
            v1 = _parse_value(df, col, f.get("val"))
            v2 = _parse_value(df, col, f.get("val2"))
            clause = f"{qcol} BETWEEN ? AND ?"
            params.extend([v1, v2])
        elif op == "IN":
            raw_vals = f.get("val") or []
            if isinstance(raw_vals, str):
                raw_vals = [v.strip() for v in raw_vals.split(",") if v.strip()]
            if not raw_vals:
                raise ValueError(f"Η συνθήκη IN για τη στήλη '{col}' χρειάζεται τουλάχιστον μία τιμή.")
            values = [_parse_value(df, col, v) for v in raw_vals]
            clause = f"{qcol} IN ({', '.join(['?'] * len(values))})"
            params.extend(values)
        elif op == "CONTAINS":
            clause = f"{qcol} ILIKE ?"   # case-insensitive
            params.append(f"%{f.get('val', '')}%")
        elif op == "BEFORE":
            clause = f"{qcol} < ?"
            params.append(_parse_value(df, col, f.get("val")))
        elif op == "AFTER":
            clause = f"{qcol} > ?"
            params.append(_parse_value(df, col, f.get("val")))
        elif op in ("=", "!=", ">", ">=", "<", "<="):
            clause = f"{qcol} {op} ?"
            params.append(_parse_value(df, col, f.get("val")))
        else:
            raise ValueError(f"Μη υποστηριζόμενος τελεστής: '{op}'.")

        parts.append(clause if i == 0 else f"{f.get('combine', 'AND')} {clause}")
    return "WHERE " + " ".join(parts), params


# ------------------------------------------------------------------ Step 2: Window functions

def _agg_expr(func: str, col) -> str:
    qcol = _quote_ident(col)
    return f"COUNT({qcol})" if func == "COUNT" else f"{func}({qcol})"


def build_order_by_sql(order_by_levels, valid_cols) -> str:
    """
    Χτίζει το SQL κομμάτι (χωρίς το 'ORDER BY') για έως MAX_ORDER_BY_LEVELS επίπεδα
    ταξινόμησης, με τη σειρά που δόθηκαν — το καθένα λειτουργεί ΜΕΣΑ στο προηγούμενο
    (standard SQL multi-column ORDER BY). Επίπεδα χωρίς επιλεγμένη στήλη, ή με στήλη
    που δεν υπάρχει (πλέον) στο valid_cols, παραλείπονται σιωπηλά.
    """
    parts = []
    for ob in order_by_levels or []:
        col = ob.get("col")
        if col and col in valid_cols:
            direction = "DESC" if ob.get("dir") == "DESC" else "ASC"
            parts.append(f"{_quote_ident(col)} {direction}")
    return ", ".join(parts)


def build_window_function_sql(wf: dict) -> str:
    """Επιστρέφει το SQL κομμάτι: {AGG}(\"col\") OVER ([PARTITION BY ...] [ORDER BY ...]) AS \"name\".
    Αν wf['partition_date_part'] είναι ορισμένο (YEAR/MONTH/DAY/HOUR/MINUTE), το PARTITION BY
    γίνεται πάνω στη στρογγυλοποιημένη ημερομηνία/ώρα (DATE_TRUNC), όχι στην ακριβή τιμή."""
    over_parts = []
    if wf.get("partition_col"):
        over_parts.append(f"PARTITION BY {date_trunc_expr(wf['partition_col'], wf.get('partition_date_part'))}")
    if wf.get("order_col"):
        direction = "DESC" if wf.get("order_dir") == "DESC" else "ASC"
        over_parts.append(f"ORDER BY {_quote_ident(wf['order_col'])} {direction}")
    over_clause = " ".join(over_parts)
    expr = _agg_expr(wf["agg_func"], wf["target_col"])
    return f'{expr} OVER ({over_clause}) AS {_quote_ident(wf["new_name"])}'


def group_by_alias(group_by: dict) -> str:
    """Όνομα της στήλης-αποτελέσματος του GROUP BY, π.χ. 'avg_Price'. Αν συμπίπτει με τη
    στήλη ομαδοποίησης, προστίθεται '_agg' ώστε οι δύο στήλες να μη συγκρούονται."""
    alias = f"{group_by['func'].lower()}_{group_by['value_col']}"
    while alias == group_by["group_col"]:
        alias += "_agg"
    return alias


# ------------------------------------------------------------------ Ενιαία εκτέλεση

def execute(df: pd.DataFrame, state: dict) -> dict:
    """
    Εκτελεί WHERE -> window functions (διαδοχικά) -> [GROUP BY] -> τελικό
    ORDER BY, όλα ως SQL μέσω DuckDB πάνω σε διαδοχικά υλοποιημένα (materialized)
    ενδιάμεσα αποτελέσματα. Ενημερώνει IN-PLACE τα result_df/result_message/error.
    """
    state["error"] = None
    state["result_message"] = None
    state["result_df"] = None
    try:
        con = duckdb.connect(database=":memory:")

        base_cols = state["selected_cols"] or df.columns.tolist()
        validate_columns(df, base_cols)
        base = df[base_cols] if state["selected_cols"] else df

        where_sql, params = build_where(base, state["filters"])
        con.register("t_src", base)
        current = con.execute(f"SELECT * FROM t_src{(' ' + where_sql) if where_sql else ''}", params).fetchdf()

        if current.empty:
            state["result_df"] = current
            state["result_message"] = "Δεν βρέθηκαν εγγραφές με αυτά τα φίλτρα."
            return state

        null_notes = []
        existing_names = set(current.columns)
        for i, wf in enumerate(state["window_functions"]):
            validate_columns(current, [wf["target_col"]])
            if wf.get("partition_col"):
                validate_columns(current, [wf["partition_col"]])
            if wf.get("order_col"):
                validate_columns(current, [wf["order_col"]])
            if wf["agg_func"] in NUMERIC_REQUIRED_FUNCS and not pd.api.types.is_numeric_dtype(current[wf["target_col"]].dtype):
                raise ValueError(
                    f"Η στήλη '{wf['target_col']}' δεν είναι αριθμητική — το {wf['agg_func']} χρειάζεται αριθμητική στήλη."
                )
            # Defensive επανέλεγχος σύγκρουσης ονόματος (η UI το ελέγχει ήδη πριν την
            # προσθήκη, αλλά το DuckDB/pandas ΔΕΝ σφάλει σε διπλό όνομα — απλώς το
            # μετονομάζει σιωπηλά σε "name_1", κάτι που η εκφώνηση ρητά απαγορεύει).
            validate_new_column_name(wf["new_name"], existing_names)
            n_null = int(current[wf["target_col"]].isna().sum())
            if n_null > 0:
                null_notes.append(f"'{wf['target_col']}' (window: {n_null})")

            # partition_date_part εφαρμόζεται μόνο αν η partition_col είναι ΠΡΑΓΜΑΤΙΚΑ
            # ημερομηνία/ώρα αυτή τη στιγμή (defensive re-check, χωρίς να πειράζει το
            # αποθηκευμένο state — π.χ. αν ο χρήστης άλλαξε στήλη-στόχο ανάμεσα σε renders).
            effective_wf = wf
            if wf.get("partition_date_part"):
                is_date_partition = wf.get("partition_col") and pd.api.types.is_datetime64_any_dtype(
                    current[wf["partition_col"]].dtype
                )
                if not is_date_partition:
                    effective_wf = {**wf, "partition_date_part": None}

            con2 = duckdb.connect(database=":memory:")
            con2.register("t_cur", current)
            expr = build_window_function_sql(effective_wf)
            current = con2.execute(f"SELECT *, {expr} FROM t_cur").fetchdf()
            existing_names.add(wf["new_name"])

        group_by = state.get("group_by")
        if group_by and group_by.get("group_col") and group_by.get("value_col"):
            validate_columns(current, [group_by["group_col"], group_by["value_col"]])
            func = group_by["func"]
            if func in NUMERIC_REQUIRED_FUNCS and not pd.api.types.is_numeric_dtype(current[group_by["value_col"]].dtype):
                raise ValueError(
                    f"Η στήλη '{group_by['value_col']}' δεν είναι αριθμητική — το {func} χρειάζεται αριθμητική στήλη."
                )
            n_null = int(current[group_by["value_col"]].isna().sum())
            if n_null > 0:
                null_notes.append(f"'{group_by['value_col']}' (group by: {n_null})")

            alias = group_by_alias(group_by)
            date_part = group_by.get("date_part") if pd.api.types.is_datetime64_any_dtype(current[group_by["group_col"]].dtype) else None
            group_expr = date_trunc_expr(group_by["group_col"], date_part)
            sql = (
                f'SELECT {group_expr} AS {_quote_ident(group_by["group_col"])}, '
                f'{_agg_expr(func, group_by["value_col"])} AS {_quote_ident(alias)} '
                f'FROM t_grp GROUP BY {group_expr}'
            )
            order_sql = build_order_by_sql(state.get("final_order_by"), {group_by["group_col"], alias})
            if order_sql:
                sql += f' ORDER BY {order_sql}'
            con3 = duckdb.connect(database=":memory:")
            con3.register("t_grp", current)
            current = con3.execute(sql).fetchdf()
        else:
            order_sql = build_order_by_sql(state.get("final_order_by"), set(current.columns))
            if order_sql:
                con4 = duckdb.connect(database=":memory:")
                con4.register("t_ord", current)
                current = con4.execute(f'SELECT * FROM t_ord ORDER BY {order_sql}').fetchdf()

        state["result_df"] = current.reset_index(drop=True)
        if null_notes:
            state["result_message"] = "Εξαιρέθηκαν από τον υπολογισμό γραμμές με NULL: " + ", ".join(null_notes) + "."
    except Exception as e:
        state["error"] = str(e)
        state["result_df"] = None
    return state
