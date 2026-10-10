"""
Λογική για την καρτέλα "Pipeline": Update/Where/Set, type casting, και
ανίχνευση Missing Values / Duplicates / Outliers ("quarantine" πίνακες).

Θεμελιώδης αρχή: όλες οι συναρτήσεις ανίχνευσης (detect_*) είναι ΚΑΘΑΡΕΣ —
υπολογίζουν τα quarantine tables ΦΡΕΣΚΑ από το τρέχον DataFrame κάθε φορά,
διατηρώντας το pandas index του. Έτσι το dataset και οι 3 πίνακες παραμένουν
πάντα συνεπή μεταξύ τους χωρίς να χρειάζεται χειροκίνητος συγχρονισμός: αρκεί
να μεταβληθεί το ένα κοινό DataFrame και να ξανακληθούν οι detect_* συναρτήσεις.
"""
import ast
import operator
import re
import pandas as pd
_CURRENCY_CHARS = "€$£¥"
_CMP_OPS_ORDERED = ["!=", ">=", "<=", ">", "<", "="]   # σειρά σημαντική: 2-char πριν 1-char
_ARITH_PREFIX_OPS = {"+": operator.add, "-": operator.sub, "*": operator.mul, "/": operator.truediv}
_ALLOWED_BINOPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}
_ALLOWED_UNARYOPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}


# ------------------------------------------------------------------ helpers

def _parse_value_for_column(series: pd.Series, raw_value: str):
    """Προσπαθεί να μετατρέψει ένα string σε τύπο συμβατό με τη στήλη (για WHERE/SET)."""
    dtype = series.dtype
    if pd.api.types.is_bool_dtype(dtype):
        low = str(raw_value).strip().lower()
        if low in ("true", "1", "yes", "ναι"):
            return True
        if low in ("false", "0", "no", "όχι"):
            return False
        return raw_value
    if pd.api.types.is_numeric_dtype(dtype):
        try:
            v = float(raw_value)
            if pd.api.types.is_integer_dtype(dtype) and v.is_integer():
                return int(v)
            return v
        except (TypeError, ValueError):
            return raw_value
    if pd.api.types.is_datetime64_any_dtype(dtype):
        try:
            return pd.to_datetime(raw_value)
        except Exception:
            return raw_value
    return raw_value


def _parse_value_strict(series: pd.Series, raw_value: str):
    """Ίδιο με _parse_value_for_column αλλά ΡΙΧΝΕΙ ValueError αν η τιμή δεν
    ταιριάζει με τον τύπο της στήλης — χρησιμοποιείται στο WHERE parser όπου
    θέλουμε σαφές μήνυμα σφάλματος αντί για σιωπηλή, πιθανώς λάθος, εναλλακτική."""
    dtype = series.dtype
    name = series.name
    if pd.api.types.is_bool_dtype(dtype):
        low = str(raw_value).strip().lower()
        if low in ("true", "1", "yes", "ναι"):
            return True
        if low in ("false", "0", "no", "όχι"):
            return False
        raise ValueError(f"Η τιμή '{raw_value}' δεν είναι έγκυρη λογική (boolean) τιμή για τη στήλη '{name}'.")
    if pd.api.types.is_numeric_dtype(dtype):
        try:
            v = float(raw_value)
        except (TypeError, ValueError):
            raise ValueError(f"Η τιμή '{raw_value}' δεν είναι έγκυρος αριθμός για τη στήλη '{name}'.")
        if pd.api.types.is_integer_dtype(dtype) and v.is_integer():
            return int(v)
        return v
    if pd.api.types.is_datetime64_any_dtype(dtype):
        try:
            return pd.to_datetime(raw_value)
        except Exception:
            raise ValueError(f"Η τιμή '{raw_value}' δεν είναι έγκυρη ημερομηνία για τη στήλη '{name}'.")
    return raw_value


def _parse_atomic_where(series: pd.Series, text: str) -> pd.Series:
    """Ένας μόνος όρος WHERE: BETWEEN x AND y, ένας τελεστής σύγκρισης (=,!=,>,<,>=,<=),
    ή — αν δεν αναγνωριστεί τελεστής — implicit equality (literal τιμή)."""
    text = text.strip()

    m = re.match(r"(?i)^BETWEEN\s+(.+?)\s+AND\s+(.+)$", text)
    if m:
        lo = _parse_value_strict(series, m.group(1).strip())
        hi = _parse_value_strict(series, m.group(2).strip())
        try:
            return (series >= lo) & (series <= hi)
        except TypeError as e:
            raise ValueError(f"Μη έγκυρη σύγκριση BETWEEN στη στήλη '{series.name}': {e}")
    if re.match(r"(?i)^BETWEEN\b", text):
        raise ValueError(f"Μη έγκυρη σύνταξη BETWEEN: '{text}' (αναμένεται 'BETWEEN x AND y').")

    for op in _CMP_OPS_ORDERED:
        if text.startswith(op):
            raw_val = text[len(op):].strip()
            if not raw_val:
                raise ValueError(f"Λείπει η τιμή μετά τον τελεστή '{op}'.")
            val = _parse_value_strict(series, raw_val)
            try:
                if op == "!=":
                    return series != val
                if op == ">=":
                    return series >= val
                if op == "<=":
                    return series <= val
                if op == ">":
                    return series > val
                if op == "<":
                    return series < val
                return series == val
            except TypeError as e:
                raise ValueError(f"Μη έγκυρη σύγκριση '{op}' στη στήλη '{series.name}': {e}")

    # καμία λέξη-κλειδί/τελεστής -> implicit equality (literal τιμή)
    val = _parse_value_strict(series, text)
    return series == val


def parse_where_condition(series: pd.Series, raw_text: str) -> pd.Series:
    """
    Ασφαλής (χωρίς eval()) parser για την ενότητα WHERE. Υποστηρίζει:
    =, !=, >, <, >=, <=, BETWEEN x AND y, και AND/OR για συνδυασμό δύο όρων
    στην ΙΔΙΑ στήλη. Χωρίς αναγνωρίσιμο τελεστή -> implicit equality.
    Ρίχνει ValueError με σαφές μήνυμα σε μη έγκυρη σύνταξη — ποτέ crash σιωπηλά.
    """
    text = (raw_text or "").strip()
    if not text:
        raise ValueError("Η συνθήκη WHERE είναι κενή.")

    if re.match(r"(?i)^BETWEEN\b", text):
        return _parse_atomic_where(series, text)

    m = re.match(r"(?i)^(.+?)\s+(AND|OR)\s+(.+)$", text)
    if m:
        left, combiner, right = m.group(1).strip(), m.group(2).upper(), m.group(3).strip()
        left_mask = _parse_atomic_where(series, left)
        right_mask = _parse_atomic_where(series, right)
        return (left_mask & right_mask) if combiner == "AND" else (left_mask | right_mask)

    return _parse_atomic_where(series, text)


def _tokenize_bracket_refs(expr_text: str, df: pd.DataFrame):
    """Αντικαθιστά [Όνομα Στήλης] με ασφαλή placeholders (έγκυρα Python identifiers).
    Επιστρέφει (νέο κείμενο, {placeholder: pandas.Series}). Ρίχνει ValueError αν η
    στήλη δεν υπάρχει ή δεν είναι αριθμητικού τύπου."""
    mapping: dict = {}

    def repl(m):
        col_name = m.group(1).strip()
        if col_name not in df.columns:
            raise ValueError(f"Η στήλη '{col_name}' δεν υπάρχει.")
        if not pd.api.types.is_numeric_dtype(df[col_name]):
            raise ValueError(f"Η στήλη '{col_name}' δεν είναι αριθμητικού τύπου.")
        placeholder = f"__col{len(mapping)}__"
        mapping[placeholder] = df[col_name]
        return placeholder

    new_text = re.sub(r"\[([^\[\]]+)\]", repl, expr_text)
    return new_text, mapping


def _eval_safe_ast(node, columns: dict):
    """Αναδρομικός evaluator για μια ΗΔΗ επιβεβαιωμένη-ασφαλή AST έκφραση
    (μόνο +,-,*,/, παρενθέσεις, αριθμητικές σταθερές, και ονόματα-placeholder
    στηλών) — ΟΧΙ eval()/exec(), κανένα άλλο node type δεν γίνεται δεκτό."""
    if isinstance(node, ast.Expression):
        return _eval_safe_ast(node.body, columns)
    if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_BINOPS:
        left = _eval_safe_ast(node.left, columns)
        right = _eval_safe_ast(node.right, columns)
        return _ALLOWED_BINOPS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_UNARYOPS:
        return _ALLOWED_UNARYOPS[type(node.op)](_eval_safe_ast(node.operand, columns))
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.Name) and node.id in columns:
        return columns[node.id]
    raise ValueError("Μη υποστηριζόμενη σύνταξη στην αριθμητική έκφραση.")


def parse_arithmetic_expression(expr_text: str, df: pd.DataFrame):
    """
    Ασφαλής (χωρίς eval()) parser αριθμητικών εκφράσεων για την ενότητα SET:
    +, -, *, /, παρενθέσεις, και αναφορές σε άλλες στήλες μέσω [Όνομα Στήλης].
    Επιστρέφει pandas Series ή αριθμητικό scalar. Ρίχνει ValueError σε μη
    αναγνωρίσιμη σύνταξη ή μη αριθμητική στήλη αναφοράς.
    """
    text, col_map = _tokenize_bracket_refs(expr_text, df)
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError:
        raise ValueError(f"Μη έγκυρη σύνταξη έκφρασης: '{expr_text}'")
    return _eval_safe_ast(tree, col_map)


def clean_numeric_string(s):
    """
    Αφαιρεί σύμβολα νομίσματος και κανονικοποιεί διαχωριστικά χιλιάδων/δεκαδικών
    πριν από cast σε int/float. Χειρίζεται EU (1.234,56) και US (1,234.56) format
    με απλή ευρετική λογική βάσει θέσης τελείας/κόμματος.
    """
    if not isinstance(s, str):
        return s
    s = s.strip()
    for ch in _CURRENCY_CHARS:
        s = s.replace(ch, "")
    s = re.sub(r"[^\d,.\-+]", "", s).strip()
    if not s:
        return None

    has_comma, has_dot = "," in s, "." in s
    if has_comma and has_dot:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")   # EU: 1.234,56
        else:
            s = s.replace(",", "")                       # US: 1,234.56
    elif has_comma and not has_dot:
        parts = s.split(",")
        if len(parts) == 2 and len(parts[1]) in (1, 2):
            s = s.replace(",", ".")                       # EU decimal: 12,5
        else:
            s = s.replace(",", "")                        # thousands: 1,234
    return s


# ------------------------------------------------------------------ Ενότητα 1: Update/Where/Set

def apply_update_set(df, where_col, where_is_null, where_text, set_col, set_is_null, set_text):
    """
    UPDATE df SET set_col = <έκφραση/τιμή> WHERE where_col <συνθήκη> (ή IS NULL).
    where_text: ελεύθερο κείμενο — βλ. parse_where_condition (=, !=, >, <, >=, <=,
    BETWEEN x AND y, AND/OR, ή implicit equality χωρίς τελεστή).
    set_text: ελεύθερο κείμενο — αν ξεκινά με + - * / εφαρμόζεται πάνω στην
    ΤΡΕΧΟΥΣΑ τιμή της στήλης-στόχου (πράξη· βλ. parse_arithmetic_expression για
    αναφορές [Άλλη Στήλη]), αλλιώς αντιμετωπίζεται ως σταθερή τιμή.
    Ρίχνει ValueError με σαφές μήνυμα σε μη έγκυρη σύνταξη. Επιστρέφει
    (νέο DataFrame, πλήθος γραμμών που επηρεάστηκαν).
    """
    out = df.copy()

    if where_is_null:
        mask = out[where_col].isna()
    else:
        mask = parse_where_condition(out[where_col], where_text)

    if set_is_null:
        null_val = pd.NaT if pd.api.types.is_datetime64_any_dtype(out[set_col].dtype) else pd.NA
        out.loc[mask, set_col] = null_val
    else:
        text = (set_text or "").strip()
        if not text:
            raise ValueError("Η τιμή/έκφραση SET είναι κενή.")
        if text[0] in _ARITH_PREFIX_OPS:
            if not pd.api.types.is_numeric_dtype(out[set_col].dtype):
                raise ValueError(f"Η στήλη-στόχος '{set_col}' δεν είναι αριθμητικού τύπου — δεν μπορεί να εφαρμοστεί αριθμητική πράξη.")
            op_func = _ARITH_PREFIX_OPS[text[0]]
            rest = text[1:].strip()
            if not rest:
                raise ValueError("Λείπει η τιμή/έκφραση μετά τον τελεστή.")
            rhs = parse_arithmetic_expression(rest, out)
            computed = op_func(out[set_col], rhs)
            out.loc[mask, set_col] = computed[mask]
        else:
            parsed = _parse_value_for_column(out[set_col], text)
            out.loc[mask, set_col] = parsed

    return out, int(mask.sum())


# ------------------------------------------------------------------ Ενότητα 2: Type Casting

def cast_column(df, col, target_type):
    """target_type: 'string' | 'int' | 'float' | 'datetime'.
    Αποτυχημένα casts γίνονται σιωπηλά NULL. Επιστρέφει (νέο DataFrame, πλήθος αποτυχιών)."""
    out = df.copy()
    series = out[col]

    if target_type == "string":
        out[col] = series.astype(str).where(series.notna(), other=pd.NA)
        return out, 0

    was_notnull = series.notna()

    if target_type in ("int", "float"):
        # clean_numeric_string() is a no-op passthrough for non-str values, so it's safe
        # to always map it — avoids relying on a fragile dtype check (pandas may use a
        # dedicated "str" extension dtype instead of classic "object" for text columns).
        cleaned = series.map(clean_numeric_string) if not pd.api.types.is_numeric_dtype(series.dtype) else series
        converted = pd.to_numeric(cleaned, errors="coerce")
        n_fail = int((was_notnull & converted.isna()).sum())
        out[col] = converted.astype("Int64") if target_type == "int" else converted.astype("float64")
        return out, n_fail

    if target_type == "datetime":
        converted = pd.to_datetime(series, errors="coerce")
        n_fail = int((was_notnull & converted.isna()).sum())
        out[col] = converted
        return out, n_fail

    raise ValueError(f"Άγνωστος target_type: {target_type}")


# -------------------------------------------------------- Ενότητα 2: String Functions

def _is_text_dtype(dtype) -> bool:
    return not (
        pd.api.types.is_numeric_dtype(dtype)
        or pd.api.types.is_datetime64_any_dtype(dtype)
        or pd.api.types.is_bool_dtype(dtype)
    )


def trim_column(df: pd.DataFrame, col: str) -> pd.DataFrame:
    """TRIM: αφαιρεί περιμετρικά κενά (όχι εσωτερικά) από κάθε τιμή της στήλης, in-place."""
    out = df.copy()
    out[col] = out[col].map(lambda v: v.strip() if isinstance(v, str) else v)
    return out


def concat_columns(df: pd.DataFrame, col1: str, col2: str, separator: str, new_col_name: str) -> pd.DataFrame:
    """
    CONCAT: δημιουργεί ΝΕΑ στήλη (τέρμα δεξιά) = <col1><separator><col2>.
    Κενό separator -> default ένα κενό (" "), ΟΧΙ τίποτα. NULL τιμές αντιμετωπίζονται
    ως κενό string στη συγχώνευση (όχι το literal "nan").
    Ρίχνει ValueError αν το new_col_name υπάρχει ήδη.
    """
    if new_col_name in df.columns:
        raise ValueError(f"Η στήλη '{new_col_name}' υπάρχει ήδη — διάλεξε άλλο όνομα.")
    sep = separator if separator else " "
    out = df.copy()
    left = out[col1].astype(str).where(out[col1].notna(), "")
    right = out[col2].astype(str).where(out[col2].notna(), "")
    out[new_col_name] = left + sep + right
    return out


def parse_position_spec(text: str):
    """Parse '3' -> (3,3) ή '1-3' -> (1,3). 1-based, inclusive. Ρίχνει ValueError σε μη έγκυρη σύνταξη."""
    text = (text or "").strip()
    if not text:
        raise ValueError("Η θέση χαρακτήρα/εύρος είναι κενή.")
    if "-" in text:
        parts = text.split("-")
        if len(parts) != 2:
            raise ValueError(f"Μη έγκυρο εύρος θέσης: '{text}' (αναμένεται π.χ. '1-3').")
        try:
            start, end = int(parts[0].strip()), int(parts[1].strip())
        except ValueError:
            raise ValueError(f"Μη έγκυρο εύρος θέσης: '{text}' (αναμένεται π.χ. '1-3').")
    else:
        try:
            start = end = int(text)
        except ValueError:
            raise ValueError(f"Μη έγκυρη θέση χαρακτήρα: '{text}' (αναμένεται π.χ. '3' ή '1-3').")
    if start < 1 or end < 1 or start > end:
        raise ValueError(f"Μη έγκυρη θέση/εύρος: '{text}' (οι θέσεις ξεκινούν από το 1, και start <= end).")
    return start, end


def _apply_case_to_value(value, start: int, end: int, mode: str):
    if not isinstance(value, str) or len(value) < end:
        return value   # μικρότερου μήκους από τη ζητούμενη θέση/εύρος -> αμετάβλητη, χωρίς σφάλμα
    prefix, middle, suffix = value[:start - 1], value[start - 1:end], value[end:]
    middle = middle.upper() if mode == "upper" else middle.lower()
    return prefix + middle + suffix


def apply_case_by_position(df: pd.DataFrame, col: str, position_text: str, mode: str) -> pd.DataFrame:
    """
    UPPER/LOWER σε συγκεκριμένη θέση/εύρος χαρακτήρων (1-based, inclusive), in-place.
    mode: 'upper' | 'lower'. Τιμές μικρότερου μήκους από τη ζητούμενη θέση/εύρος
    παραμένουν αμετάβλητες, χωρίς σφάλμα. Ρίχνει ValueError αν η στήλη δεν είναι
    τύπου κειμένου, ή αν το position_text έχει μη έγκυρη σύνταξη.
    """
    if not _is_text_dtype(df[col].dtype):
        raise ValueError(f"Το {mode.upper()} εφαρμόζεται μόνο σε στήλες κειμένου.")
    start, end = parse_position_spec(position_text)
    out = df.copy()
    out[col] = out[col].map(lambda v: _apply_case_to_value(v, start, end, mode))
    return out


# ------------------------------------------------- Επαναφορά / αποθήκευση επεξεργασμένων γραμμών

def apply_row_edits(df: pd.DataFrame, edited: pd.DataFrame, rows) -> pd.DataFrame:
    """
    Επιστρέφει αντίγραφο του df όπου οι γραμμές `rows` (index labels) παίρνουν τις τιμές
    τους από τον επεξεργασμένο πίνακα `edited` (π.χ. Missing Values, Duplicates, Outliers,
    Ενεργό σύνολο). Μόνο στήλες που υπάρχουν και στους δύο: βοηθητικές στήλες του edited
    ("Επιλογή", "Αιτία") αγνοούνται, και διορθώσεις σε γραμμές εκτός `rows` δεν περνούν.
    """
    out = df.copy()
    for idx in rows:
        for col in out.columns:
            if col in edited.columns:
                out.loc[idx, col] = edited.loc[idx, col]
    return out


# ------------------------------------------------------------------ Ενότητα 3: Missing Values

def detect_missing_values(df: pd.DataFrame) -> pd.DataFrame:
    """Γραμμές με NULL/NaN σε τουλάχιστον μία στήλη, με το πλήρες row context."""
    return df[df.isna().any(axis=1)]



# ------------------------------------------------------------------ Ενότητα 4: Duplicates

def detect_key_duplicates(df: pd.DataFrame, key_col) -> pd.DataFrame:
    """
    Καθαρή ανίχνευση: γραμμές των οποίων η τιμή στη στήλη key_col επαναλαμβάνεται
    σε τουλάχιστον μία ακόμη γραμμή — χωρίς κριτήριο "ποια κρατάμε" (αυτό το
    αποφασίζει αποκλειστικά ο χρήστης μέσω Επαναφορά/Διαγραφή). NULL τιμές στο
    key_col αγνοούνται (δεν θεωρούνται "ίδιο κλειδί" μεταξύ τους).
    """
    cols = ["Αιτία"] + list(df.columns)
    if not key_col or key_col not in df.columns or df.empty:
        return pd.DataFrame(columns=cols)

    dup_mask = df[key_col].notna() & df.duplicated(subset=[key_col], keep=False)
    if not dup_mask.any():
        return pd.DataFrame(columns=cols)

    result = df[dup_mask].copy()
    result.insert(0, "Αιτία", [
        f"Επαναλαμβανόμενη τιμή στη στήλη '{key_col}' (τιμή: {v})" for v in result[key_col]
    ])
    return result


# ------------------------------------------------------------------ Ενότητα 5: Outliers

def detect_outliers(df: pd.DataFrame, rules: list) -> pd.DataFrame:
    """
    rules: [{"col": str, "min": value|None, "max": value|None}, ...] — numeric ή
    datetime στήλες. Επιστρέφει γραμμές που παραβιάζουν έστω έναν κανόνα, με
    στήλη "Αιτία" που περιγράφει ΟΛΕΣ τις παραβιάσεις ανά γραμμή.
    """
    reasons: dict = {}
    for rule in rules:
        col, lo, hi = rule.get("col"), rule.get("min"), rule.get("max")
        if not col or col not in df.columns or (lo is None and hi is None):
            continue
        series = df[col]
        mask = pd.Series(False, index=df.index)
        if lo is not None:
            mask = mask | (series < lo)
        if hi is not None:
            mask = mask | (series > hi)
        mask = mask & series.notna()
        for idx in df.index[mask]:
            val = series.loc[idx]
            reasons.setdefault(idx, []).append(f"{col}: εκτός ορίων [{lo}, {hi}] (τιμή: {val})")

    cols = ["Αιτία"] + list(df.columns)
    if not reasons:
        return pd.DataFrame(columns=cols)

    ordered_idx = [i for i in df.index if i in reasons]
    result = df.loc[ordered_idx].copy()
    result.insert(0, "Αιτία", ["\n".join(reasons[i]) for i in ordered_idx])
    return result
