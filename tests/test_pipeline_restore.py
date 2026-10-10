"""Pipeline: "Επαναφορά στο dataset" / "Αποθήκευση αλλαγών" write the ticked rows back."""
import numpy as np
import pandas as pd
import pytest

from conftest import DATASET_NAME, run_app
from modules import cleaning_pipeline as cp


def _edited_view(df: pd.DataFrame) -> pd.DataFrame:
    """What the Pipeline editors hand back: the shown rows plus helper columns."""
    view = df.copy()
    view.insert(0, "Αιτία", "test")
    view.insert(0, "Επιλογή", False)
    return view


def test_only_ticked_rows_are_written_back(clean_main):
    edited = _edited_view(clean_main)
    edited.loc[0, "Price"] = 1.0
    edited.loc[1, "Price"] = 2.0
    result = cp.apply_row_edits(clean_main, edited, [0])
    assert result.loc[0, "Price"] == 1.0
    assert result.loc[1, "Price"] == clean_main.loc[1, "Price"]
    pd.testing.assert_frame_equal(result.drop(index=0), clean_main.drop(index=0))


def test_helper_columns_never_reach_the_dataset(clean_main):
    result = cp.apply_row_edits(clean_main, _edited_view(clean_main), list(clean_main.index))
    assert list(result.columns) == list(clean_main.columns)


def test_edits_can_clear_or_set_values_of_any_type(clean_main):
    edited = _edited_view(clean_main)
    edited.loc[3, "Open"] = np.nan
    edited.loc[3, "Date"] = pd.Timestamp("2030-01-01")
    edited.loc[3, "Note"] = "διορθώθηκε"
    result = cp.apply_row_edits(clean_main, edited, [3])
    assert np.isnan(result.loc[3, "Open"])
    assert result.loc[3, "Date"] == pd.Timestamp("2030-01-01")
    assert result.loc[3, "Note"] == "διορθώθηκε"
    assert result.dtypes.equals(clean_main.dtypes)


def test_the_input_dataset_is_not_modified(clean_main):
    before = clean_main.copy()
    edited = _edited_view(clean_main).assign(Price=0.0)
    cp.apply_row_edits(clean_main, edited, list(clean_main.index[:10]))
    pd.testing.assert_frame_equal(clean_main, before)


def test_deleted_missing_value_rows_come_back_with_undo(typed_main):
    at = run_app(typed_main)
    missing_before = int(typed_main.isna().any(axis=1).sum())
    at.tabs[1].checkbox(key="mv_select_all").check().run()
    at.tabs[1].button(key="mv_delete").click().run()
    assert not at.exception, at.exception
    assert len(at.session_state["datasets"][DATASET_NAME]) == len(typed_main) - missing_before
    at.tabs[1].button(key="undo_pipeline").click().run()
    pd.testing.assert_frame_equal(at.session_state["datasets"][DATASET_NAME], typed_main)


@pytest.mark.parametrize("prefix, button_label", [
    ("active", "Αποθήκευση αλλαγών"),
    ("mv", "Επαναφορά στο dataset"),
    ("dup", "Επαναφορά στο dataset"),
])
def test_restoring_unedited_rows_keeps_the_dataset_and_records_undo(typed_main, prefix, button_label):
    at = run_app(typed_main)
    if prefix == "dup":
        at.tabs[1].selectbox(key="dup_key_col_sel").set_value("Date").run()
    at.tabs[1].checkbox(key=f"{prefix}_select_all").check().run()
    at.tabs[1].button(key=f"{prefix}_restore").click().run()
    assert not at.exception, at.exception

    after = at.session_state["datasets"][DATASET_NAME]
    pd.testing.assert_frame_equal(after, typed_main)  # same values and same column types
    history = at.session_state["undo_stack"][DATASET_NAME]
    assert len(history) == 1 and history[0]["description"].startswith(f"{button_label} (")
