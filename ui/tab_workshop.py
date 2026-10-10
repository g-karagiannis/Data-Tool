"""
Tab Workshop: προβολή table, εγχειρίδιο εντολών, ελεύθερος κώδικας Python με έτοιμες
βιβλιοθήκες, και τα αποτελέσματά του με λήψεις. Η εκτέλεση και οι λήψεις ζουν στο
modules/workshop.py· εδώ μόνο η οθόνη.
"""
import copy
from pathlib import Path

import pandas as pd
import streamlit as st

from modules import query_builder as qb
from modules import workshop as ws
from ui import state

MANUAL_FILE = Path(__file__).resolve().parent.parent / "docs" / "workshop_εντολές.md"
ACTIVE_DATASET = "(Ενεργό σύνολο δεδομένων)"
CODE_KEY = "workshop_code"
VIEW_KEY = "workshop_view_table"
STARTER_CODE = (
    "# Γράψε κώδικα Python και πάτα «Εκτέλεση». Δες τις «Εντολές» για όσα είναι διαθέσιμα.\n"
    "print(df.shape)\n"
    "show(df.head())\n"
)
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _table_frames(df: pd.DataFrame, name: str) -> dict:
    """{όνομα table: αποτέλεσμα} για τα tables του ενεργού dataset. Τα tables του Analysis
    υπολογίζονται σε αντίγραφο, ώστε να μην αλλάξει τίποτα στην καρτέλα τους."""
    frames = {}
    for table in state.group_analysis_state(name)["tables"]:
        if qb.is_snapshot(table):
            frames[table["name"]] = table["result_df"]
            continue
        result = qb.execute(df, copy.deepcopy(table))
        if result["error"] is None and result["result_df"] is not None:
            frames[table["name"]] = result["result_df"]
    return frames


def _viewer(df: pd.DataFrame, frames: dict) -> None:
    st.subheader("Προβολή")
    options = [ACTIVE_DATASET] + list(frames)
    if st.session_state.get(VIEW_KEY) not in options:   # π.χ. το table διαγράφηκε στο Analysis
        st.session_state[VIEW_KEY] = ACTIVE_DATASET
    choice = st.selectbox("Table", options, key=VIEW_KEY)
    shown = df if choice == ACTIVE_DATASET else frames[choice]
    st.caption(f"**{choice}** — {shown.shape[0]} γραμμές × {shown.shape[1]} στήλες · μόνο για προβολή")
    st.dataframe(shown, width="stretch", height=300)


def _load_uploaded_code() -> None:
    uploaded = st.session_state.get("workshop_code_file")
    if uploaded is not None:
        st.session_state[CODE_KEY] = uploaded.getvalue().decode("utf-8", errors="replace")


def _prepare_downloads(items: list) -> None:
    """Οι λήψεις φτιάχνονται μία φορά, μετά την εκτέλεση (όχι σε κάθε ανανέωση της σελίδας)."""
    for item in items:
        if item["kind"] == "table":
            item["downloads"] = ws.table_downloads(item["value"])
        elif item["kind"] == "plotly":
            item["downloads"] = {"html": ws.plotly_html(item["value"])}
        elif item["kind"] == "matplotlib":
            item["downloads"] = {fmt: ws.matplotlib_image(item["value"], fmt) for fmt in ("png", "pdf")}
            item["value"] = None   # η εικόνα PNG αρκεί για την προβολή· το Figure δεν κρατιέται
    import matplotlib.pyplot as plt
    plt.close("all")


def _run(code: str, df: pd.DataFrame, name: str, frames: dict) -> bool:
    """Τρέχει τον κώδικα. Επιστρέφει True αν αποθηκεύτηκε κάποιο table (χρειάζεται rerun)."""
    items, saved, problems = [], [], []
    container = state.group_analysis_state(name)

    def show(obj, title=None):
        kind, value = ws.classify(obj)
        items.append({"kind": kind, "value": value, "title": title})

    def save_table(table_name, frame):
        if isinstance(frame, pd.Series):
            frame = frame.to_frame()
        error = qb.save_snapshot_table(container, table_name, frame)
        if error:
            problems.append(error)
        else:
            saved.append(str(table_name).strip())

    namespace = ws.build_namespace(st.session_state.datasets, frames, df, show, save_table)
    outcome = ws.run_code(code, namespace)
    _prepare_downloads(items)
    st.session_state.workshop_result = {**outcome, "items": items, "saved": saved, "problems": problems}
    return bool(saved)


def _show_item(index: int, item: dict) -> None:
    key = f"workshop_out_{index}_"
    base = str(item["title"] or f"αποτέλεσμα_{index + 1}")
    if item["title"]:
        st.markdown(f"**{item['title']}**")
    files = item.get("downloads", {})
    if item["kind"] == "table":
        st.dataframe(item["value"], width="stretch")
        c1, c2, c3 = st.columns(3)
        c1.download_button("Λήψη CSV", files["csv"], file_name=f"{base}.csv", key=f"{key}csv")
        c2.download_button("Λήψη Excel", files["xlsx"], file_name=f"{base}.xlsx", mime=XLSX_MIME, key=f"{key}xlsx")
        c3.download_button("Λήψη HTML", files["html"], file_name=f"{base}.html", mime="text/html", key=f"{key}html")
    elif item["kind"] == "plotly":
        st.plotly_chart(item["value"], width="stretch", key=f"{key}chart")
        st.download_button("Λήψη HTML (διαδραστικό)", files["html"], file_name=f"{base}.html",
                           mime="text/html", key=f"{key}html")
        st.caption("Για εικόνα PNG: κουμπί κάμερας πάνω δεξιά στο γράφημα.")
    elif item["kind"] == "matplotlib":
        st.image(files["png"])
        c1, c2 = st.columns(2)
        c1.download_button("Λήψη PNG", files["png"], file_name=f"{base}.png", mime="image/png", key=f"{key}png")
        c2.download_button("Λήψη PDF", files["pdf"], file_name=f"{base}.pdf", mime="application/pdf", key=f"{key}pdf")
    else:
        st.code(item["value"], language=None)


def _results() -> None:
    result = st.session_state.workshop_result
    if result is None:
        return
    st.subheader("Αποτελέσματα")
    for table_name in result["saved"]:
        st.success(f"Το table '{table_name}' αποθηκεύτηκε — φαίνεται στην «Προβολή» και στο Analysis.")
    for problem in result["problems"]:
        st.warning(f"save_table: {problem}")
    if result["stdout"]:
        st.code(result["stdout"], language=None)
    for index, item in enumerate(result["items"]):
        _show_item(index, item)
    if result["error"]:
        st.error("Ο κώδικας σταμάτησε με σφάλμα:")
        st.code(result["error"], language=None)
    if not (result["stdout"] or result["items"] or result["error"] or result["saved"] or result["problems"]):
        st.caption("Ο κώδικας ολοκληρώθηκε χωρίς έξοδο — χρησιμοποίησε print() ή show().")


def render(df: pd.DataFrame, name: str) -> None:
    frames = _table_frames(df, name)
    _viewer(df, frames)

    st.divider()
    st.subheader("Κώδικας")
    with st.expander("Εντολές (εγχειρίδιο)"):
        st.markdown(MANUAL_FILE.read_text(encoding="utf-8"))
    st.file_uploader("Φόρτωση κώδικα (.txt, .py)", type=["txt", "py"], key="workshop_code_file",
                     on_change=_load_uploaded_code)
    if CODE_KEY not in st.session_state:
        st.session_state[CODE_KEY] = st.session_state.workshop_code_saved or STARTER_CODE
    code = st.text_area("Κώδικας Python", height=320, key=CODE_KEY)
    st.session_state.workshop_code_saved = code
    c1, c2 = st.columns(2)
    run = c1.button("Εκτέλεση", key="workshop_run", type="primary")
    c2.download_button("Λήψη κώδικα (.txt)", code.encode("utf-8"), file_name="workshop_κώδικας.txt",
                       mime="text/plain", key="workshop_code_download")
    st.caption(
        "Ο κώδικας τρέχει από την αρχή σε κάθε «Εκτέλεση», πάνω σε αντίγραφα των δεδομένων. "
        "Αν δεν τελειώνει (π.χ. ατέρμονος βρόχος), κλείσε την εφαρμογή και ξεκίνα την ξανά."
    )
    if run and _run(code, df, name, frames):
        st.rerun()   # να φανεί αμέσως το νέο table στην «Προβολή» και στο Analysis

    st.divider()
    _results()
