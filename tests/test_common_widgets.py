"""Screen pieces shared by several tabs: Update/Where/Set, editable tables, column picker,
WHERE filters and the CSV/Excel download buttons."""
import pandas as pd
import pytest

from conftest import DATASET_NAME, run_app
from modules import cleaning_pipeline as cp

KP = f"ga_{DATASET_NAME}_"


def _add_table(at):
    at.tabs[2].button(key=f"{KP}add_table_btn").click().run()
    assert not at.exception, at.exception


@pytest.mark.parametrize("where", ["pipeline", "analysis"])
def test_update_where_set_changes_the_dataset_and_can_be_undone(clean_main, where):
    at = run_app(clean_main)
    tab_index, prefix, undo_key = 1, "us_", "undo_pipeline"
    if where == "analysis":
        _add_table(at)
        tab_index, prefix, undo_key = 2, f"{KP}us_", "undo_analysis"

    def tab():  # re-read after every run: an old reference keeps stale widget states
        return at.tabs[tab_index]

    tab().selectbox(key=f"{prefix}where_col").set_value("Market").run()
    tab().text_input(key=f"{prefix}where_val").set_value("= LME").run()
    tab().selectbox(key=f"{prefix}set_col").set_value("Note").run()
    tab().text_input(key=f"{prefix}set_val").set_value("ελεγμένο").run()
    tab().button(key=f"{prefix}apply").click().run()
    assert not at.exception, at.exception

    expected, n = cp.apply_update_set(clean_main, "Market", False, "= LME", "Note", False, "ελεγμένο")
    assert n == int((clean_main["Market"] == "LME").sum()) > 0
    pd.testing.assert_frame_equal(at.session_state["datasets"][DATASET_NAME], expected)
    assert at.session_state["undo_stack"][DATASET_NAME][-1]["description"].startswith("Update/Where/Set: SET Note WHERE Market")

    tab().button(key=undo_key).click().run()
    pd.testing.assert_frame_equal(at.session_state["datasets"][DATASET_NAME], clean_main)


def test_null_filter_limits_the_editable_table_to_rows_with_gaps_in_that_column(typed_main):
    at = run_app(typed_main)
    at.tabs[1].selectbox(key="mv_filter").set_value("Open").run()
    at.tabs[1].checkbox(key="mv_select_all").check().run()
    at.tabs[1].button(key="mv_delete").click().run()
    assert not at.exception, at.exception
    after = at.session_state["datasets"][DATASET_NAME]
    assert len(after) == len(typed_main) - int(typed_main["Open"].isna().sum())
    assert not after["Open"].isna().any()


def test_column_picker_none_and_all(clean_main):
    at = run_app(clean_main)
    at.tabs[2].button(key=f"{KP}builder_selectnone").click().run()
    assert at.session_state["group_analysis"][DATASET_NAME]["builder_cols"] == []
    assert at.tabs[2].button(key=f"{KP}add_table_btn").disabled
    at.tabs[2].button(key=f"{KP}builder_selectall").click().run()
    assert at.session_state["group_analysis"][DATASET_NAME]["builder_cols"] == list(clean_main.columns)


def test_where_filter_is_saved_with_the_new_table(clean_main):
    at = run_app(clean_main)
    bkp = f"{KP}builder_"
    at.tabs[2].button(key=f"{bkp}addf").click().run()
    at.tabs[2].selectbox(key=f"{bkp}f_col_0").set_value("Market").run()
    at.tabs[2].selectbox(key=f"{bkp}f_op_0").set_value("=").run()
    at.tabs[2].selectbox(key=f"{bkp}f_val_0").set_value("LME").run()
    _add_table(at)
    [table] = at.session_state["group_analysis"][DATASET_NAME]["tables"]
    assert [(f["col"], f["op"], f["val"]) for f in table["filters"]] == [("Market", "=", "LME")]
    assert set(table["result_df"]["Market"]) == {"LME"}


def test_where_filter_can_be_removed_again(clean_main):
    at = run_app(clean_main)
    bkp = f"{KP}builder_"
    at.tabs[2].button(key=f"{bkp}addf").click().run()
    assert len(at.session_state["group_analysis"][DATASET_NAME]["builder_filters"]) == 1
    at.tabs[2].button(key=f"{bkp}rmf").click().run()
    assert at.session_state["group_analysis"][DATASET_NAME]["builder_filters"] == []


def _downloads(at):
    return {d.proto.id.rsplit("-", 1)[-1]: d.proto.label for d in at.get("download_button")}


def test_download_buttons_in_pipeline_export_and_analysis_result(clean_main):
    at = run_app(clean_main)
    _add_table(at)
    downloads = _downloads(at)
    assert downloads["clean_export_csv"] == "Λήψη ως CSV"
    assert downloads["clean_export_xlsx"] == "Λήψη ως Excel"
    assert downloads[f"{KP}t1_export_csv"] == "Λήψη ως CSV"
    assert downloads[f"{KP}t1_export_xlsx"] == "Λήψη ως Excel"
