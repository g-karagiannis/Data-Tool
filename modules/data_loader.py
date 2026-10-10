"""
Φόρτωση δεδομένων από πολλαπλούς τύπους αρχείων:
.csv, .xls/.xlsx, .px (PC-Axis), .pdf (πίνακες), .sql (queries), και αρχεία μέσα σε .zip
Επιστρέφει πάντα ένα ή περισσότερα pandas DataFrame.
"""
import io
import zipfile

import pandas as pd
import duckdb


DEFAULT_PRIVACY_SYMBOLS = ["**", "*", ":", "..", "...", "…", "-", "N/A", "n/a", "NA"]


def read_raw_csv(raw_bytes: bytes):
    """Διαβάζει το CSV ως 'raw grid' (χωρίς υπόθεση για header), δοκιμάζοντας
    διαφορετικά διαχωριστικά/encodings. Επιστρέφει (DataFrame, sep, encoding)."""
    for enc in ("utf-8", "utf-8-sig", "cp1253", "latin1"):
        for sep in (",", ";", "\t"):
            try:
                df = pd.read_csv(io.BytesIO(raw_bytes), sep=sep, encoding=enc, header=None, dtype=str)
                if df.shape[1] > 1:
                    return df, sep, enc
            except Exception:
                continue
    return pd.read_csv(io.BytesIO(raw_bytes), header=None, dtype=str), ",", "utf-8"


def get_excel_sheet_names(raw_bytes: bytes) -> list:
    return pd.ExcelFile(io.BytesIO(raw_bytes)).sheet_names


def read_raw_excel(raw_bytes: bytes, sheet_name) -> pd.DataFrame:
    """Διαβάζει ένα φύλλο Excel ως 'raw grid', χωρίς υπόθεση για header."""
    return pd.read_excel(io.BytesIO(raw_bytes), sheet_name=sheet_name, header=None, dtype=str)


def build_dataframe_from_raw(
    raw: pd.DataFrame,
    skip_rows: int = 0,
    skip_cols: int = 0,
    ffill_header: bool = True,
    privacy_symbols: list | None = None,
) -> pd.DataFrame:
    """Χτίζει το τελικό DataFrame από ένα raw grid:
    - παραλείπει τις πρώτες `skip_rows` γραμμές
    - παραλείπει τις πρώτες `skip_cols` στήλες (από αριστερά)
    - χρησιμοποιεί την πρώτη γραμμή που απομένει (μετά τις παραλείψεις) ως επικεφαλίδες
    - προαιρετικά κάνει forward-fill τα κενά κελιά της επικεφαλίδας (merged cells)
    - μετατρέπει τα δοσμένα σύμβολα απορρήτου (π.χ. "**") σε NaN
    - προσπαθεί να αναγνωρίσει αριθμητικές στήλες
    """
    trimmed = raw.iloc[skip_rows:, skip_cols:].reset_index(drop=True)
    if trimmed.empty:
        return pd.DataFrame()

    header_values = trimmed.iloc[0].copy()
    if ffill_header:
        header_values = header_values.ffill()
    header_values = header_values.fillna("")

    col_names = []
    seen = {}
    for i, v in enumerate(header_values.tolist()):
        name = str(v).strip() if str(v).strip() else f"Στήλη_{i + 1}"
        if name in seen:
            seen[name] += 1
            name = f"{name}_{seen[name]}"
        else:
            seen[name] = 0
        col_names.append(name)

    data = trimmed.iloc[1:].reset_index(drop=True)
    data.columns = col_names

    if privacy_symbols:
        data = data.replace({s: pd.NA for s in privacy_symbols})

    for col in data.columns:
        non_null = data[col].notna().sum()
        if non_null == 0:
            continue
        converted = pd.to_numeric(data[col], errors="coerce")
        if converted.notna().sum() / non_null >= 0.8:
            data[col] = converted

    return data


def zip_members(raw_bytes: bytes) -> list:
    """[(όνομα, αποσυμπιεσμένο μέγεθος σε bytes)] των αρχείων ενός zip, χωρίς φακέλους και
    χωρίς τα κρυφά αρχεία που προσθέτει το macOS (__MACOSX/, ._*). Δεν αποσυμπιέζει τίποτα."""
    with zipfile.ZipFile(io.BytesIO(raw_bytes)) as archive:
        return [
            (info.filename, info.file_size)
            for info in archive.infolist()
            if not info.is_dir()
            and not info.filename.startswith("__MACOSX/")
            and not info.filename.rsplit("/", 1)[-1].startswith("._")
        ]


def read_zip_member(raw_bytes: bytes, name: str) -> bytes:
    """Τα bytes ενός αρχείου μέσα στο zip. Το zipfile διαβάζει το πολύ το δηλωμένο μέγεθος
    και ελέγχει το CRC, οπότε ένα αλλοιωμένο αρχείο βγάζει σφάλμα αντί για λάθος δεδομένα."""
    with zipfile.ZipFile(io.BytesIO(raw_bytes)) as archive:
        return archive.read(name)


def load_px(file) -> pd.DataFrame:
    """PC-Axis (.px) αρχεία — χρησιμοποιούνται από στατιστικές υπηρεσίες
    (π.χ. Στατιστική Υπηρεσία Δανίας, Eurostat)."""
    import tempfile
    from pyaxis import pyaxis

    with tempfile.NamedTemporaryFile(suffix=".px", delete=False) as tmp:
        tmp.write(file.read())
        tmp_path = tmp.name
    parsed = pyaxis.parse(tmp_path, encoding="ISO-8859-15")
    return parsed["DATA"]


def load_pdf_tables(file) -> list:
    """Εξάγει όλους τους πίνακες από ένα PDF. Επιστρέφει λίστα από DataFrames."""
    import pdfplumber

    tables = []
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            for tbl in page.extract_tables():
                if not tbl or len(tbl) < 2:
                    continue
                header, *rows = tbl
                df = pd.DataFrame(rows, columns=header)
                tables.append(df)
    return tables


def run_sql_script(sql_text: str, existing_tables: dict) -> dict:
    """
    Εκτελεί ένα .sql script (CREATE TABLE / SELECT / κλπ) μέσω DuckDB.
    existing_tables: dict {name: DataFrame} που ήδη έχουν φορτωθεί στη
    συνεδρία, ώστε το script να μπορεί να τα αναφέρει.
    Επιστρέφει dict {table_or_query_name: DataFrame} με ό,τι προέκυψε.
    """
    con = duckdb.connect(database=":memory:")
    for name, df in existing_tables.items():
        con.register(name, df)

    results = {}
    # Σπάει το script σε ξεχωριστές εντολές (απλός διαχωρισμός με ;)
    statements = [s.strip() for s in sql_text.split(";") if s.strip()]
    for i, stmt in enumerate(statements):
        try:
            res = con.execute(stmt)
            df = res.fetchdf()
            if not df.empty or stmt.lower().startswith("select"):
                label = f"αποτέλεσμα_{i+1}"
                results[label] = df
        except Exception as e:
            results[f"σφάλμα_{i+1}"] = pd.DataFrame({"σφάλμα": [str(e)], "εντολή": [stmt]})
    # Πρόσθεσε και όποιους νέους πίνακες δημιουργήθηκαν (CREATE TABLE)
    try:
        table_names = [r[0] for r in con.execute("SHOW TABLES").fetchall()]
        for t in table_names:
            if t not in existing_tables:
                results[t] = con.execute(f"SELECT * FROM {t}").fetchdf()
    except Exception:
        pass
    return results


def query_dataframe(df: pd.DataFrame, sql: str, table_name: str = "data") -> pd.DataFrame:
    """Advanced mode: τρέχει ένα ελεύθερο SQL SELECT πάνω σε ένα DataFrame."""
    con = duckdb.connect(database=":memory:")
    con.register(table_name, df)
    return con.execute(sql).fetchdf()


