"""Codebook PDFs: the "Start End Name Description" variable list is read once, searched,
ticked, and gives the .dat columns instead of typed positions."""
import io
import zipfile

import matplotlib
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from conftest import APP_PATH
from modules import codebook as cbk
from modules import fixed_width as fw
from modules import upload_plan as up
from test_fixed_width import DAT, load

matplotlib.use("Agg")

# The variable list of the test .dat (40 characters per line), alphabetical like MEPS,
# with a description that continues on the next line and a page that is not part of the list.
PAGES = [
    ["TEST SURVEY", "FULL YEAR DATA CODEBOOK", "Contents"],
    ["TEST Codebook", "Start End Name Description", "11 13 AGE AGE AT END OF YEAR", "1 10 ID PERSON ID",
     "Page 2 of 4"],
    ["TEST Codebook", "Start End Name Description", "33 40 REGION REGION OF RESIDENCE", "14 20 RX TOTAL RX-EXP",
     "21 32 WT FINAL PERSON", "WEIGHT", "Page 3 of 4"],
    ["Variable Codebook", "1 10 NOTAVAR SHOULD NOT BE READ"],
]
CATALOGUE = pd.DataFrame({
    "Όνομα": ["AGE", "ID", "REGION", "RX", "WT"],
    "Περιγραφή": ["AGE AT END OF YEAR", "PERSON ID", "REGION OF RESIDENCE", "TOTAL RX-EXP", "FINAL PERSON WEIGHT"],
    "Από": [11, 1, 33, 14, 21],
    "Έως": [13, 10, 40, 20, 32],
})


def make_pdf(pages) -> bytes:
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages

    buffer = io.BytesIO()
    with matplotlib.rc_context({"pdf.fonttype": 42}), PdfPages(buffer) as pdf:
        for lines in pages:
            fig = plt.figure(figsize=(8.5, 11))
            for i, line in enumerate(lines):
                fig.text(0.1, 0.9 - i * 0.04, line, fontsize=10)
            pdf.savefig(fig)
            plt.close(fig)
    return buffer.getvalue()


@pytest.fixture(scope="module")
def codebook_pdf():
    return make_pdf(PAGES)


# ---------------------------------------------------------------- reading (no UI)

def test_the_variable_list_is_read_from_the_text_of_the_pages():
    pd.testing.assert_frame_equal(cbk.parse_variable_list(["\n".join(p) for p in PAGES]), CATALOGUE)


def test_the_variable_list_is_read_from_a_pdf(codebook_pdf):
    pd.testing.assert_frame_equal(cbk.read_variable_list(codebook_pdf), CATALOGUE)


def test_a_list_given_twice_alphabetically_and_by_position_is_kept_once():
    by_position = ["Start End Name Description", "1 10 ID PERSON ID", "11 13 AGE AGE AT END OF YEAR",
                   "14 20 RX TOTAL RX-EXP", "21 32 WT FINAL PERSON WEIGHT", "33 40 REGION REGION OF RESIDENCE"]
    pages = ["\n".join(p) for p in PAGES[:3]] + ["\n".join(by_position)]
    pd.testing.assert_frame_equal(cbk.parse_variable_list(pages), CATALOGUE)
    moved = ["Start End Name Description", "2 11 ID PERSON ID"]
    catalogue = cbk.parse_variable_list(["\n".join(p) for p in PAGES[1:3]] + ["\n".join(moved)])
    assert catalogue["Όνομα"].tolist().count("ID") == 2
    assert cbk.coverage_problems(catalogue, 40)[0] == "Διπλά ονόματα: ID"


def test_a_pdf_without_a_variable_list_gives_an_empty_catalogue():
    catalogue = cbk.parse_variable_list(["Some report\n1 10 LOOKS LIKE A ROW", "More text"])
    assert catalogue.empty and list(catalogue.columns) == cbk.CATALOGUE_COLUMNS


def test_a_complete_catalogue_has_no_coverage_problems():
    assert cbk.coverage_problems(CATALOGUE, 40) == []


def test_gaps_overlaps_duplicates_and_a_wrong_line_length_are_reported():
    gap = CATALOGUE[CATALOGUE["Όνομα"] != "RX"]
    assert cbk.coverage_problems(gap, 40) == ["Οι θέσεις 14–20 δεν ανήκουν σε καμία μεταβλητή."]
    overlap = pd.concat([CATALOGUE, pd.DataFrame([["X", "", 30, 35]], columns=cbk.CATALOGUE_COLUMNS)])
    assert cbk.coverage_problems(overlap, 40) == ["Η X (30–35) επικαλύπτεται με προηγούμενη μεταβλητή.",
                                                  "Η REGION (33–40) επικαλύπτεται με προηγούμενη μεταβλητή."]
    assert cbk.coverage_problems(CATALOGUE, 4690) == [
        "Ο κατάλογος φτάνει ως τη θέση 40, ενώ η γραμμή του αρχείου έχει 4690 χαρακτήρες."]
    twice = pd.concat([CATALOGUE, CATALOGUE.iloc[[0]]])
    assert cbk.coverage_problems(twice, 40)[0] == "Διπλά ονόματα: AGE"


def test_search_matches_name_or_description_in_any_case():
    assert cbk.search(CATALOGUE, "weight")["Όνομα"].tolist() == ["WT"]
    assert cbk.search(CATALOGUE, "id")["Όνομα"].tolist() == ["ID", "REGION"]   # "resIDence"
    assert len(cbk.search(CATALOGUE, "  ")) == 5


def test_only_pdfs_within_the_limit_are_codebook_candidates():
    members = [("h256.dat", 90 * 1024 * 1024), ("h256cb.pdf", 4 * 1024 * 1024), ("big.pdf", 11 * 1024 * 1024)]
    assert up.codebook_candidates(members) == ["h256cb.pdf"]


# ---------------------------------------------------------------- the real screen

SOURCE = "pack.zip/people.dat"


def make_zip(codebook_pdf) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("people.dat", DAT)
        archive.writestr("codebook.pdf", codebook_pdf)
    return buffer.getvalue()


def app(state=None):
    at = AppTest.from_file(str(APP_PATH), default_timeout=120)
    for key, value in (state or {}).items():
        at.session_state[key] = value
    at.run()
    return at


def upload(at, content):
    at.file_uploader(key="file_uploader_0").set_value([("pack.zip", content, "application/zip")]).run()
    assert not at.exception, at.exception


def press_load(at):
    at.button(key="load_all").click().run()
    assert not at.exception, at.exception


def test_the_codebook_in_the_zip_is_read_once_and_checked(codebook_pdf):
    at = app()
    upload(at, make_zip(codebook_pdf))
    assert at.radio(key=f"fwf_columns_from_{SOURCE}").value == "Codebook: codebook.pdf"
    book = at.session_state["codebooks"][SOURCE]
    pd.testing.assert_frame_equal(book["catalogue"], CATALOGUE)
    assert any("5 μεταβλητές" in s.value and "1–40" in s.value for s in at.success)
    press_load(at)
    assert not at.session_state["datasets"]
    assert any("Τίκαρε τουλάχιστον μία μεταβλητή" in i.value for i in at.info)
    assert any("δεν έχεις τικάρει καμία μεταβλητή" in t.value for t in at.toast)


def test_ticked_variables_load_in_tick_order_with_their_types(codebook_pdf):
    book = {"pdf": "codebook.pdf", "catalogue": CATALOGUE, "picked": {"WT": fw.TYPE_AUTO, "ID": fw.TYPE_TEXT}}
    at = app({"codebooks": {SOURCE: book}})
    upload(at, make_zip(codebook_pdf))
    assert any("Επιλεγμένες (2): WT, ID (Κείμενο)" in c.value for c in at.caption)
    press_load(at)
    expected, _, _ = load({"ID": fw.TYPE_TEXT})
    pd.testing.assert_frame_equal(at.session_state["datasets"][SOURCE], expected[["WT", "ID"]])


def test_a_codebook_that_does_not_match_the_file_is_flagged(codebook_pdf):
    other = make_pdf([["Start End Name Description", "1 10 ID PERSON ID", "11 30 REST EVERYTHING ELSE"]])
    at = app()
    upload(at, make_zip(other))
    assert any("δεν ταιριάζει" in w.value and "θέση 30" in w.value for w in at.warning)


def test_the_typed_position_table_is_still_available(codebook_pdf):
    table = pd.DataFrame({"Όνομα": ["AGE"], "Από": pd.array([11], dtype="Int64"),
                          "Έως": pd.array([13], dtype="Int64"), "Τύπος": [fw.TYPE_AUTO]})
    at = app({"fixed_width_specs": {SOURCE: table}})
    upload(at, make_zip(codebook_pdf))
    at.radio(key=f"fwf_columns_from_{SOURCE}").set_value("Χειροκίνητα (πίνακας θέσεων)").run()
    press_load(at)
    assert list(at.session_state["datasets"][SOURCE].columns) == ["AGE"]


def test_clear_all_forgets_the_codebooks(codebook_pdf):
    at = app()
    upload(at, make_zip(codebook_pdf))
    assert at.session_state["codebooks"]
    [button] = [b for b in at.sidebar.button if b.label == "Καθαρισμός όλων (νέα ανάλυση)"]
    button.click().run()
    assert at.session_state["codebooks"] == {}
