"""
Workshop: εκτέλεση ελεύθερου κώδικα Python πάνω σε ΑΝΤΙΓΡΑΦΑ των δεδομένων, με έτοιμες
βιβλιοθήκες και εντολές (show, save_table, historical_volatility, moving_average), και οι
λήψεις των αποτελεσμάτων (πίνακες, γραφήματα Plotly/matplotlib). Καμία εξάρτηση από
Streamlit: η οθόνη (ui/tab_workshop.py) δίνει τις συναρτήσεις show/save_table.
"""
import contextlib
import io
import traceback

import numpy as np
import pandas as pd

from modules import econometrics as ec

CODE_FILENAME = "<κώδικας>"

# Τα γραφήματα matplotlib (π.χ. τα έτοιμα του statsmodels/pyfixest) φτιάχνονται ως εικόνες
# στη μνήμη· χωρίς αυτό, η matplotlib θα προσπαθούσε να ανοίξει παράθυρο στον server.
import matplotlib  # noqa: E402

matplotlib.use("Agg")


# ------------------------------------------------------------------ έτοιμες εντολές

def historical_volatility(prices, dates=None, window: int = 20, annualization_factor: int = 252):
    """Ιστορική μεταβλητότητα με σωστή χρονολογική σειρά. Χωρίς dates: με τη σειρά των γραμμών
    (η πρώτη γραμμή θεωρείται η παλαιότερη)."""
    prices = pd.Series(prices)
    dates = pd.Series(range(len(prices)), index=prices.index) if dates is None else pd.Series(dates)
    return ec.historical_volatility(prices, dates, window=window, annualization_factor=annualization_factor)


def moving_average(series, dates=None, window: int = 20, method: str = "SMA"):
    """Κινητός μέσος (SMA ή EMA) με σωστή χρονολογική σειρά. Χωρίς dates: με τη σειρά των
    γραμμών (η πρώτη γραμμή θεωρείται η παλαιότερη)."""
    series = pd.Series(series)
    dates = pd.Series(range(len(series)), index=series.index) if dates is None else pd.Series(dates)
    return ec.moving_average(series, dates, window=window, method=method)


def build_namespace(datasets: dict, tables: dict, active_df: pd.DataFrame, show, save_table) -> dict:
    """Οι μεταβλητές που βρίσκει έτοιμες ο κώδικας του χρήστη. Τα δεδομένα είναι ΑΝΤΙΓΡΑΦΑ:
    καμία αλλαγή μέσα στον κώδικα δεν φτάνει στις άλλες καρτέλες (εκτός από το save_table)."""
    import linearmodels
    import plotly.express as px
    import plotly.graph_objects as go
    import pyfixest as pf
    import statsmodels.api as sm
    import statsmodels.formula.api as smf
    from arch import arch_model

    return {
        "__name__": "__workshop__",
        "datasets": {name: frame.copy() for name, frame in datasets.items()},
        "tables": {name: frame.copy() for name, frame in tables.items()},
        "df": active_df.copy(),
        "pd": pd, "np": np, "px": px, "go": go, "sm": sm, "smf": smf,
        "linearmodels": linearmodels, "pf": pf, "arch_model": arch_model,
        "show": show, "save_table": save_table,
        "historical_volatility": historical_volatility, "moving_average": moving_average,
    }


def run_code(code: str, namespace: dict) -> dict:
    """Τρέχει τον κώδικα από την αρχή. Επιστρέφει {"stdout": ό,τι τυπώθηκε, "error": μήνυμα
    σφάλματος της Python ή None}. Ό,τι τυπώθηκε πριν από ένα σφάλμα διατηρείται."""
    buffer = io.StringIO()
    error = None
    try:
        compiled = compile(code, CODE_FILENAME, "exec")
    except SyntaxError as e:
        return {"stdout": "", "error": "".join(traceback.format_exception_only(type(e), e))}
    try:
        with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
            exec(compiled, namespace)
    except Exception as e:  # noqa: BLE001 — κάθε σφάλμα του χρήστη εμφανίζεται, δεν «σκάει» η εφαρμογή
        user_frames = e.__traceback__.tb_next if e.__traceback__ is not None else None
        error = "".join(traceback.format_exception(type(e), e, user_frames))
    return {"stdout": buffer.getvalue(), "error": error}


# ------------------------------------------------------------------ show(): είδος αποτελέσματος

def classify(obj):
    """Επιστρέφει (είδος, αντικείμενο) για το show(): "table" (DataFrame), "plotly",
    "matplotlib" (Figure) ή "text" (οτιδήποτε άλλο, π.χ. summary μοντέλου, ως κείμενο)."""
    if isinstance(obj, pd.Series):
        return "table", obj.to_frame()
    if isinstance(obj, pd.DataFrame):
        return "table", obj
    try:
        import plotly.graph_objects as go
        if isinstance(obj, go.Figure):
            return "plotly", obj
    except ImportError:
        pass
    from matplotlib.axes import Axes
    from matplotlib.figure import Figure
    if isinstance(obj, Axes):
        return "matplotlib", obj.get_figure()
    if isinstance(obj, Figure):
        return "matplotlib", obj
    return "text", str(obj)


# ------------------------------------------------------------------ λήψεις

def table_downloads(frame: pd.DataFrame) -> dict:
    """{"csv", "xlsx", "html"} -> bytes."""
    excel = io.BytesIO()
    with pd.ExcelWriter(excel, engine="openpyxl") as writer:
        frame.to_excel(writer, index=False, sheet_name="Sheet1")
    return {
        "csv": frame.to_csv(index=False).encode("utf-8-sig"),
        "xlsx": excel.getvalue(),
        "html": frame.to_html(index=False).encode("utf-8"),
    }


def plotly_html(fig) -> bytes:
    """Διαδραστικό γράφημα σε αυτόνομο HTML (ανοίγει σε browser, χωρίς internet)."""
    return fig.to_html(include_plotlyjs=True, full_html=True).encode("utf-8")


def matplotlib_image(fig, fmt: str) -> bytes:
    """Στατική εικόνα "png" ή "pdf"."""
    buffer = io.BytesIO()
    fig.savefig(buffer, format=fmt, bbox_inches="tight")
    return buffer.getvalue()
