# datatool — Data Analysis Tool

An application for cleaning, analysing and modelling data. Written in **Python** with **Streamlit**,
it runs locally in the browser and your data stays on your computer.

Upload files (CSV, Excel, PDF, SQL, PC-Axis, ZIP, or fixed-width `.dat` files with their codebook),
clean them, analyse them with built-in tools or your own Python code, and download the results.

---

## Features

### Loading data
- **CSV / Excel**: automatic detection of separator and encoding (including Greek `cp1253`), skipping
  rows/columns, privacy symbols (`*`, `..`, `N/A` …) turned into blanks, preview before loading.
- **PDF** (table extraction), **SQL scripts** (via DuckDB), **PC-Axis `.px`** (statistical offices).
- **ZIP**: pick which file inside to load; the size limit is checked on the uncompressed size, before
  anything is unzipped.
- **Fixed-width `.dat` files** (e.g. the Medical Expenditure Panel Survey):
  - the app reads the **codebook PDF** from the same zip and lists every variable, with search and
    tick boxes — no character positions to type;
  - it checks that the codebook covers the whole line of the file, with no gaps or overlaps;
  - it loads only the columns you picked, with optional row filters (e.g. `AGE ≥ 18`);
  - every value is exactly the characters at its position — no conversion that could alter the data.
- **Combining files**: Join, set operators (UNION, INTERSECT …), Chain and Hub-and-Spoke for 3+ files.

### Cleaning (Pipeline)
- Edit values in the table, Update / Where / Set.
- Type conversion (text, number, date), TRIM, CONCAT, upper/lower case.
- Missing values, duplicates, outliers.
- **Undo** up to 20 steps and a history of every change.
- Download as CSV / Excel.

### Analysis
- Descriptive statistics for every column.
- Up to 10 analysis tables per dataset: column choice, filters, window functions, sorting, GROUP BY.
- **Advanced (SQL)**: free SQL on the data.

### Workshop: free Python code
- Code runs on **copies** of the data — nothing breaks in the other tabs.
- Ready-to-use libraries: pandas, numpy, Plotly, statsmodels, linearmodels, pyfixest, arch.
- `show(...)` for tables, charts and model results, with downloads (CSV, Excel, HTML, PNG, PDF).
- `save_table(...)` keeps a result as a table of the app.
- Built-in command manual with examples (regression, logit, panel, GARCH, charts).

### Language
Greek interface with an **ΕΛ | EN** switch at the top right. The English translation of the screens
is in progress.

---

## Technologies

| Area | Libraries |
|---|---|
| Application | Streamlit |
| Data | pandas, numpy, DuckDB |
| Files | openpyxl, xlrd, pdfplumber, pypdfium2, pyaxis |
| Statistics & econometrics | statsmodels, linearmodels, pyfixest, arch, scipy |
| Charts | Plotly, matplotlib |
| Testing | pytest, Streamlit AppTest |

All versions are pinned in `requirements-lock.txt`, so the app behaves the same on every computer.

---

## Installation and start (Windows)

1. Install **Python 3.13** from [python.org](https://www.python.org/downloads/), ticking
   "Add python.exe to PATH".
2. Double-click **`start_windows.bat`**.

The first time, it creates an isolated environment (`.venv`) and installs the libraries; then the
browser opens at `http://localhost:8501`. Detailed user instructions (in Greek): [ΟΔΗΓΙΕΣ.md](ΟΔΗΓΙΕΣ.md).

The app accepts connections **only from the same computer** (`server.address = "localhost"`),
because the Workshop runs free code.

---

## Code structure

```
app.py                 entry point: page, sidebar, tabs
ui/                    screens (loading, sidebar, tabs, SQL) and the session state
modules/               logic: plain functions on data, no Streamlit
  data_loader.py         reading files and zips
  fixed_width.py         fixed-width files, types, row filters
  codebook.py            reading and checking codebook PDFs
  cleaning_pipeline.py   cleaning
  query_builder.py       analysis tables (via DuckDB)
  combiner.py            combining files
  workshop.py            running code and downloads
  i18n.py, texts/        texts in Greek and English
styles/app.css         styling
docs/                  Workshop command manual
tests/                 automated tests and synthetic test data
```

The logic (`modules/`) does not depend on Streamlit — an automated test enforces this — so it can be
tested and reused independently of the screens.

---

## Tests

**197 automated tests**: logic, full app screens (via Streamlit AppTest), and architecture rules.
They use synthetic data only.

```
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python -m pytest -q -p no:logging
```

---

## How it was developed

- Every change is a small, separate step with its own commit.
- Before logic changes, tests are written that lock the current behaviour.
