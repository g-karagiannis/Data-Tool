"""
Αρχεία σταθερού πλάτους (.dat): κάθε γραμμή είναι μια εγγραφή και κάθε στήλη βρίσκεται
σε σταθερές θέσεις χαρακτήρων, που δίνει το codebook (π.χ. "AGE24X 192-193"). Οι θέσεις
μετρούν από το 1 και περιλαμβάνουν και τα δύο άκρα. Καμία εξάρτηση από Streamlit.

Κάθε τιμή είναι ακριβώς οι χαρακτήρες της θέσης της, χωρίς τα κενά στις άκρες· κενό πεδίο
γίνεται κενή τιμή (NA). Η μετατροπή σε αριθμό γίνεται μόνο όταν ΟΛΕΣ οι τιμές είναι αριθμοί —
αλλιώς η στήλη δεν φορτώνεται και ο χρήστης βλέπει ποια τιμή φταίει.
"""
import operator

import pandas as pd

TYPE_AUTO = "Αυτόματο"
TYPE_NUMBER = "Αριθμός"
TYPE_TEXT = "Κείμενο"
TYPES = (TYPE_AUTO, TYPE_NUMBER, TYPE_TEXT)
SPEC_COLUMNS = ("Όνομα", "Από", "Έως", "Τύπος")


def decode(raw_bytes: bytes) -> str:
    """Κείμενο του αρχείου: utf-8, αλλιώς ελληνικά cp1253, αλλιώς latin1 (που δεν αποτυγχάνει ποτέ)."""
    for encoding in ("utf-8", "cp1253"):
        try:
            return raw_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw_bytes.decode("latin1")


def split_lines(text: str) -> list:
    """Οι γραμμές του αρχείου (CRLF ή LF), χωρίς κενές γραμμές στο τέλος."""
    lines = text.splitlines()
    while lines and not lines[-1].strip():
        lines.pop()
    return lines


def empty_spec() -> pd.DataFrame:
    """Κενός πίνακας θέσεων (Όνομα, Από, Έως, Τύπος)."""
    return pd.DataFrame({
        "Όνομα": pd.Series(dtype="object"),
        "Από": pd.Series(dtype="Int64"),
        "Έως": pd.Series(dtype="Int64"),
        "Τύπος": pd.Series(dtype="object"),
    })


def _whole_number(value):
    """Ακέραιος ≥ 1 από κελί του πίνακα, ή None."""
    if pd.isna(value):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return int(number) if number.is_integer() and number >= 1 else None


def clean_spec(spec_df: pd.DataFrame, line_length: int):
    """Ελέγχει τον πίνακα θέσεων. Επιστρέφει (στήλες, λάθη): στήλες = [{"name", "start",
    "end", "type"}], με τη σειρά του πίνακα· λάθη = μηνύματα για τον χρήστη. Εντελώς κενές
    γραμμές του πίνακα αγνοούνται."""
    columns, errors, seen = [], [], set()
    for row_number, row in enumerate(spec_df.itertuples(index=False), start=1):
        name, start, end, kind = (row[i] for i in range(4))
        name = "" if pd.isna(name) else str(name).strip()
        if not name and pd.isna(start) and pd.isna(end):
            continue
        where = f"Γραμμή {row_number}" + (f" ({name})" if name else "")
        start_n, end_n = _whole_number(start), _whole_number(end)
        if not name:
            errors.append(f"{where}: λείπει το όνομα.")
        elif name in seen:
            errors.append(f"{where}: το όνομα υπάρχει ήδη.")
        if start_n is None or end_n is None:
            errors.append(f"{where}: «Από» και «Έως» πρέπει να είναι ακέραιοι από 1 και πάνω.")
        elif start_n > end_n:
            errors.append(f"{where}: το «Από» ({start_n}) είναι μετά το «Έως» ({end_n}).")
        elif end_n > line_length:
            errors.append(f"{where}: το «Έως» ({end_n}) ξεπερνά το μήκος της γραμμής ({line_length}).")
        seen.add(name)
        kind = TYPE_AUTO if pd.isna(kind) or kind not in TYPES else kind
        columns.append({"name": name, "start": start_n, "end": end_n, "type": kind})
    return columns, errors


def cut_columns(lines: list, columns: list) -> pd.DataFrame:
    """Κόβει κάθε στήλη στις θέσεις της, ως κείμενο. Κενό πεδίο -> NA."""
    series = pd.Series(lines, dtype="object")
    data = {}
    for col in columns:
        values = series.str.slice(col["start"] - 1, col["end"]).str.strip()
        data[col["name"]] = values.mask(values == "")
    return pd.DataFrame(data)


def _as_numbers(values: pd.Series):
    """(αριθμοί, πρώτη τιμή που δεν είναι αριθμός ή None)."""
    numbers = pd.to_numeric(values, errors="coerce")
    bad = values[numbers.isna() & values.notna()]
    return numbers, (None if bad.empty else bad.iloc[0])


def apply_types(text_df: pd.DataFrame, columns: list):
    """Μετατρέπει τις στήλες στον τύπο τους. «Αυτόματο»: αριθμός αν όλες οι τιμές είναι
    αριθμοί, αλλιώς κείμενο. Επιστρέφει (DataFrame, {στήλη: τελικός τύπος}, λάθη)."""
    result, chosen, errors = text_df.copy(), {}, []
    for col in columns:
        name, kind = col["name"], col["type"]
        if kind == TYPE_TEXT:
            chosen[name] = TYPE_TEXT
            continue
        numbers, bad = _as_numbers(text_df[name])
        if bad is None and text_df[name].notna().any():
            result[name] = numbers
            chosen[name] = TYPE_NUMBER
        elif kind == TYPE_NUMBER:
            if bad is not None:
                errors.append(f"Η στήλη {name} έχει τιμές που δεν είναι αριθμοί (π.χ. «{bad}») — "
                              f"διάλεξε «{TYPE_TEXT}» ή έλεγξε τις θέσεις.")
            else:
                result[name] = numbers   # μόνο κενές τιμές
                chosen[name] = TYPE_NUMBER
        else:
            chosen[name] = TYPE_TEXT
    return result, chosen, errors


# ---------------------------------------------------------------- φίλτρο γραμμών

OPERATORS = ("=", "≠", ">", "≥", "<", "≤")
ORDER_OPERATORS = (">", "≥", "<", "≤")
FILTER_COLUMNS = ("Στήλη", "Τελεστής", "Τιμή")
_COMPARE = {
    "=": operator.eq, "≠": operator.ne, ">": operator.gt, "≥": operator.ge, "<": operator.lt, "≤": operator.le,
}


def empty_filters() -> pd.DataFrame:
    """Κενός πίνακας κανόνων γραμμών (Στήλη, Τελεστής, Τιμή)."""
    return pd.DataFrame({name: pd.Series(dtype="object") for name in FILTER_COLUMNS})


def clean_filters(filter_df: pd.DataFrame, chosen: dict):
    """Ελέγχει τους κανόνες γραμμών. chosen: {στήλη: τύπος} του αποτελέσματος (από το
    apply_types). Επιστρέφει (κανόνες, λάθη)· κανόνας = {"column", "op", "value"} με την τιμή
    ήδη αριθμό για στήλες «Αριθμός». Εντελώς κενές γραμμές του πίνακα αγνοούνται."""
    rules, errors = [], []
    for row_number, row in enumerate(filter_df.itertuples(index=False), start=1):
        column, op, value = (None if pd.isna(v) else str(v).strip() for v in row[:3])
        if not column and not op and not value:
            continue
        where = f"Φίλτρο {row_number}"
        if column not in chosen:
            errors.append(f"{where}: διάλεξε μία από τις στήλες που φορτώνονται.")
            continue
        if op not in OPERATORS:
            errors.append(f"{where}: διάλεξε τελεστή ({' '.join(OPERATORS)}).")
            continue
        if not value:
            errors.append(f"{where}: λείπει η τιμή.")
            continue
        if chosen[column] == TYPE_NUMBER:
            try:
                value = float(value.replace(",", "."))
            except ValueError:
                errors.append(f"{where}: η {column} είναι αριθμός, ενώ η τιμή «{value}» δεν είναι.")
                continue
        elif op in ORDER_OPERATORS:
            errors.append(f"{where}: ο τελεστής {op} ισχύει μόνο για στήλες «{TYPE_NUMBER}» — η {column} είναι "
                          f"«{TYPE_TEXT}».")
            continue
        rules.append({"column": column, "op": op, "value": value})
    return rules, errors


def apply_filters(df: pd.DataFrame, rules: list) -> pd.DataFrame:
    """Κρατά τις γραμμές που περνούν ΟΛΟΥΣ τους κανόνες. Κενή τιμή δεν περνά κανέναν κανόνα
    (ούτε το ≠), όπως στην SQL."""
    keep = pd.Series(True, index=df.index)
    for rule in rules:
        values = df[rule["column"]]
        present = values.notna()
        compare = _COMPARE[rule["op"]](values[present], rule["value"])
        keep &= present & compare.reindex(df.index, fill_value=False)
    return df[keep].reset_index(drop=True)
