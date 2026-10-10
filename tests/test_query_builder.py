"""Ομαδοποίηση & Ανάλυση: the GROUP BY result column name ("alias") and where it is used."""
import pandas as pd

from conftest import DATASET_NAME, run_app
from modules import query_builder as qb


def group_by_table(df: pd.DataFrame, group_col: str, value_col: str, func: str) -> dict:
    table = qb.new_table(table_id=1, name="Πίνακας 1", selected_cols=list(df.columns), filters=[])
    table["group_by"] = {"group_col": group_col, "value_col": value_col, "func": func, "date_part": None}
    return qb.execute(df, table)


def test_group_by_result_column_is_func_and_value_column(clean_main):
    result = group_by_table(clean_main, "Market", "Price", "AVG")
    assert result["error"] is None
    assert list(result["result_df"].columns) == ["Market", "avg_Price"]


def test_group_by_alias_that_clashes_with_the_group_column_gets_agg_suffix():
    df = pd.DataFrame({"count_Price": ["a", "a", "b"], "Price": [1.0, 2.0, 3.0]})
    result = group_by_table(df, "count_Price", "Price", "COUNT")
    assert result["error"] is None
    assert list(result["result_df"].columns) == ["count_Price", "count_Price_agg"]


def test_group_by_alias_rules():
    assert qb.group_by_alias({"group_col": "Market", "value_col": "Price", "func": "SUM"}) == "sum_Price"
    assert qb.group_by_alias({"group_col": "max_Price", "value_col": "Price", "func": "MAX"}) == "max_Price_agg"


def test_final_order_by_offers_the_group_by_columns(clean_main):
    at = run_app(clean_main)
    kp = f"ga_{DATASET_NAME}_"
    at.tabs[2].button(key=f"{kp}add_table_btn").click().run()
    tkp = f"{kp}t1_"
    at.tabs[2].checkbox(key=f"{tkp}gb_enable").check().run()
    at.tabs[2].selectbox(key=f"{tkp}gb_col").set_value("Market").run()
    at.tabs[2].selectbox(key=f"{tkp}gb_value").set_value("Price").run()
    at.tabs[2].selectbox(key=f"{tkp}gb_func").set_value("AVG").run()
    at.run()  # the ORDER BY options are drawn before the GROUP BY form, from the saved group_by
    assert not at.exception, at.exception
    options = list(at.tabs[2].selectbox(key=f"{tkp}orderby_0").options)
    assert options == ["(καμία)", "Market", "avg_Price"]

    at.tabs[2].selectbox(key=f"{tkp}orderby_0").set_value("avg_Price").run()
    at.tabs[2].radio(key=f"{tkp}orderdir_0").set_value("DESC").run()
    assert not at.exception, at.exception
    shown = [d.value for d in at.tabs[2].dataframe if list(d.value.columns) == ["Market", "avg_Price"]]
    assert shown and shown[0]["avg_Price"].is_monotonic_decreasing
