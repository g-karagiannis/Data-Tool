"""File upload: one "Φόρτωση" button, opt-in combination in tick order, 10MB total limit
(200MB per .zip/.dat file)."""
import io

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from conftest import APP_PATH, JOIN_FILE, MAIN_FILE, load_like_the_app
from modules import combiner as cb
from modules import upload_plan as up

MAIN = MAIN_FILE.name
JOIN = JOIN_FILE.name
RATES = "rates.csv"
RATES_BYTES = b"Currency,rate\nUSD,1.0\nCNY,0.14\n"


# ---------------------------------------------------------------- rules (no UI)

def test_tick_order_is_kept_and_new_ticks_go_last():
    order = up.update_combine_order([], ["b.csv"])
    order = up.update_combine_order(order, ["a.csv", "b.csv"])
    assert order == ["b.csv", "a.csv"]
    order = up.update_combine_order(order, ["a.csv", "b.csv", "c.csv"])
    assert order == ["b.csv", "a.csv", "c.csv"]
    assert up.update_combine_order(order, ["a.csv", "c.csv"]) == ["a.csv", "c.csv"]


def test_plan_splits_ticked_and_unticked_files():
    plan = up.plan_load({"a.csv": 10, "b.csv": 10, "c.csv": 10}, ["c.csv", "a.csv"])
    assert plan["error"] is None
    assert plan["combine"] == ["c.csv", "a.csv"]
    assert plan["separate"] == ["b.csv"]
    assert plan["total_bytes"] == 30


def test_plan_needs_two_ticked_files_or_none():
    assert up.plan_load({"a.csv": 1, "b.csv": 1}, ["a.csv"])["error"]
    assert up.plan_load({"a.csv": 1, "b.csv": 1}, [])["error"] is None


def test_plan_refuses_more_than_10mb_in_total():
    limit = up.MAX_TOTAL_UPLOAD_BYTES
    assert limit == 10 * 1024 * 1024
    assert up.plan_load({"a.csv": limit // 2, "b.csv": limit // 2}, [])["error"] is None
    assert "10" in up.plan_load({"a.csv": limit // 2, "b.csv": limit // 2 + 1}, [])["error"]


def test_each_file_type_has_its_own_size_limit():
    mb = 1024 * 1024
    assert up.size_limit("a.csv") == up.size_limit("a.PDF") == up.size_limit("a.sql") == 10 * mb
    assert up.size_limit("a.zip") == up.size_limit("a.DAT") == up.MAX_LARGE_FILE_BYTES == 200 * mb
    assert up.file_too_large("a.csv", 10 * mb) is None
    assert "a.csv" in up.file_too_large("a.csv", 10 * mb + 1)
    assert up.file_too_large("a.zip", 200 * mb) is None
    assert up.file_too_large("a.zip", 200 * mb + 1)


def test_plan_refuses_a_second_combination_while_one_is_open():
    plan = up.plan_load({"a.csv": 1, "b.csv": 1}, ["a.csv", "b.csv"], combination_in_progress=True)
    assert plan["error"]
    assert up.plan_load({"a.csv": 1}, [], combination_in_progress=True)["error"] is None


def test_only_csv_excel_and_zip_go_through_the_load_settings():
    assert up.is_combinable("x.CSV") and up.is_combinable("x.xlsx") and up.is_combinable("x.xls")
    assert up.is_combinable("x.zip")
    assert not up.is_combinable("x.pdf") and not up.is_combinable("x.px") and not up.is_combinable("x.sql")


# ---------------------------------------------------------------- the real screen

def empty_app():
    at = AppTest.from_file(str(APP_PATH), default_timeout=120)
    at.run()
    return at


def upload(at, files):
    at.file_uploader(key="file_uploader_0").set_value(
        [(name, content, "text/csv") for name, content in files]
    ).run()
    assert not at.exception, at.exception


def tick(at, *names):
    for name in names:
        at.checkbox(key=f"combine_{name}").check().run()
        assert not at.exception, at.exception


def press_load(at):
    at.button(key="load_all").click().run()
    assert not at.exception, at.exception


def test_one_load_button_replaces_the_per_file_buttons():
    at = empty_app()
    upload(at, [(MAIN, MAIN_FILE.read_bytes()), (JOIN, JOIN_FILE.read_bytes())])
    assert not [b for b in at.button if (b.key or "").startswith("confirm_")]
    assert at.button(key="load_all").label == "Φόρτωση"


def test_unticked_files_become_separate_datasets():
    at = empty_app()
    upload(at, [(MAIN, MAIN_FILE.read_bytes()), (JOIN, JOIN_FILE.read_bytes())])
    press_load(at)
    datasets = at.session_state["datasets"]
    assert set(datasets) == {MAIN, JOIN}
    pd.testing.assert_frame_equal(datasets[MAIN], load_like_the_app(MAIN_FILE))
    assert at.session_state["batch"] is None
    assert not at.session_state["pending_uploads"]


def test_ticked_files_are_combined_in_tick_order_and_the_rest_load_separately():
    at = empty_app()
    upload(at, [(MAIN, MAIN_FILE.read_bytes()), (JOIN, JOIN_FILE.read_bytes()), (RATES, RATES_BYTES)])
    tick(at, JOIN, MAIN)
    press_load(at)
    assert at.session_state["batch"]["names"] == [JOIN, MAIN]
    assert set(at.session_state["datasets"]) == {RATES}

    at.selectbox(key="combine2_key1").set_value("Market").run()
    at.selectbox(key="combine2_key2").set_value("Market").run()
    assert at.selectbox(key="combine2_key1").label == f"Κλειδί από '{JOIN}'"
    at.button(key="combine2_join_apply").click().run()
    assert not at.exception, at.exception

    label = cb.build_combined_label([cb.strip_extension(JOIN), cb.strip_extension(MAIN)], "Inner", is_structure=False)
    expected = cb.apply_join(load_like_the_app(JOIN_FILE), "Market", load_like_the_app(MAIN_FILE), "Market", "Inner", 1, 2)
    pd.testing.assert_frame_equal(at.session_state["datasets"][label], expected)
    assert at.session_state["batch"] is None


def test_a_single_ticked_file_disables_load():
    at = empty_app()
    upload(at, [(MAIN, MAIN_FILE.read_bytes()), (JOIN, JOIN_FILE.read_bytes())])
    tick(at, MAIN)
    assert at.button(key="load_all").disabled
    assert any("τουλάχιστον 2" in i.value for i in at.info)


def test_more_than_10mb_in_total_loads_nothing():
    row = b"x" * 95 + b",1\n"
    big = b"text,n\n" + row * (6 * 1024 * 1024 // len(row))
    at = empty_app()
    upload(at, [("big1.csv", big), ("big2.csv", big)])
    press_load(at)
    assert not at.session_state["datasets"]
    assert set(at.session_state["pending_uploads"]) == {"big1.csv", "big2.csv"}
    assert any("10" in t.value and "MB" in t.value for t in at.toast)


def test_a_csv_over_10mb_is_refused_before_it_is_read():
    row = b"x" * 95 + b",1\n"
    big = b"text,n\n" + row * (11 * 1024 * 1024 // len(row))
    at = empty_app()
    upload(at, [("big.csv", big), (MAIN, MAIN_FILE.read_bytes())])
    assert set(at.session_state["pending_uploads"]) == {MAIN}
    assert any("big.csv" in e.value and "10.0MB" in e.value for e in at.sidebar.error)


def test_an_sql_file_over_10mb_is_not_run():
    big = b"SELECT 1 AS x;\n" + b"-- padding\n" * (1024 * 1024)
    at = empty_app()
    upload(at, [("big.sql", big)])
    assert not at.session_state["datasets"]
    assert "big.sql" not in at.session_state["done_uploads"]
    assert any("big.sql" in e.value for e in at.sidebar.error)


def test_removing_a_file_from_the_uploader_removes_it_from_the_list():
    at = empty_app()
    upload(at, [(MAIN, MAIN_FILE.read_bytes()), (JOIN, JOIN_FILE.read_bytes())])
    tick(at, JOIN, MAIN)
    upload(at, [(MAIN, MAIN_FILE.read_bytes())])
    assert set(at.session_state["pending_uploads"]) == {MAIN}
    assert at.session_state["combine_order"] == [MAIN]


def test_chain_follows_the_tick_order_without_position_fields():
    at = empty_app()
    upload(at, [(RATES, RATES_BYTES), (JOIN, JOIN_FILE.read_bytes()), (MAIN, MAIN_FILE.read_bytes())])
    tick(at, MAIN, JOIN, RATES)
    press_load(at)
    assert at.session_state["batch"]["names"] == [MAIN, JOIN, RATES]

    at.radio(key="combineN_scope").set_value("Join").run()
    at.radio(key="combineN_structure").set_value("Chain").run()
    assert not [n for n in at.number_input if (n.key or "").startswith("chain_pos_")]
    at.button(key="chain_start").click().run()
    at.selectbox(key="wizard_keyleft_1").set_value("Market").run()
    at.selectbox(key="wizard_keyright_1").set_value("Market").run()
    at.button(key="wizard_confirm_1").click().run()
    at.selectbox(key="wizard_keyleft_2").set_value("Currency").run()
    at.selectbox(key="wizard_keyright_2").set_value("Currency").run()
    at.button(key="wizard_confirm_2").click().run()
    at.run()
    assert not at.exception, at.exception

    label = cb.build_combined_label([cb.strip_extension(n) for n in (MAIN, JOIN, RATES)], "Chain", is_structure=True)
    combined = at.session_state["datasets"][label]
    assert len(combined) == len(load_like_the_app(MAIN_FILE))
    assert {"Exchange", "Currency", "rate"} <= set(combined.columns)


def test_unticked_excel_loads_one_sheet_per_load_until_all_are_loaded():
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        pd.DataFrame({"a": [1, 2]}).to_excel(writer, sheet_name="A", index=False)
        pd.DataFrame({"b": [3, 4]}).to_excel(writer, sheet_name="B", index=False)
    at = empty_app()
    upload(at, [("book.xlsx", buffer.getvalue())])
    press_load(at)
    assert set(at.session_state["datasets"]) == {"book.xlsx [A]"}
    assert "book.xlsx" in at.session_state["pending_uploads"]
    press_load(at)
    assert set(at.session_state["datasets"]) == {"book.xlsx [A]", "book.xlsx [B]"}
    assert not at.session_state["pending_uploads"]
