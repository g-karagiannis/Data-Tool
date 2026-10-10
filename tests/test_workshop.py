"""Workshop: running code on copies, show(), save_table(), downloads, the command manual,
and the tab itself."""
import io
import re

import numpy as np
import pandas as pd
import pytest

from conftest import DATASET_NAME, PROJECT_ROOT, run_app
from modules import econometrics as ec
from modules import query_builder as qb
from modules import workshop as ws

MANUAL = PROJECT_ROOT / "docs" / "workshop_εντολές.md"
KP = f"ga_{DATASET_NAME}_"


def namespace_for(df, saved=None, shown=None):
    saved = saved if saved is not None else {}
    shown = shown if shown is not None else []
    return ws.build_namespace({DATASET_NAME: df}, {}, df,
                              show=lambda obj, title=None: shown.append(ws.classify(obj)),
                              save_table=lambda name, frame: saved.__setitem__(name, frame))


# ---------------------------------------------------------------- running code (no UI)

def test_print_output_is_captured(clean_main):
    out = ws.run_code("print('γραμμές:', len(df))", namespace_for(clean_main))
    assert out == {"stdout": f"γραμμές: {len(clean_main)}\n", "error": None}


def test_errors_show_the_users_line_and_keep_earlier_output(clean_main):
    out = ws.run_code("print('πριν')\nx = 1 / 0\n", namespace_for(clean_main))
    assert out["stdout"] == "πριν\n"
    assert "ZeroDivisionError" in out["error"] and 'line 2' in out["error"]
    assert "modules" not in out["error"]  # only the user's code, not the app's internals


def test_syntax_errors_are_reported():
    out = ws.run_code("print(", namespace_for(pd.DataFrame()))
    assert "SyntaxError" in out["error"] and out["stdout"] == ""


def test_code_works_on_copies(clean_main):
    original = clean_main.copy()
    ws.run_code("df['Price'] = 0\ndatasets[next(iter(datasets))].drop(columns=['Price'], inplace=True)",
                namespace_for(clean_main))
    pd.testing.assert_frame_equal(clean_main, original)


def test_classify_tables_charts_and_text():
    import matplotlib.pyplot as plt
    import plotly.express as px

    frame = pd.DataFrame({"a": [1, 2]})
    assert ws.classify(frame)[0] == "table"
    assert ws.classify(frame["a"])[0] == "table"
    assert ws.classify(px.line(frame, y="a"))[0] == "plotly"
    fig, ax = plt.subplots()
    assert ws.classify(fig) == ("matplotlib", fig) and ws.classify(ax) == ("matplotlib", fig)
    plt.close(fig)
    assert ws.classify(123) == ("text", "123")


def test_downloads_are_real_files():
    import matplotlib.pyplot as plt
    import plotly.express as px

    frame = pd.DataFrame({"α": [1.5, 2.5], "β": ["x", "y"]})
    files = ws.table_downloads(frame)
    assert files["csv"].decode("utf-8-sig").startswith("α,β")
    pd.testing.assert_frame_equal(pd.read_excel(io.BytesIO(files["xlsx"])), frame)
    assert b"<table" in files["html"]
    assert b"plotly" in ws.plotly_html(px.line(frame, y="α"))
    fig, ax = plt.subplots()
    ax.plot([1, 2, 3])
    assert ws.matplotlib_image(fig, "png").startswith(b"\x89PNG")
    assert ws.matplotlib_image(fig, "pdf").startswith(b"%PDF")
    plt.close(fig)


def test_ready_made_volatility_and_moving_average(clean_main):
    hv = ws.historical_volatility(clean_main["Price"], clean_main["Date"], window=20)
    pd.testing.assert_series_equal(hv, ec.historical_volatility(clean_main["Price"], clean_main["Date"], window=20))
    by_rows = ws.moving_average(clean_main["Price"], window=5)
    np.testing.assert_allclose(by_rows.to_numpy(), clean_main["Price"].rolling(5).mean().to_numpy(), equal_nan=True)


# ---------------------------------------------------------------- save_table rules (no UI)

def test_save_table_adds_replaces_and_refuses():
    container = qb.new_container_state()
    container["tables"].append(qb.new_table(1, "Πίνακας 1", ["a"], []))
    container["next_num"] = 2
    frame = pd.DataFrame({"x": [1]})

    assert qb.save_snapshot_table(container, "OLS", frame) is None
    assert qb.is_snapshot(container["tables"][-1]) and container["next_num"] == 3
    assert qb.save_snapshot_table(container, "OLS", pd.DataFrame({"x": [2]})) is None
    assert len(container["tables"]) == 2 and container["tables"][-1]["result_df"]["x"].tolist() == [2]

    assert "Analysis" in qb.save_snapshot_table(container, "Πίνακας 1", frame)
    assert "αυτόματα" in qb.save_snapshot_table(container, "Πίνακας 7", frame)
    assert qb.save_snapshot_table(container, "  ", frame)
    assert qb.save_snapshot_table(container, "x", [1, 2])
    for i in range(qb.MAX_TABLES - 2):
        assert qb.save_snapshot_table(container, f"t{i}", frame) is None
    assert "10" in qb.save_snapshot_table(container, "ένα ακόμα", frame)
    assert qb.MAX_TABLES == 10


# ---------------------------------------------------------------- the command manual works

def test_manual_documents_every_ready_made_name():
    names = [n for n in ws.build_namespace({}, {}, pd.DataFrame(), show=None, save_table=None) if n != "__name__"]
    manual = MANUAL.read_text(encoding="utf-8")
    assert [n for n in names if f"`{n}" not in manual] == []


MANUAL_EXAMPLES = re.findall(r"```python\n(.*?)```", MANUAL.read_text(encoding="utf-8"), flags=re.S)


@pytest.mark.parametrize("code", MANUAL_EXAMPLES, ids=[f"example_{i + 1}" for i in range(len(MANUAL_EXAMPLES))])
def test_every_manual_example_runs_on_the_test_file(clean_main, code):
    shown, saved = [], {}
    out = ws.run_code(code, namespace_for(clean_main, saved=saved, shown=shown))
    assert out["error"] is None, out["error"]
    assert out["stdout"] or shown or saved


# ---------------------------------------------------------------- the tab

def workshop(at):
    return at.tabs[3]


def run_code_in_tab(at, code):
    workshop(at).text_area(key="workshop_code").set_value(code).run()
    workshop(at).button(key="workshop_run").click().run()
    assert not at.exception, at.exception


def test_tab_runs_the_starter_code(clean_main):
    at = run_app(clean_main)
    assert at.tabs[3].label == "Workshop"
    assert "show(df.head())" in workshop(at).text_area(key="workshop_code").value
    workshop(at).button(key="workshop_run").click().run()
    assert not at.exception, at.exception
    assert any(c.value == f"{clean_main.shape}" for c in workshop(at).code)
    pd.testing.assert_frame_equal(workshop(at).dataframe[-1].value, clean_main.head(), check_dtype=False)


def test_results_stay_until_the_next_run(clean_main):
    at = run_app(clean_main)
    run_code_in_tab(at, "print('μία φορά')")
    first = at.session_state["workshop_result"]
    workshop(at).selectbox(key="workshop_view_table").set_value("(Ενεργό σύνολο δεδομένων)").run()
    at.tabs[1].button(key="trim_apply").click().run()
    assert at.session_state["workshop_result"] is first
    assert any(c.value == "μία φορά" for c in workshop(at).code)


def test_errors_are_shown_in_the_tab(clean_main):
    at = run_app(clean_main)
    run_code_in_tab(at, "df['δεν υπάρχει']")
    assert any("σφάλμα" in e.value for e in workshop(at).error)
    assert any("KeyError" in c.value for c in workshop(at).code)


def test_charts_get_their_downloads(clean_main):
    at = run_app(clean_main)
    run_code_in_tab(at, (
        "show(px.line(df, x='Date', y='Price'), title='τιμή')\n"
        "import matplotlib.pyplot as plt\n"
        "fig, ax = plt.subplots(); ax.plot(df['Price'].to_numpy())\n"
        "show(fig, title='matplotlib')\n"
    ))
    downloads = {d.proto.label for d in at.get("download_button")}
    assert {"Λήψη HTML (διαδραστικό)", "Λήψη PNG", "Λήψη PDF"} <= downloads
    kinds = [item["kind"] for item in at.session_state["workshop_result"]["items"]]
    assert kinds == ["plotly", "matplotlib"]


def test_saved_table_appears_everywhere_and_is_view_only_in_analysis(clean_main):
    at = run_app(clean_main)
    run_code_in_tab(at, "save_table('Μέσες τιμές', df.groupby('Market', as_index=False)['Price'].mean())")
    [table] = at.session_state["group_analysis"][DATASET_NAME]["tables"]
    assert table["name"] == "Μέσες τιμές" and qb.is_snapshot(table)
    expected = clean_main.groupby("Market", as_index=False)["Price"].mean()
    assert "Μέσες τιμές" in workshop(at).selectbox(key="workshop_view_table").options
    assert any("αποθηκεύτηκε" in s.value for s in workshop(at).success)

    analysis = at.tabs[2]
    assert analysis.selectbox(key=f"{KP}active_table_sel").value == "Μέσες τιμές"
    assert not [e for e in analysis.expander if e.label == "Προσθήκη νέας window function"]
    pd.testing.assert_frame_equal(analysis.dataframe[-1].value, expected, check_dtype=False)
    keys = {d.proto.id.rsplit("-", 1)[-1] for d in at.get("download_button")}
    assert f"{KP}t1_export_csv" in keys

    analysis.button(key=f"{KP}del_table_btn").click().run()
    assert at.session_state["group_analysis"][DATASET_NAME]["tables"] == []


def test_code_can_be_loaded_from_a_file_and_downloaded(clean_main):
    at = run_app(clean_main)
    workshop(at).file_uploader(key="workshop_code_file").set_value(
        ("ανάλυση.py", "print('από αρχείο')\n".encode("utf-8"), "text/x-python")
    ).run()
    assert not at.exception, at.exception
    assert workshop(at).text_area(key="workshop_code").value == "print('από αρχείο')\n"
    assert "Λήψη κώδικα (.txt)" in {d.proto.label for d in at.get("download_button")}
