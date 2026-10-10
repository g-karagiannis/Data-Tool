"""Time-series helpers used by the Workshop (historical_volatility, moving_average): they
compute in ascending date order whatever the row order.

Blanks (NaN) always fall on the oldest dates: N for Historical Volatility (window N),
N-1 for SMA, none for EMA. Results are written back to their own rows.
"""
import numpy as np
import pandas as pd
import pytest

from modules import econometrics as ec

WINDOW = 20

TOOLS = {
    "historical_volatility": lambda df: ec.historical_volatility(df["Price"], df["Date"], window=WINDOW),
    "sma": lambda df: ec.moving_average(df["Price"], df["Date"], window=WINDOW, method="SMA"),
    "ema": lambda df: ec.moving_average(df["Price"], df["Date"], window=WINDOW, method="EMA"),
}
EXPECTED_BLANKS = {"historical_volatility": WINDOW, "sma": WINDOW - 1, "ema": 0}

# Computed once from datatool_test_main.csv with the versions in requirements-lock.txt.
# A failure here after a library upgrade means the upgrade changed the numbers.
GOLDEN_LAST_DATE = pd.Timestamp("2026-07-24")
GOLDEN_HV63 = 0.143608
GOLDEN_SMA20 = 2680.653
GOLDEN_FIRST_FULL_SMA20_DATE = pd.Timestamp("2025-06-27")
GOLDEN_FIRST_FULL_SMA20 = 2533.462
SIGMA_TOLERANCE = 0.005
PRICE_TOLERANCE = 0.01


def by_date(df: pd.DataFrame, values) -> pd.Series:
    """Tool output keyed by date, oldest first."""
    return pd.Series(np.asarray(values, dtype=float), index=df["Date"].to_numpy()).sort_index()


def row_orders(df: pd.DataFrame) -> dict:
    return {
        "ascending": df.sort_values("Date").reset_index(drop=True),
        "descending": df.sort_values("Date", ascending=False).reset_index(drop=True),
        "random": df.sample(frac=1, random_state=0).reset_index(drop=True),
    }


@pytest.mark.parametrize("tool", TOOLS)
def test_same_results_in_any_row_order(clean_main, tool):
    results = {name: by_date(df, TOOLS[tool](df)) for name, df in row_orders(clean_main).items()}
    pd.testing.assert_series_equal(results["ascending"], results["descending"])
    pd.testing.assert_series_equal(results["ascending"], results["random"])


@pytest.mark.parametrize("tool", TOOLS)
def test_blanks_fall_on_the_oldest_dates(clean_main, tool):
    assert clean_main["Date"].is_monotonic_decreasing  # the file is newest-first
    result = by_date(clean_main, TOOLS[tool](clean_main))
    blanks = EXPECTED_BLANKS[tool]
    assert result.isna().sum() == blanks
    assert result.iloc[:blanks].isna().all()
    assert result.iloc[blanks:].notna().all()


def test_results_land_on_their_own_rows(clean_main):
    result = TOOLS["sma"](clean_main)
    assert result.index.equals(clean_main.index)
    oldest_rows = clean_main.nsmallest(WINDOW - 1, "Date").index
    assert result.loc[oldest_rows].isna().all()
    assert result.drop(oldest_rows).notna().all()


def test_values_match_an_independent_calculation(clean_main):
    prices = clean_main.sort_values("Date")["Price"].to_numpy()
    log_returns = np.log(prices[1:] / prices[:-1])
    n = len(prices)

    hv = by_date(clean_main, TOOLS["historical_volatility"](clean_main)).to_numpy()
    for day in range(WINDOW, n):
        expected = np.std(log_returns[day - WINDOW:day], ddof=1) * np.sqrt(252)
        assert hv[day] == pytest.approx(expected, rel=1e-9)

    sma = by_date(clean_main, TOOLS["sma"](clean_main)).to_numpy()
    for day in range(WINDOW - 1, n):
        assert sma[day] == pytest.approx(prices[day - WINDOW + 1:day + 1].mean(), rel=1e-12)


def test_golden_values(clean_main):
    newest = clean_main.index[clean_main["Date"] == GOLDEN_LAST_DATE][0]
    hv63 = ec.historical_volatility(clean_main["Price"], clean_main["Date"], window=63)
    sma20 = ec.moving_average(clean_main["Price"], clean_main["Date"], window=20, method="SMA")

    assert hv63[newest] == pytest.approx(GOLDEN_HV63, abs=SIGMA_TOLERANCE)
    assert sma20[newest] == pytest.approx(GOLDEN_SMA20, abs=PRICE_TOLERANCE)

    sma_by_date = by_date(clean_main, sma20)
    assert sma_by_date.first_valid_index() == GOLDEN_FIRST_FULL_SMA20_DATE
    assert sma_by_date[GOLDEN_FIRST_FULL_SMA20_DATE] == pytest.approx(GOLDEN_FIRST_FULL_SMA20, abs=PRICE_TOLERANCE)


@pytest.mark.parametrize("tool", TOOLS)
def test_duplicate_and_missing_dates_never_block(typed_main, tool):
    """The tools compute on what they are given; cleaning dates is the user's job in Pipeline."""
    assert typed_main["Date"].isna().any()
    assert typed_main["Date"].duplicated().any()
    result = TOOLS[tool](typed_main)
    assert len(result) == len(typed_main)
    assert result.index.equals(typed_main.index)


def test_unknown_moving_average_method_is_refused(clean_main):
    with pytest.raises(ValueError):
        ec.moving_average(clean_main["Price"], clean_main["Date"], window=5, method="WMA")
