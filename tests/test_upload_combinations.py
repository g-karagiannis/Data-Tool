"""Combination paths not covered in test_upload.py: Set Operators, Hub-and-Spoke, a refused
join key, and files that load immediately (SQL)."""
import pandas as pd
from streamlit.testing.v1 import AppTest

from conftest import APP_PATH, JOIN_FILE, MAIN_FILE, load_like_the_app
from modules import combiner as cb
from modules import data_loader as dl

MAIN, JOIN = MAIN_FILE.name, JOIN_FILE.name
JOIN_MORE = ("join_more.csv", b"Market,Exchange,Currency\nLME,London Metal Exchange,USD\nMCX,Multi Commodity Exchange,INR\n")
JOIN_LAST = ("join_last.csv", b"Market,Exchange,Currency\nSGX,Singapore Exchange,SGD\n")
REGIONS = ("regions.csv", b"Market,Region\nLME,Europe\nCOMEX,America\n")
RATES = ("rates.csv", b"Currency,rate\nUSD,1.0\nCNY,0.14\n")


def start(files, ticked):
    at = AppTest.from_file(str(APP_PATH), default_timeout=120)
    at.run()
    at.file_uploader(key="file_uploader_0").set_value([(n, c, "text/csv") for n, c in files]).run()
    for name in ticked:
        at.checkbox(key=f"combine_{name}").check().run()
    at.button(key="load_all").click().run()
    assert not at.exception, at.exception
    return at


def loaded(name, content):
    raw, _, _ = dl.read_raw_csv(content)
    return dl.build_dataframe_from_raw(raw, 0, 0, True, list(dl.DEFAULT_PRIVACY_SYMBOLS))


def label(names, technique, structure=False):
    return cb.build_combined_label([cb.strip_extension(n) for n in names], technique, is_structure=structure)


def test_two_files_set_operator_union():
    files = [(JOIN, JOIN_FILE.read_bytes()), JOIN_MORE]
    at = start(files, [JOIN, JOIN_MORE[0]])
    at.radio(key="combine2_type").set_value("Set Operator").run()
    at.selectbox(key="combine2_setop_technique").set_value("Union").run()
    at.button(key="combine2_setop_apply").click().run()
    assert not at.exception, at.exception
    expected = cb.apply_set_operator([load_like_the_app(JOIN_FILE), loaded(*JOIN_MORE)], "Union")
    result = at.session_state["datasets"][label([JOIN, JOIN_MORE[0]], "Union")]
    # UNION removes duplicates and, in SQL, promises no row order: compare the rows as a set.
    by_rows = lambda df: df.sort_values(list(df.columns)).reset_index(drop=True)  # noqa: E731
    pd.testing.assert_frame_equal(by_rows(result), by_rows(expected))
    assert len(result) == 4  # LME appears in both files but only once in the union


def test_three_files_set_operator_union_all_in_tick_order():
    files = [(JOIN, JOIN_FILE.read_bytes()), JOIN_MORE, JOIN_LAST]
    at = start(files, [JOIN_LAST[0], JOIN, JOIN_MORE[0]])
    at.selectbox(key="combineN_setop_technique").set_value("Union All").run()
    at.button(key="combineN_setop_apply").click().run()
    assert not at.exception, at.exception
    expected = cb.apply_set_operator([loaded(*JOIN_LAST), load_like_the_app(JOIN_FILE), loaded(*JOIN_MORE)], "Union All")
    names = [JOIN_LAST[0], JOIN, JOIN_MORE[0]]
    pd.testing.assert_frame_equal(at.session_state["datasets"][label(names, "Union All")], expected)


def test_hub_and_spoke_joins_every_spoke_to_the_hub():
    files = [(MAIN, MAIN_FILE.read_bytes()), (JOIN, JOIN_FILE.read_bytes()), REGIONS]
    at = start(files, [MAIN, JOIN, REGIONS[0]])
    at.radio(key="combineN_scope").set_value("Join").run()
    at.radio(key="combineN_structure").set_value("Hub-and-Spoke").run()
    at.selectbox(key="hub_pick").set_value(MAIN).run()
    at.button(key="hub_start").click().run()
    for step in (1, 2):
        at.selectbox(key=f"wizard_keyleft_{step}").set_value("Market").run()
        at.selectbox(key=f"wizard_keyright_{step}").set_value("Market").run()
        at.button(key=f"wizard_confirm_{step}").click().run()
    at.run()
    assert not at.exception, at.exception
    combined = at.session_state["datasets"][label([MAIN, JOIN, REGIONS[0]], "Hub-and-Spoke", structure=True)]
    assert len(combined) == len(load_like_the_app(MAIN_FILE))
    assert {"Exchange", "Region"} <= set(combined.columns)


def test_join_keys_of_different_types_are_refused():
    files = [(MAIN, MAIN_FILE.read_bytes()), RATES]
    at = start(files, [MAIN, RATES[0]])
    at.selectbox(key="combine2_key1").set_value("Market").run()
    at.selectbox(key="combine2_key2").set_value("rate").run()
    at.button(key="combine2_join_apply").click().run()
    assert not at.exception, at.exception
    assert any("Ασύμβατοι τύποι" in t.value for t in at.toast)
    assert at.session_state["batch"] is not None
    assert not at.session_state["datasets"]


def test_sql_file_loads_immediately_without_the_load_button():
    at = AppTest.from_file(str(APP_PATH), default_timeout=120)
    at.run()
    at.file_uploader(key="file_uploader_0").set_value([("q.sql", b"SELECT 42 AS answer", "text/plain")]).run()
    assert not at.exception, at.exception
    assert not at.session_state["pending_uploads"]
    result = at.session_state["datasets"]["q.sql [αποτέλεσμα_1]"]
    assert result["answer"].tolist() == [42]
