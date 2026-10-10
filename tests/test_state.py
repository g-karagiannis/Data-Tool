"""What the app remembers between reruns (session state), "Καθαρισμός όλων" and undo."""
from streamlit.testing.v1 import AppTest

from conftest import APP_PATH, DATASET_NAME, run_app

STARTUP_STATE = {
    "datasets": {},
    "active": None,
    "pending_uploads": {},
    "excel_loaded_sheets": {},
    "zip_loaded_members": {},
    "codebooks": {},
    "fixed_width_specs": {},
    "fixed_width_filters": {},
    "done_uploads": set(),
    "sql_result": None,
    "batch": None,
    "combine_order": [],
    "uploader_reset_counter": 0,
    "cleaning": {},
    "group_analysis": {},
    "undo_stack": {},
    "workshop_result": None,
    "workshop_code_saved": None,
}


def test_startup_creates_every_state_entry_with_its_default():
    at = AppTest.from_file(str(APP_PATH), default_timeout=120)
    at.run()
    assert not at.exception, at.exception
    for key, default in STARTUP_STATE.items():
        assert at.session_state[key] == default, key


def _clear_all(at):
    [button] = [b for b in at.sidebar.button if b.label == "Καθαρισμός όλων (νέα ανάλυση)"]
    button.click().run()
    assert not at.exception, at.exception


def test_clear_all_resets_data_uploads_pipeline_settings_and_tables(clean_main):
    at = run_app(clean_main)
    at.tabs[1].button(key="trim_apply").click().run()                    # one undo entry
    at.tabs[2].button(key=f"ga_{DATASET_NAME}_add_table_btn").click().run()   # one Analysis table
    assert at.session_state["undo_stack"] and at.session_state["group_analysis"]
    assert at.session_state["cleaning"]

    _clear_all(at)
    for key in ("datasets", "active", "pending_uploads", "excel_loaded_sheets", "zip_loaded_members", "codebooks", "fixed_width_specs", "fixed_width_filters", "done_uploads",
                "sql_result", "batch", "combine_order", "undo_stack", "workshop_result",
                "cleaning", "group_analysis"):
        assert at.session_state[key] == STARTUP_STATE[key], key
    assert at.session_state["uploader_reset_counter"] == 1

    # A new file with the same name starts clean: no old tables or Pipeline rules come back.
    at.session_state["datasets"] = {DATASET_NAME: clean_main.copy()}
    at.run()
    assert at.session_state["group_analysis"][DATASET_NAME]["tables"] == []
    assert at.session_state["cleaning"][DATASET_NAME]["outlier_rules"] == []


def test_clear_all_keeps_the_workshop_code(clean_main):
    at = run_app(clean_main)
    at.tabs[3].text_area(key="workshop_code").set_value("print('κράτα με')").run()
    _clear_all(at)
    at.session_state["datasets"] = {DATASET_NAME: clean_main.copy()}
    at.run()
    assert not at.exception, at.exception
    assert at.tabs[3].text_area(key="workshop_code").value == "print('κράτα με')"


def test_undo_keeps_the_last_20_changes(clean_main):
    at = run_app(clean_main)
    for _ in range(21):
        at.tabs[1].button(key="trim_apply").click().run()
    assert not at.exception, at.exception
    assert len(at.session_state["undo_stack"][DATASET_NAME]) == 20


def test_undo_removes_a_vanished_column_from_analysis_tables(clean_main):
    at = run_app(clean_main)
    at.tabs[1].selectbox(key="concat_col1").set_value("Market").run()
    at.tabs[1].selectbox(key="concat_col2").set_value("Note").run()
    at.tabs[1].text_input(key="concat_new_name").set_value("market_note").run()
    at.tabs[1].button(key="concat_apply").click().run()
    at.tabs[2].button(key=f"ga_{DATASET_NAME}_add_table_btn").click().run()
    [table] = at.session_state["group_analysis"][DATASET_NAME]["tables"]
    assert "market_note" in table["selected_cols"]

    at.tabs[1].button(key="undo_pipeline").click().run()
    assert not at.exception, at.exception
    assert "market_note" not in at.session_state["datasets"][DATASET_NAME].columns
    [table] = at.session_state["group_analysis"][DATASET_NAME]["tables"]
    assert "market_note" not in table["selected_cols"]
    assert table["error"] is None
