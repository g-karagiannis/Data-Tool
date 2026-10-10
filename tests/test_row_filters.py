"""Row filters while loading a .dat: rules on the loaded columns, all of them must hold,
blank values never pass."""
import pandas as pd
from streamlit.testing.v1 import AppTest

from conftest import APP_PATH
from modules import fixed_width as fw
from test_fixed_width import DAT, load, spec

TYPES = {"ID": fw.TYPE_TEXT, "AGE": fw.TYPE_NUMBER, "RX": fw.TYPE_NUMBER, "WT": fw.TYPE_NUMBER,
         "REGION": fw.TYPE_TEXT}


def rules_table(*rows) -> pd.DataFrame:
    return pd.DataFrame(list(rows), columns=list(fw.FILTER_COLUMNS)) if rows else fw.empty_filters()


def data():
    df, chosen, _ = load({"ID": fw.TYPE_TEXT})
    assert chosen == TYPES
    return df


# ---------------------------------------------------------------- rules (no UI)

def test_valid_rules_are_read_with_numbers_as_numbers():
    rules, errors = fw.clean_filters(rules_table(("AGE", "≥", "18"), ("WT", ">", "0,5"), ("REGION", "=", "NA"),
                                                 (None, None, None)), TYPES)
    assert errors == []
    assert rules == [{"column": "AGE", "op": "≥", "value": 18.0}, {"column": "WT", "op": ">", "value": 0.5},
                     {"column": "REGION", "op": "=", "value": "NA"}]


def test_wrong_rules_are_explained():
    _, errors = fw.clean_filters(rules_table(
        ("SEX", "=", "1"), ("AGE", None, "1"), ("AGE", "=", None), ("AGE", ">", "abc"), ("REGION", ">", "N")), TYPES)
    assert errors == [
        "Φίλτρο 1: διάλεξε μία από τις στήλες που φορτώνονται.",
        "Φίλτρο 2: διάλεξε τελεστή (= ≠ > ≥ < ≤).",
        "Φίλτρο 3: λείπει η τιμή.",
        "Φίλτρο 4: η AGE είναι αριθμός, ενώ η τιμή «abc» δεν είναι.",
        "Φίλτρο 5: ο τελεστής > ισχύει μόνο για στήλες «Αριθμός» — η REGION είναι «Κείμενο».",
    ]


def test_blank_values_never_pass_a_rule():
    df = data()                                         # AGE: 34, -1, 5, blank
    ge, _ = fw.clean_filters(rules_table(("AGE", "≥", "5")), TYPES)
    assert fw.apply_filters(df, ge)["ID"].tolist() == ["0000012345", "0000012347"]
    ne, _ = fw.clean_filters(rules_table(("AGE", "≠", "34")), TYPES)
    assert fw.apply_filters(df, ne)["AGE"].tolist() == [-1, 5]


def test_all_rules_must_hold_and_text_is_compared_exactly():
    df = data()
    rules, _ = fw.clean_filters(rules_table(("WT", ">", "0"), ("RX", "<", "1000000")), TYPES)
    assert fw.apply_filters(df, rules)["ID"].tolist() == ["0000012345", "0000012348"]
    text, _ = fw.clean_filters(rules_table(("REGION", "=", "NA")), TYPES)
    assert fw.apply_filters(df, text)["ID"].tolist() == ["0000012346"]
    kept = fw.apply_filters(df, [])
    pd.testing.assert_frame_equal(kept, df)


# ---------------------------------------------------------------- the real screen

def app(filters):
    at = AppTest.from_file(str(APP_PATH), default_timeout=120)
    at.session_state["fixed_width_specs"] = {"people.dat": spec({"ID": fw.TYPE_TEXT})}
    at.session_state["fixed_width_filters"] = {"people.dat": filters}
    at.run()
    at.file_uploader(key="file_uploader_0").set_value([("people.dat", DAT, "application/octet-stream")]).run()
    assert not at.exception, at.exception
    return at


def press_load(at):
    at.button(key="load_all").click().run()
    assert not at.exception, at.exception


def test_only_the_rows_that_pass_are_loaded():
    at = app(rules_table(("WT", ">", "0"), ("AGE", "≥", "18")))
    assert any("Μετά τα φίλτρα: 1 από 4 γραμμές." in c.value for c in at.caption)
    press_load(at)
    loaded = at.session_state["datasets"]["people.dat"]
    pd.testing.assert_frame_equal(loaded, data().iloc[[0]].reset_index(drop=True))


def test_without_rules_every_row_is_loaded():
    at = app(fw.empty_filters())
    press_load(at)
    pd.testing.assert_frame_equal(at.session_state["datasets"]["people.dat"], data())


def test_a_wrong_rule_blocks_the_load():
    at = app(rules_table(("REGION", ">", "N")))
    assert any("Φίλτρο 1" in w.value for w in at.warning)
    press_load(at)
    assert not at.session_state["datasets"]
    assert any("φίλτρα γραμμών" in t.value for t in at.toast)


def test_rules_that_keep_no_row_block_the_load():
    at = app(rules_table(("AGE", ">", "200")))
    assert any("καμία γραμμή" in w.value for w in at.warning)
    press_load(at)
    assert not at.session_state["datasets"]


def test_clear_all_forgets_the_row_rules():
    at = app(rules_table(("AGE", ">", "1")))
    [button] = [b for b in at.sidebar.button if b.label == "Καθαρισμός όλων (νέα ανάλυση)"]
    button.click().run()
    assert at.session_state["fixed_width_filters"] == {}
