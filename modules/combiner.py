"""
Συνδυασμός πολλαπλών datasets μέσω Join ή Set Operator.
Καλύπτει: validation τύπων join key, validation συμβατότητας για set operators,
join βήμα-βήμα (apply_join_step, για Chain και για Hub-and-Spoke),
set operators μέσω DuckDB, και τη σύμβαση ονομασίας του συνδυασμένου dataset.
"""
import os
import pandas as pd
import duckdb


JOIN_TECHNIQUES = ["Inner", "Left", "Right", "Full", "Cross"]
SET_OPERATORS = ["Union", "Union All", "Intersect", "Except"]

_JOIN_HOW = {"Inner": "inner", "Left": "left", "Right": "right", "Full": "outer", "Cross": "cross"}
_SET_OP_SQL = {"Union": "UNION", "Union All": "UNION ALL", "Intersect": "INTERSECT", "Except": "EXCEPT"}


def _dtype_group(dtype) -> str:
    """Ομαδοποιεί dtypes σε ευρύτερες, φιλικές προς τον χρήστη κατηγορίες
    (π.χ. int64/float64 -> 'numeric') ώστε ένα απλό NaN να μην μπλοκάρει ένα join."""
    kind = dtype.kind
    if kind in "iuf":
        return "numeric"
    if kind == "b":
        return "bool"
    if kind == "M":
        return "datetime"
    return "text"


def strip_extension(filename: str) -> str:
    return os.path.splitext(filename)[0]


def validate_join_key_types(df_left: pd.DataFrame, key_left: str, df_right: pd.DataFrame, key_right: str):
    """Επιστρέφει (True, None) αν οι δύο στήλες-κλειδιά έχουν ΑΚΡΙΒΩΣ τον ίδιο τύπο δεδομένων
    (exact dtype match, π.χ. int64 vs float64 ΔΕΝ περνάει), αλλιώς (False, μήνυμα λάθους)."""
    t_left, t_right = df_left[key_left].dtype, df_right[key_right].dtype
    if t_left != t_right:
        return False, (
            f"Ασύμβατοι τύποι δεδομένων στο join key: η στήλη '{key_left}' είναι τύπου {t_left} "
            f"ενώ η στήλη '{key_right}' είναι τύπου {t_right}. Διάλεξε στήλες-κλειδιά με ΑΚΡΙΒΩΣ τον ίδιο τύπο."
        )
    return True, None


def apply_join(df_left: pd.DataFrame, key_left: str, df_right: pd.DataFrame, key_right: str,
               technique: str, left_label, right_label) -> pd.DataFrame:
    """Απλό join δύο πινάκων (χωρίς origin-tracking — χρησιμοποιείται μόνο στην περίπτωση 2 αρχείων)."""
    how = _JOIN_HOW[technique]
    suffixes = (f" (table {left_label})", f" (table {right_label})")
    if how == "cross":
        return df_left.merge(df_right, how="cross", suffixes=suffixes)
    return df_left.merge(df_right, left_on=key_left, right_on=key_right, how=how, suffixes=suffixes)


def apply_join_step(current_df, origin, right_df, right_table_num, key_left, key_right, technique):
    """
    Εφαρμόζει ΕΝΑ μόνο join step πάνω στο συσσωρευμένο αποτέλεσμα, διατηρώντας για κάθε
    στήλη τον αριθμό του table από το οποίο ΠΡΑΓΜΑΤΙΚΑ προήλθε (origin tracking) — ώστε
    τα ονόματα "(table N)" να παραμένουν σωστά ακόμα κι αν μια στήλη συγκρουστεί σε
    ΕΠΟΜΕΝΟ βήμα με μια νέα στήλη (και όχι μόνο στο πρώτο βήμα).

    current_df/origin: το τρέχον συσσωρευμένο αποτέλεσμα και το {όνομα στήλης: table}.
    right_df/right_table_num: το επόμενο table που μπαίνει στην αλυσίδα.
    key_left: στήλη-κλειδί από τις (πιθανώς ήδη μετονομασμένες) στήλες του current_df.
    key_right: στήλη-κλειδί από τις (πρωτότυπες) στήλες του right_df.

    Επιστρέφει (merged_df, new_origin).
    """
    how = _JOIN_HOW[technique]

    colliding = set(current_df.columns) & set(right_df.columns)
    if key_left == key_right:
        colliding.discard(key_left)  # θα ενοποιηθεί αυτόματα από το pandas merge σε μία στήλη

    rename_left = {c: f"{c} (table {origin[c]})" for c in colliding}
    rename_right = {c: f"{c} (table {right_table_num})" for c in colliding}

    left_r = current_df.rename(columns=rename_left)
    right_r = right_df.rename(columns=rename_right)
    kl = rename_left.get(key_left, key_left)
    kr = rename_right.get(key_right, key_right)

    if how == "cross":
        merged = left_r.merge(right_r, how="cross")
    else:
        merged = left_r.merge(right_r, left_on=kl, right_on=kr, how=how)

    inv_rename_left = {v: k for k, v in rename_left.items()}
    inv_rename_right = {v: k for k, v in rename_right.items()}
    new_origin = {}
    for c in merged.columns:
        if c in inv_rename_left:
            new_origin[c] = origin[inv_rename_left[c]]
        elif c in origin:
            new_origin[c] = origin[c]
        elif c in inv_rename_right:
            new_origin[c] = right_table_num
        else:
            new_origin[c] = right_table_num
    return merged, new_origin


def validate_set_operator_compatibility(dfs, names):
    """
    Ελέγχει ότι όλα τα datasets έχουν τον ίδιο αριθμό στηλών, τα ΙΔΙΑ ονόματα στηλών
    (matching by name) και συμβατούς τύπους ανά αντίστοιχη στήλη (ίδιο όνομα).
    Επιστρέφει (True, None) ή (False, μήνυμα λάθους).
    """
    ref_cols = list(dfs[0].columns)
    for name, df in zip(names[1:], dfs[1:]):
        if len(df.columns) != len(ref_cols):
            return False, (
                f"Το '{name}' έχει {len(df.columns)} στήλες ενώ το '{names[0]}' έχει {len(ref_cols)} στήλες. "
                "Όλα τα datasets πρέπει να έχουν τον ίδιο αριθμό στηλών."
            )
        missing = set(ref_cols) - set(df.columns)
        extra = set(df.columns) - set(ref_cols)
        if missing or extra:
            return False, (
                f"Το '{name}' έχει διαφορετικά ονόματα στηλών από το '{names[0]}'. "
                f"Λείπουν: {sorted(missing) if missing else '-'} | Επιπλέον: {sorted(extra) if extra else '-'}."
            )
    for col in ref_cols:
        base_dtype = dfs[0][col].dtype
        base_group = _dtype_group(base_dtype)
        for name, df in zip(names[1:], dfs[1:]):
            g = _dtype_group(df[col].dtype)
            if g != base_group:
                return False, (
                    f"Η στήλη '{col}' έχει ασύμβατο τύπο δεδομένων: {base_dtype} στο '{names[0]}' "
                    f"έναντι {df[col].dtype} στο '{name}'."
                )
    return True, None


def apply_set_operator(dfs, technique: str) -> pd.DataFrame:
    """Εφαρμόζει το set operator διαδοχικά σε όλα τα datasets (Α op Β op Γ ... — matching by name)."""
    ref_cols = list(dfs[0].columns)
    op_sql = _SET_OP_SQL[technique]
    con = duckdb.connect(database=":memory:")
    select_parts = []
    for i, df in enumerate(dfs):
        table = f"t{i}"
        con.register(table, df[ref_cols])
        select_parts.append(f"SELECT * FROM {table}")
    sql = f" {op_sql} ".join(select_parts)
    return con.execute(sql).fetchdf()


def build_combined_label(base_names, technique_or_structure: str, is_structure: bool = False) -> str:
    """
    base_names: λίστα ονομάτων αρχείων ΧΩΡΙΣ επέκταση, με τη σειρά της ετικέτας.
    technique_or_structure: π.χ. 'Inner', 'Union All', 'Chain', 'Hub-and-Spoke'.
    is_structure: True μόνο για Join δομή 3+ αρχείων (Chain/Hub-and-Spoke) —
    τότε διατηρείται όπως δόθηκε (π.χ. 'Chain'), αλλιώς γίνεται lowercase_με_underscore.
    """
    prefix = technique_or_structure if is_structure else technique_or_structure.lower().replace(" ", "_")
    return f"{prefix}_" + "_".join(base_names) + ".csv"
