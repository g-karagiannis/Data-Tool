"""Tab Analysis: descriptive statistics and Ομαδοποίηση & Ανάλυση tables (window functions,
switching, deleting, the table limit). GROUP BY / ORDER BY, WHERE filters, Update/Where/Set
and the column picker are covered in other test files."""
import pandas as pd
import pytest

from conftest import DATASET_NAME, run_app
from modules import analysis as an
from modules import query_builder as qb

KP = f"ga_{DATASET_NAME}_"


def analysis(at):
    return at.tabs[2]


def add_table(at):
    analysis(at).button(key=f"{KP}add_table_btn").click().run()
    assert not at.exception, at.exception


def tables(at):
    return at.session_state["group_analysis"][DATASET_NAME]["tables"]


def test_descriptive_statistics(clean_main):
    at = run_app(clean_main)
    shown = [d.value for d in analysis(at).dataframe]
    pd.testing.assert_frame_equal(shown[1], an.describe_numeric(clean_main), check_dtype=False)
    pd.testing.assert_frame_equal(shown[2], an.describe_non_numeric(clean_main), check_dtype=False)


def test_no_table_yet_shows_a_hint(clean_main):
    at = run_app(clean_main)
    assert any("Δεν έχει δημιουργηθεί ακόμα κανένα table" in i.value for i in analysis(at).info)


def test_window_function_is_added_computed_and_removed(clean_main):
    at = run_app(clean_main)
    add_table(at)
    wf = f"{KP}t1_wf0_"
    analysis(at).selectbox(key=f"{wf}new_func").set_value("AVG").run()
    analysis(at).selectbox(key=f"{wf}new_target").set_value("Price").run()
    analysis(at).selectbox(key=f"{wf}new_partition").set_value("Market").run()
    analysis(at).text_input(key=f"{wf}new_name").set_value("avg_market").run()
    analysis(at).button(key=f"{wf}add_btn").click().run()
    assert not at.exception, at.exception

    [table] = tables(at)
    assert table["window_functions"] == [{
        "agg_func": "AVG", "target_col": "Price", "partition_col": "Market", "partition_date_part": None,
        "order_col": None, "order_dir": "ASC", "new_name": "avg_market",
    }]
    result = table["result_df"].sort_values("Date").reset_index(drop=True)
    expected = clean_main.groupby("Market")["Price"].transform("mean")
    expected = pd.Series(expected.to_numpy(), index=clean_main["Date"]).sort_index().to_numpy()
    assert result["avg_market"].to_numpy() == pytest.approx(expected)
    assert table["wf_form_seq"] == 1  # the next form starts with fresh widget keys

    analysis(at).button(key=f"{KP}t1_wf_rm_0").click().run()
    assert tables(at)[0]["window_functions"] == []


def test_two_tables_switch_and_delete(clean_main):
    at = run_app(clean_main)
    add_table(at)
    add_table(at)
    assert [t["name"] for t in tables(at)] == ["Πίνακας 1", "Πίνακας 2"]
    assert analysis(at).selectbox(key=f"{KP}active_table_sel").value == "Πίνακας 2"
    analysis(at).selectbox(key=f"{KP}active_table_sel").set_value("Πίνακας 1").run()
    assert at.session_state["group_analysis"][DATASET_NAME]["active_id"] == 1

    analysis(at).button(key=f"{KP}del_table_btn").click().run()
    assert not at.exception, at.exception
    assert [t["name"] for t in tables(at)] == ["Πίνακας 2"]
    assert analysis(at).selectbox(key=f"{KP}active_table_sel").value == "Πίνακας 2"


def test_table_limit(clean_main):
    at = run_app(clean_main)
    for _ in range(qb.MAX_TABLES):
        add_table(at)
    assert len(tables(at)) == qb.MAX_TABLES
    assert analysis(at).button(key=f"{KP}add_table_btn").disabled
    assert any(f"{qb.MAX_TABLES} tables" in w.value for w in analysis(at).warning)
