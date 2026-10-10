"""Tab View: data preview and the column overview (with its date tie-break choice)."""
import pandas as pd
import pytest

from conftest import run_app
from modules import data_cleaner as dc


def shown(at, position):
    return at.tabs[0].dataframe[position].value


def test_preview_shows_the_whole_dataset(clean_main):
    at = run_app(clean_main)
    pd.testing.assert_frame_equal(shown(at, 0), clean_main, check_dtype=False)


@pytest.mark.parametrize("fixture_name, tie_col", [("raw_main", None), ("clean_main", "Date")])
def test_overview_uses_the_only_date_column_or_none(request, fixture_name, tie_col):
    df = request.getfixturevalue(fixture_name)
    at = run_app(df)
    with pytest.raises(KeyError):
        at.tabs[0].selectbox(key="text_minmax_tie_col")
    pd.testing.assert_frame_equal(shown(at, 1), dc.profile(df, tie_col), check_dtype=False)


def test_overview_lets_the_user_pick_the_tie_break_date_when_there_are_two(clean_main):
    df = clean_main.assign(Settled=clean_main["Date"] + pd.Timedelta(days=2))
    at = run_app(df)
    picker = at.tabs[0].selectbox(key="text_minmax_tie_col")
    assert list(picker.options) == ["Date", "Settled"] and picker.value == "Date"
    pd.testing.assert_frame_equal(shown(at, 1), dc.profile(df, "Date"), check_dtype=False)
    picker.set_value("Settled").run()
    pd.testing.assert_frame_equal(shown(at, 1), dc.profile(df, "Settled"), check_dtype=False)
