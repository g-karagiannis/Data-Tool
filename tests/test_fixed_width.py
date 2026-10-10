"""Fixed-width .dat files: columns cut at the codebook positions, every value exactly the
characters at its position, numbers only when every value is a number."""
import io
import zipfile

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from conftest import APP_PATH
from modules import fixed_width as fw
from modules import upload_plan as up

# A small MEPS-like file: person id (1-10), age (11-13), drug spending (14-20),
# weight with 6 decimals (21-32), region text (33-40). Blank fields and the text "NA" included.
RECORDS = [
    ("0000012345", " 34", "   1250", "  776.278855", "NORTH   "),
    ("0000012346", " -1", "      0", "    0.000000", "NA      "),
    ("0000012347", "  5", "1188795", "91256.761356", "        "),
    ("0000012348", "   ", "     17", " 1234.500000", "SOUTH  W"),
]
LINES = ["".join(r) for r in RECORDS]
DAT = ("\r\n".join(LINES) + "\r\n").encode("ascii")
POSITIONS = {"ID": (1, 10), "AGE": (11, 13), "RX": (14, 20), "WT": (21, 32), "REGION": (33, 40)}


def spec(types=None, positions=POSITIONS) -> pd.DataFrame:
    types = types or {}
    return pd.DataFrame({
        "Όνομα": list(positions),
        "Από": pd.array([a for a, _ in positions.values()], dtype="Int64"),
        "Έως": pd.array([b for _, b in positions.values()], dtype="Int64"),
        "Τύπος": [types.get(name, fw.TYPE_AUTO) for name in positions],
    })


def load(types=None):
    lines = fw.split_lines(fw.decode(DAT))
    columns, errors = fw.clean_spec(spec(types), max(len(line) for line in lines))
    assert not errors
    return fw.apply_types(fw.cut_columns(lines, columns), columns)


# ---------------------------------------------------------------- reading (no UI)

def test_every_value_is_exactly_the_characters_at_its_position():
    lines = fw.split_lines(fw.decode(DAT))
    columns, _ = fw.clean_spec(spec(), 40)
    text = fw.cut_columns(lines, columns)
    for i, line in enumerate(LINES):
        for name, (a, b) in POSITIONS.items():
            expected = line[a - 1:b].strip()
            value = text.at[i, name]
            assert (pd.isna(value) and expected == "") or value == expected, (i, name)


def test_numbers_are_converted_without_changing_their_value():
    df, chosen, errors = load({"ID": fw.TYPE_TEXT})
    assert not errors
    assert chosen == {"ID": fw.TYPE_TEXT, "AGE": fw.TYPE_NUMBER, "RX": fw.TYPE_NUMBER,
                      "WT": fw.TYPE_NUMBER, "REGION": fw.TYPE_TEXT}
    assert df["AGE"].tolist()[:3] == [34, -1, 5] and pd.isna(df["AGE"].iloc[3])
    assert df["RX"].tolist() == [1250, 0, 1188795, 17]
    for line, weight in zip(LINES, df["WT"]):
        assert weight == float(line[20:32])
    assert df["WT"].sum() == pytest.approx(776.278855 + 91256.761356 + 1234.5)


def test_text_keeps_leading_zeros_and_the_literal_na():
    df, _, _ = load({"ID": fw.TYPE_TEXT})
    assert df["ID"].tolist() == [r[0] for r in RECORDS]
    assert df["REGION"].iloc[1] == "NA"
    assert pd.isna(df["REGION"].iloc[2])
    assert df["REGION"].iloc[3] == "SOUTH  W"       # inner spaces stay


def test_automatic_type_turns_an_all_digit_id_into_a_number():
    df, chosen, _ = load()
    assert chosen["ID"] == fw.TYPE_NUMBER
    assert df["ID"].iloc[0] == 12345


def test_a_number_column_with_text_in_it_is_refused_with_the_bad_value():
    _, _, errors = load({"REGION": fw.TYPE_NUMBER})
    assert len(errors) == 1
    assert "REGION" in errors[0] and "NORTH" in errors[0]


def test_the_position_table_is_checked():
    table = pd.DataFrame({
        "Όνομα": ["A", "A", "", "B", "C", "D", None],
        "Από": pd.array([1, 2, 3, 5, 1, 2, None], dtype="Int64"),
        "Έως": pd.array([2, 3, 4, 4, 41, None, None], dtype="Int64"),
        "Τύπος": [fw.TYPE_AUTO] * 7,
    })
    columns, errors = fw.clean_spec(table, 40)
    assert errors == [
        "Γραμμή 2 (A): το όνομα υπάρχει ήδη.",
        "Γραμμή 3: λείπει το όνομα.",
        "Γραμμή 4 (B): το «Από» (5) είναι μετά το «Έως» (4).",
        "Γραμμή 5 (C): το «Έως» (41) ξεπερνά το μήκος της γραμμής (40).",
        "Γραμμή 6 (D): «Από» και «Έως» πρέπει να είναι ακέραιοι από 1 και πάνω.",
    ]
    assert fw.clean_spec(spec(), 40) == (
        [{"name": n, "start": a, "end": b, "type": fw.TYPE_AUTO} for n, (a, b) in POSITIONS.items()], [])


def test_greek_text_and_line_endings_are_read():
    assert fw.split_lines(fw.decode("Αθήνα 1\nΠάτρα 2\n\n".encode("cp1253"))) == ["Αθήνα 1", "Πάτρα 2"]
    assert fw.split_lines(fw.decode("ab\r\ncd".encode("utf-8"))) == ["ab", "cd"]


def test_dat_files_go_through_the_load_settings_and_from_zips():
    assert up.is_combinable("h256.DAT")
    assert up.size_limit("h256.dat") == up.MAX_LARGE_FILE_BYTES
    loadable, _ = up.zip_choices([("h256.dat", 90 * 1024 * 1024), ("h256cb.pdf", 1)])
    assert loadable == ["h256.dat"]


def test_a_file_that_is_not_ready_blocks_the_load():
    plan = up.plan_load({"a.dat": 0, "b.csv": 1}, [], not_ready={"a.dat": "ο πίνακας στηλών είναι άδειος."})
    assert plan["error"] == "Το a.dat δεν είναι έτοιμο για φόρτωση: ο πίνακας στηλών είναι άδειος."


# ---------------------------------------------------------------- the real screen

def app_with_spec(source=None, table=None):
    at = AppTest.from_file(str(APP_PATH), default_timeout=120)
    if source:
        at.session_state["fixed_width_specs"] = {source: table}
    at.run()
    return at


def upload(at, name, content):
    at.file_uploader(key="file_uploader_0").set_value([(name, content, "application/octet-stream")]).run()
    assert not at.exception, at.exception


def press_load(at):
    at.button(key="load_all").click().run()
    assert not at.exception, at.exception


def test_uploader_accepts_dat_files():
    at = app_with_spec()
    assert ".dat" in at.file_uploader(key="file_uploader_0").proto.type


def test_a_dat_without_columns_is_not_loaded():
    at = app_with_spec()
    upload(at, "people.dat", DAT)
    assert any("4 γραμμές, 40 χαρακτήρες" in c.value for c in at.caption)
    press_load(at)
    assert not at.session_state["datasets"]
    assert any("people.dat" in t.value and "άδειος" in t.value for t in at.toast)


def test_a_dat_loads_only_the_columns_in_the_table():
    table = spec({"ID": fw.TYPE_TEXT}, {k: POSITIONS[k] for k in ("ID", "AGE", "WT")})
    at = app_with_spec("people.dat", table)
    upload(at, "people.dat", DAT)
    press_load(at)
    df = at.session_state["datasets"]["people.dat"]
    assert list(df.columns) == ["ID", "AGE", "WT"]
    expected, _, _ = load({"ID": fw.TYPE_TEXT})
    pd.testing.assert_frame_equal(df, expected[["ID", "AGE", "WT"]])
    assert not at.session_state["pending_uploads"]


def test_a_dat_inside_a_zip_loads_with_its_own_table():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("people.dat", DAT)
        archive.writestr("codebook.pdf", b"%PDF")
    at = app_with_spec("pack.zip/people.dat", spec({"ID": fw.TYPE_TEXT}))
    upload(at, "pack.zip", buffer.getvalue())
    assert at.selectbox(key="zipmember_pack.zip").options == ["people.dat"]
    press_load(at)
    expected, _, _ = load({"ID": fw.TYPE_TEXT})
    pd.testing.assert_frame_equal(at.session_state["datasets"]["pack.zip/people.dat"], expected)


def test_a_position_past_the_end_of_the_line_is_shown_and_blocks_the_load():
    at = app_with_spec("people.dat", spec(positions={"ID": (1, 10), "TOO_FAR": (35, 45)}))
    upload(at, "people.dat", DAT)
    assert any("TOO_FAR" in w.value and "(45)" in w.value for w in at.warning)
    press_load(at)
    assert not at.session_state["datasets"]


def test_clear_all_forgets_the_position_tables():
    at = app_with_spec("people.dat", spec())
    [button] = [b for b in at.sidebar.button if b.label == "Καθαρισμός όλων (νέα ανάλυση)"]
    button.click().run()
    assert at.session_state["fixed_width_specs"] == {}
