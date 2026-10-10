"""Generate the synthetic test files in this folder (fixed seed: identical output on every run).

Run from the datatool folder:
    .venv\\Scripts\\python tests\\data\\make_test_data.py

datatool_test_main.csv mimics an investing.com price export: newest day first,
dates like "09/28/2026", prices like "3,405.00", volume like "0.04K", change like
"-1.48%". It adds the columns and dirty rows the other tabs need (category, messy
text, missing values, outliers, an exact duplicate row, a duplicate date with a
different price, a row without a date). datatool_test_join.csv is a small lookup
table for the Join/combine flow; its SHFE row has no match in the main file.
"""
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
MAIN_FILE = "datatool_test_main.csv"
JOIN_FILE = "datatool_test_join.csv"

SEED = 20261007
N_DAYS = 300
FIRST_DAY = "2025-06-02"
START_PRICE = 2600.0

# GARCH(1,1) daily returns so volatility clusters (long-run daily sigma = 1%).
GARCH_OMEGA, GARCH_ALPHA, GARCH_BETA = 2e-6, 0.08, 0.90

# Dirty rows, identified by the (clean) date they relate to.
EXACT_DUPLICATE_DATE = "2026-03-10"
DUPLICATE_DATE = "2026-01-15"
DUPLICATE_DATE_PRICE_SHIFT = 12.5
MISSING_DATE_PRICE = 3001.0
MISSING_OPEN_DATES = ["2025-07-07", "2025-11-03", "2026-05-18"]
MISSING_VOL_DATES = ["2025-09-15", "2026-02-02"]
MISSING_NOTE_DATES = ["2025-08-11", "2026-06-22"]
OUTLIER_HIGH = {"2025-10-20": 99999.0, "2026-04-14": 0.5}

NOTES = ["  Spot ", "spot", "FUTURES", " Futures  ", "Forward"]
MARKETS = ["LME", "COMEX"]


def clean_series() -> pd.DataFrame:
    """The 300 clean trading days, oldest first, as numbers and real dates."""
    rng = np.random.default_rng(SEED)
    dates = pd.bdate_range(FIRST_DAY, periods=N_DAYS)

    returns = np.empty(N_DAYS)
    variance = GARCH_OMEGA / (1 - GARCH_ALPHA - GARCH_BETA)
    for i in range(N_DAYS):
        returns[i] = np.sqrt(variance) * rng.standard_normal()
        variance = GARCH_OMEGA + GARCH_ALPHA * returns[i] ** 2 + GARCH_BETA * variance
    returns[0] = 0.0
    price = np.round(START_PRICE * np.exp(np.cumsum(returns)), 2)

    prev_close = np.concatenate([[price[0]], price[:-1]])
    open_ = np.round(prev_close * (1 + rng.normal(0, 0.002, N_DAYS)), 2)
    high = np.round(np.maximum(open_, price) * (1 + np.abs(rng.normal(0, 0.003, N_DAYS))), 2)
    low = np.round(np.minimum(open_, price) * (1 - np.abs(rng.normal(0, 0.003, N_DAYS))), 2)
    volume_k = rng.integers(0, 80, N_DAYS) / 1000
    change_pct = np.round((price / prev_close - 1) * 100, 2)

    return pd.DataFrame({
        "Date": dates,
        "Price": price,
        "Open": open_,
        "High": high,
        "Low": low,
        "Vol.": volume_k,
        "Change %": change_pct,
        "Market": rng.choice(MARKETS, N_DAYS),
        "Note": rng.choice(NOTES, N_DAYS),
    })


def _as_export_text(df: pd.DataFrame) -> pd.DataFrame:
    """Format numbers and dates the way an investing.com export does."""
    out = pd.DataFrame({
        "Date": df["Date"].dt.strftime("%m/%d/%Y"),
        "Price": df["Price"].map(lambda v: f"{v:,.2f}"),
        "Open": df["Open"].map(lambda v: f"{v:,.2f}"),
        "High": df["High"].map(lambda v: f"{v:,.2f}"),
        "Low": df["Low"].map(lambda v: f"{v:,.2f}"),
        "Vol.": df["Vol."].map(lambda v: f"{v:.2f}K"),
        "Change %": df["Change %"].map(lambda v: f"{v:.2f}%"),
        "Market": df["Market"],
        "Note": df["Note"],
    })
    return out


def main_file_frame() -> pd.DataFrame:
    """The main test file as text, newest day first, with the dirty rows inserted."""
    clean = clean_series()
    text = _as_export_text(clean)

    def rows_on(day):
        return clean.index[clean["Date"] == pd.Timestamp(day)]

    for day in MISSING_OPEN_DATES:
        text.loc[rows_on(day), "Open"] = ""
    for day in MISSING_VOL_DATES:
        text.loc[rows_on(day), "Vol."] = ""
    for day in MISSING_NOTE_DATES:
        text.loc[rows_on(day), "Note"] = ""
    for day, value in OUTLIER_HIGH.items():
        text.loc[rows_on(day), "High"] = f"{value:,.2f}"

    newest_first = text.iloc[::-1].reset_index(drop=True)
    rows = []
    for _, row in newest_first.iterrows():
        rows.append(row.copy())
        day = pd.to_datetime(row["Date"], format="%m/%d/%Y")
        if day == pd.Timestamp(EXACT_DUPLICATE_DATE):
            rows.append(row.copy())
        if day == pd.Timestamp(DUPLICATE_DATE):
            other = row.copy()
            shifted = float(other["Price"].replace(",", "")) + DUPLICATE_DATE_PRICE_SHIFT
            other["Price"] = f"{shifted:,.2f}"
            rows.append(other)
        if day == pd.Timestamp("2026-04-01"):
            no_date = row.copy()
            no_date["Date"] = ""
            no_date["Price"] = f"{MISSING_DATE_PRICE:,.2f}"
            rows.append(no_date)
    return pd.DataFrame(rows).reset_index(drop=True)


def join_file_frame() -> pd.DataFrame:
    return pd.DataFrame({
        "Market": ["LME", "COMEX", "SHFE"],
        "Exchange": ["London Metal Exchange", "COMEX (CME Group)", "Shanghai Futures Exchange"],
        "Currency": ["USD", "USD", "CNY"],
    })


def write_files(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    main_file_frame().to_csv(out_dir / MAIN_FILE, index=False, lineterminator="\n")
    join_file_frame().to_csv(out_dir / JOIN_FILE, index=False, lineterminator="\n")


if __name__ == "__main__":
    write_files(HERE)
    print(f"Wrote {MAIN_FILE} and {JOIN_FILE} to {HERE}")
