"""Shared fixtures: load the synthetic test file exactly the way the app does."""
import sys
from pathlib import Path

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from modules import cleaning_pipeline as cp  # noqa: E402
from modules import data_loader as dl  # noqa: E402

DATA_DIR = Path(__file__).resolve().parent / "data"
APP_PATH = PROJECT_ROOT / "app.py"
MAIN_FILE = DATA_DIR / "datatool_test_main.csv"
JOIN_FILE = DATA_DIR / "datatool_test_join.csv"
NUMERIC_TEXT_COLUMNS = ["Price", "Open", "High", "Low", "Vol.", "Change %"]
DATASET_NAME = "datatool_test_main.csv"


def load_like_the_app(path: Path) -> pd.DataFrame:
    """Sidebar upload with default settings: no skipped rows/columns, header
    forward-fill on, default privacy symbols."""
    raw, _sep, _enc = dl.read_raw_csv(path.read_bytes())
    return dl.build_dataframe_from_raw(raw, 0, 0, True, list(dl.DEFAULT_PRIVACY_SYMBOLS))


def run_app(df: pd.DataFrame):
    """Start the app (Streamlit AppTest) with a copy of `df` as the active dataset.
    The app edits its dataset in place, so the caller's frame must stay untouched."""
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(APP_PATH), default_timeout=120)
    at.session_state["datasets"] = {DATASET_NAME: df.copy()}
    at.session_state["active"] = DATASET_NAME
    at.run()
    assert not at.exception, at.exception
    return at


@pytest.fixture
def raw_main() -> pd.DataFrame:
    """As uploaded: prices and dates are still text (e.g. "3,405.00", "09/28/2026")."""
    return load_like_the_app(MAIN_FILE)


@pytest.fixture
def typed_main(raw_main) -> pd.DataFrame:
    """After Pipeline > Casting: number columns to float, Date to datetime. Dirty rows kept."""
    df = raw_main
    for col in NUMERIC_TEXT_COLUMNS:
        df, _ = cp.cast_column(df, col, "float")
    df, _ = cp.cast_column(df, "Date", "datetime")
    return df


@pytest.fixture
def clean_main(typed_main) -> pd.DataFrame:
    """After the user's Pipeline cleaning: no missing dates, no duplicate rows or dates.
    Keeps the file's order (newest day first)."""
    df = typed_main.dropna(subset=["Date"]).drop_duplicates()
    df = df.drop_duplicates(subset=["Date"], keep="first")
    return df.reset_index(drop=True)
