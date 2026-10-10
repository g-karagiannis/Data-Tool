"""Every tab opens with the test file, and undo restores the dataset."""
import pytest

from conftest import DATASET_NAME, run_app

TAB_LABELS = ["View", "Pipeline", "Analysis", "Workshop"]


@pytest.mark.parametrize("fixture_name", ["raw_main", "typed_main", "clean_main"])
def test_all_tabs_open_without_errors(request, fixture_name):
    at = run_app(request.getfixturevalue(fixture_name))
    assert [t.label for t in at.tabs] == TAB_LABELS


def test_sidebar_has_no_visible_columns_section(clean_main):
    at = run_app(clean_main)
    assert not any("Ορατές στήλες" in e.label for e in at.sidebar.expander)
    assert not any((cb.key or "").startswith("colvis_") for cb in at.sidebar.checkbox)
    assert [h.value for h in at.sidebar.header] == [
        "1. Φόρτωση δεδομένων", "2. Ενεργό σύνολο δεδομένων", "3. Ιστορικό αλλαγών",
    ]


def test_view_and_analysis_show_every_column(clean_main):
    at = run_app(clean_main)
    for tab in (at.tabs[0], at.tabs[2]):
        assert list(tab.dataframe[0].value.columns) == list(clean_main.columns)


def test_added_column_shows_in_history_and_is_undone(clean_main):
    at = run_app(clean_main)
    at.tabs[1].selectbox(key="concat_col1").set_value("Market").run()
    at.tabs[1].selectbox(key="concat_col2").set_value("Note").run()
    at.tabs[1].text_input(key="concat_new_name").set_value("market_note").run()
    at.tabs[1].button(key="concat_apply").click().run()
    assert not at.exception, at.exception
    assert "market_note" in at.session_state["datasets"][DATASET_NAME].columns
    history = [d.value for d in at.sidebar.dataframe if "Αλλαγή" in d.value.columns]
    assert history and history[0]["Αλλαγή"].str.contains("market_note").any()

    at.tabs[1].button(key="undo_pipeline").click().run()
    assert not at.exception, at.exception
    assert list(at.session_state["datasets"][DATASET_NAME].columns) == list(clean_main.columns)
