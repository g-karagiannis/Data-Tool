"""Sidebar (mode, active dataset, change history) and the Advanced (SQL) screen."""
import pandas as pd
from streamlit.testing.v1 import AppTest

from conftest import APP_PATH, DATASET_NAME, run_app
from modules import data_loader as dl

QUERY = "SELECT Market, COUNT(*) AS n FROM data GROUP BY Market ORDER BY Market"


def button(at, label):
    """The SQL screen's buttons have no key (the Workshop's own "Εκτέλεση" does)."""
    [b] = [b for b in at.button if b.label == label and b.key is None]
    return b


def advanced(at):
    [mode] = [r for r in at.sidebar.radio if r.label == "Λειτουργία"]
    mode.set_value("Advanced (SQL)").run()
    assert not at.exception, at.exception


def run_query(at, query):
    at.text_area(key="sql_query_text").set_value(query).run()
    button(at, "Εκτέλεση").click().run()
    assert not at.exception, at.exception


def test_the_dataset_picker_switches_the_active_dataset(clean_main):
    other = clean_main.head(10)
    at = AppTest.from_file(str(APP_PATH), default_timeout=120)
    at.session_state["datasets"] = {DATASET_NAME: clean_main.copy(), "μικρό": other.copy()}
    at.run()
    [picker] = [s for s in at.sidebar.selectbox if s.label == "Επίλεξε dataset"]
    assert list(picker.options) == [DATASET_NAME, "μικρό"] and picker.value == DATASET_NAME
    picker.set_value("μικρό").run()
    assert at.session_state["active"] == "μικρό"
    assert any("10 γραμμές" in m.value for m in at.sidebar.markdown)
    pd.testing.assert_frame_equal(at.tabs[0].dataframe[0].value, other, check_dtype=False)


def test_history_is_empty_at_first_then_lists_changes(clean_main):
    at = run_app(clean_main)
    assert any(c.value == "Καμία αλλαγή ακόμα σε αυτό το dataset." for c in at.sidebar.caption)
    at.tabs[1].button(key="trim_apply").click().run()
    [history] = [d.value for d in at.sidebar.dataframe]
    assert list(history.columns) == ["Ώρα", "Αλλαγή"]
    assert history["Αλλαγή"].tolist() == ["TRIM: 'Date'"]


def test_sql_query_result_and_save_as_new_dataset(clean_main):
    at = run_app(clean_main)
    advanced(at)
    run_query(at, QUERY)
    expected = dl.query_dataframe(clean_main, QUERY, table_name="data")
    pd.testing.assert_frame_equal(at.session_state["sql_result"], expected)
    labels = [d.proto.label for d in at.get("download_button")]
    assert "Λήψη αποτελέσματος ως CSV" in labels

    at.text_input(key="sql_save_name").set_value("ανά αγορά").run()
    button(at, "Αποθήκευση ως νέο dataset").click().run()
    assert not at.exception, at.exception
    pd.testing.assert_frame_equal(at.session_state["datasets"]["ανά αγορά"], expected)
    assert at.session_state["sql_result"] is None


def test_sql_result_can_replace_the_active_dataset_with_undo(clean_main):
    at = run_app(clean_main)
    advanced(at)
    run_query(at, QUERY)
    button(at, f"Ενημέρωση ενεργού dataset ('{DATASET_NAME}') με το αποτέλεσμα").click().run()
    assert not at.exception, at.exception
    assert list(at.session_state["datasets"][DATASET_NAME].columns) == ["Market", "n"]
    assert at.session_state["undo_stack"][DATASET_NAME][-1]["description"] == "Ενημέρωση μέσω SQL (Advanced mode)"


def test_a_bad_query_shows_the_error_and_keeps_no_result(clean_main):
    at = run_app(clean_main)
    advanced(at)
    run_query(at, "SELECT nope FROM data")
    assert any(t.value.startswith("Σφάλμα στο query:") for t in at.toast)
    assert at.session_state["sql_result"] is None
