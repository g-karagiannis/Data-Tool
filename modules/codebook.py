"""
Codebook σε PDF για αρχεία σταθερού πλάτους (.dat): βρίσκει τον κατάλογο μεταβλητών με
στήλες «Start End Name Description» (π.χ. τα codebooks του MEPS) και τον επιστρέφει ως
πίνακα, ώστε ο χρήστης να διαλέγει μεταβλητές αντί να γράφει θέσεις. Ελέγχει επίσης αν ο
κατάλογος καλύπτει όλη τη γραμμή του .dat χωρίς κενά και επικαλύψεις — αν όχι, κάτι
διαβάστηκε λάθος ή το codebook δεν είναι αυτού του αρχείου. Καμία εξάρτηση από Streamlit.
"""
import re

import pandas as pd

CATALOGUE_COLUMNS = ["Όνομα", "Περιγραφή", "Από", "Έως"]
MAX_PAGES_BEFORE_LIST = 100   # ο κατάλογος αναζητείται στις πρώτες σελίδες

_HEADER = re.compile(r"^start\s+end\s+name\b", re.IGNORECASE)
_VARIABLE = re.compile(r"^(\d+)\s+(\d+)\s+([A-Za-z][A-Za-z0-9_]*)(?:\s+(.*))?$")
_PAGE_FOOTER = re.compile(r"^page\s+\d+\s+of\s+\d+$", re.IGNORECASE)


def pdf_pages_text(pdf_bytes: bytes, max_pages: int = None):
    """Κείμενο ανά σελίδα (generator, για να σταματά η ανάγνωση μόλις τελειώσει ο κατάλογος)."""
    import pypdfium2 as pdfium

    document = pdfium.PdfDocument(pdf_bytes)
    try:
        for index in range(min(len(document), max_pages or len(document))):
            text = document[index].get_textpage().get_text_range()
            yield text.replace("￾", "-")   # ενωτικό αλλαγής γραμμής
    finally:
        document.close()


def parse_variable_list(pages) -> pd.DataFrame:
    """Ο κατάλογος μεταβλητών από τις σελίδες (κείμενο) ενός codebook: οι σελίδες με επικεφαλίδα
    «Start End Name Description», στη σειρά. Περιγραφές που συνεχίζουν σε επόμενη γραμμή
    ενώνονται. Επιστρέφει πίνακα CATALOGUE_COLUMNS (κενό αν δεν βρέθηκε κατάλογος)."""
    rows, in_list = [], False
    for page_number, text in enumerate(pages, start=1):
        lines = [line.strip() for line in text.splitlines()]
        header_at = next((i for i, line in enumerate(lines) if _HEADER.match(line)), None)
        if header_at is None:
            if in_list or page_number >= MAX_PAGES_BEFORE_LIST:
                break
            continue
        in_list = True
        for line in lines[header_at + 1:]:
            if not line or _PAGE_FOOTER.match(line):
                continue
            match = _VARIABLE.match(line)
            if match:
                rows.append([match[3], (match[4] or "").strip(), int(match[1]), int(match[2])])
            elif rows:
                rows[-1][1] = f"{rows[-1][1]} {line}".strip()
    # Πολλά codebooks (π.χ. MEPS) δίνουν τον κατάλογο δύο φορές — αλφαβητικά και κατά θέση.
    # Η ίδια μεταβλητή με τις ίδιες θέσεις κρατιέται μία φορά· με άλλες θέσεις μένει, και
    # τη δείχνει ο έλεγχος κάλυψης.
    catalogue = pd.DataFrame(rows, columns=CATALOGUE_COLUMNS)
    catalogue = catalogue.drop_duplicates(["Όνομα", "Από", "Έως"]).reset_index(drop=True)
    catalogue["Από"] = catalogue["Από"].astype("int64")
    catalogue["Έως"] = catalogue["Έως"].astype("int64")
    return catalogue


def read_variable_list(pdf_bytes: bytes) -> pd.DataFrame:
    return parse_variable_list(pdf_pages_text(pdf_bytes))


def coverage_problems(catalogue: pd.DataFrame, line_length: int) -> list:
    """Τι δεν ταιριάζει ανάμεσα στον κατάλογο και στο .dat: διπλά ονόματα, επικαλύψεις, κενά,
    και αν οι θέσεις δεν καλύπτουν ακριβώς 1..μήκος γραμμής. Κενή λίστα = όλα σωστά."""
    problems = []
    duplicates = sorted(set(catalogue.loc[catalogue["Όνομα"].duplicated(), "Όνομα"]))
    if duplicates:
        problems.append("Διπλά ονόματα: " + ", ".join(duplicates[:5]))
    ordered = catalogue.sort_values(["Από", "Έως"]).reset_index(drop=True)
    covered_to = 0
    for row in ordered.itertuples(index=False):
        name, start, end = row[0], row[2], row[3]
        if start <= covered_to:
            problems.append(f"Η {name} ({start}–{end}) επικαλύπτεται με προηγούμενη μεταβλητή.")
        elif start > covered_to + 1:
            problems.append(f"Οι θέσεις {covered_to + 1}–{start - 1} δεν ανήκουν σε καμία μεταβλητή.")
        covered_to = max(covered_to, end)
        if len(problems) >= 5:
            return problems
    if covered_to != line_length:
        problems.append(f"Ο κατάλογος φτάνει ως τη θέση {covered_to}, ενώ η γραμμή του αρχείου έχει "
                        f"{line_length} χαρακτήρες.")
    return problems


def search(catalogue: pd.DataFrame, query: str) -> pd.DataFrame:
    """Μεταβλητές που περιέχουν το κείμενο στο όνομα ή στην περιγραφή (χωρίς διάκριση πεζών/κεφαλαίων)."""
    query = (query or "").strip()
    if not query:
        return catalogue
    hits = (catalogue["Όνομα"].str.contains(query, case=False, regex=False)
            | catalogue["Περιγραφή"].str.contains(query, case=False, regex=False))
    return catalogue[hits]
