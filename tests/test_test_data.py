"""The synthetic test files are reproducible and contain the rows the other tests rely on."""
import importlib.util

import pandas as pd

from conftest import DATA_DIR, JOIN_FILE, MAIN_FILE


def _generator():
    spec = importlib.util.spec_from_file_location("make_test_data", DATA_DIR / "make_test_data.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_committed_files_match_the_generator(tmp_path):
    _generator().write_files(tmp_path)
    for path in (MAIN_FILE, JOIN_FILE):
        assert (tmp_path / path.name).read_bytes() == path.read_bytes(), path.name


def test_main_file_has_the_planned_dirty_rows(typed_main):
    assert len(typed_main) == 303
    assert typed_main["Date"].isna().sum() == 1
    assert typed_main.duplicated().sum() == 1
    dated = typed_main.dropna(subset=["Date"]).drop_duplicates()
    assert dated["Date"].duplicated().sum() == 1
    assert typed_main["Open"].isna().sum() == 3
    assert typed_main["Vol."].isna().sum() == 2
    assert typed_main["Note"].isna().sum() == 2
    assert (typed_main["High"] > 10_000).sum() == 1
    assert (typed_main["High"] < 1).sum() == 1


def test_cleaning_recovers_the_generated_series(clean_main):
    expected = _generator().clean_series().iloc[::-1].reset_index(drop=True)
    assert clean_main["Date"].is_monotonic_decreasing
    pd.testing.assert_series_equal(clean_main["Date"], expected["Date"], check_names=False, check_dtype=False)
    pd.testing.assert_series_equal(clean_main["Price"], expected["Price"], check_names=False)


def test_join_file_has_one_unmatched_market(raw_main):
    join = pd.read_csv(JOIN_FILE)
    assert set(raw_main["Market"]) == {"LME", "COMEX"}
    assert set(join["Market"]) - set(raw_main["Market"]) == {"SHFE"}
