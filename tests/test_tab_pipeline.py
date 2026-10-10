"""Tab Pipeline: casting, string functions, Missing Values / Duplicates / Outliers, export copy.
(Update/Where/Set, restore/delete and TRIM/CONCAT undo are covered in other test files.)"""
import pandas as pd

from conftest import DATASET_NAME, run_app
from modules import cleaning_pipeline as cp


def pipeline(at):
    return at.tabs[1]


def dataset(at):
    return at.session_state["datasets"][DATASET_NAME]


def captions(at):
    return [c.value for c in pipeline(at).caption]


def test_casting_converts_the_column_and_records_undo(raw_main):
    at = run_app(raw_main)
    pipeline(at).selectbox(key="cast_col").set_value("Price").run()
    pipeline(at).selectbox(key="cast_target").set_value("float").run()
    pipeline(at).button(key="cast_apply").click().run()
    assert not at.exception, at.exception
    pd.testing.assert_frame_equal(dataset(at), cp.cast_column(raw_main, "Price", "float")[0])
    assert at.session_state["undo_stack"][DATASET_NAME][-1]["description"] == "Casting: 'Price' -> float"


def test_concat_needs_a_name_for_the_new_column(clean_main):
    at = run_app(clean_main)
    pipeline(at).button(key="concat_apply").click().run()
    assert any("υποχρεωτικό" in t.value for t in at.toast)
    pd.testing.assert_frame_equal(dataset(at), clean_main)


def test_upper_by_position_and_a_bad_position_is_refused(clean_main):
    at = run_app(clean_main)
    pipeline(at).selectbox(key="case_col").set_value("Market").run()
    pipeline(at).text_input(key="case_pos").set_value("2-3").run()
    pipeline(at).radio(key="case_mode").set_value("LOWER").run()
    pipeline(at).button(key="case_apply").click().run()
    assert not at.exception, at.exception
    expected = cp.apply_case_by_position(clean_main, "Market", "2-3", "lower")
    pd.testing.assert_frame_equal(dataset(at), expected)

    pipeline(at).text_input(key="case_pos").set_value("abc").run()
    pipeline(at).button(key="case_apply").click().run()
    assert at.toast
    pd.testing.assert_frame_equal(dataset(at), expected)


def test_missing_values_and_duplicates_are_counted(typed_main):
    at = run_app(typed_main)
    n_missing = len(cp.detect_missing_values(typed_main))
    assert f"Εντοπίστηκαν {n_missing} γραμμές με τουλάχιστον μία κενή τιμή." in captions(at)
    pipeline(at).selectbox(key="dup_key_col_sel").set_value("Date").run()
    n_dup = len(cp.detect_key_duplicates(typed_main, "Date"))
    assert n_dup > 0 and f"Εντοπίστηκαν {n_dup} γραμμές." in captions(at)
    assert at.session_state["cleaning"][DATASET_NAME]["dup_key_col"] == "Date"


def test_outlier_rule_is_added_counted_and_removed(typed_main):
    at = run_app(typed_main)
    pipeline(at).selectbox(key="outlier_new_col").set_value("High").run()
    pipeline(at).text_input(key="outlier_new_max").set_value("10000").run()
    pipeline(at).button(key="outlier_add_rule_btn").click().run()
    assert not at.exception, at.exception
    rules = at.session_state["cleaning"][DATASET_NAME]["outlier_rules"]
    assert rules == [{"col": "High", "min": None, "max": 10000.0}]
    n_out = len(cp.detect_outliers(typed_main, rules))
    assert n_out == 1 and f"Εντοπίστηκαν {n_out} γραμμές." in captions(at)

    pipeline(at).button(key="outlier_rule_remove_0").click().run()
    assert at.session_state["cleaning"][DATASET_NAME]["outlier_rules"] == []


def test_outlier_rule_needs_a_valid_limit(typed_main):
    at = run_app(typed_main)
    pipeline(at).selectbox(key="outlier_new_col").set_value("High").run()
    pipeline(at).button(key="outlier_add_rule_btn").click().run()
    assert any("τουλάχιστον ένα" in w.value for w in pipeline(at).warning)
    pipeline(at).text_input(key="outlier_new_min").set_value("abc").run()
    pipeline(at).button(key="outlier_add_rule_btn").click().run()
    assert any("Μη έγκυρη τιμή ορίου." == t.value for t in at.toast)
    assert at.session_state["cleaning"][DATASET_NAME]["outlier_rules"] == []


def test_export_saves_a_separate_copy(clean_main):
    at = run_app(clean_main)
    pipeline(at).button(key="clean_export_save").click().run()
    assert not at.exception, at.exception
    copy_name = f"{DATASET_NAME} (αντίγραφο)"
    pd.testing.assert_frame_equal(at.session_state["datasets"][copy_name], clean_main)
    assert at.session_state["datasets"][copy_name] is not at.session_state["datasets"][DATASET_NAME]
