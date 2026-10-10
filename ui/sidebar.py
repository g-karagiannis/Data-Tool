"""
Sidebar: «Λειτουργία», «2. Ενεργό σύνολο δεδομένων» και «3. Ιστορικό αλλαγών».
(Η ενότητα «1. Φόρτωση δεδομένων» ζει στο ui/upload.py.)
"""
import pandas as pd
import streamlit as st


def mode_choice() -> str:
    """«Απλή» ή «Advanced (SQL)»."""
    mode = st.sidebar.radio("Λειτουργία", ["Απλή", "Advanced (SQL)"])
    return mode


def active_dataset():
    """Επιλογή του ενεργού dataset. Επιστρέφει (όνομα, DataFrame)."""
    st.sidebar.header("2. Ενεργό σύνολο δεδομένων")
    name = st.sidebar.selectbox("Επίλεξε dataset", list(st.session_state.datasets.keys()))
    st.session_state.active = name
    df = st.session_state.datasets[name]

    st.sidebar.markdown(f"**Διαστάσεις:** {df.shape[0]} γραμμές × {df.shape[1]} στήλες")
    return name, df


def change_history(name: str) -> None:
    """Πίνακας με τις αλλαγές του ενεργού dataset, από την παλαιότερη στη νεότερη."""
    st.sidebar.header("3. Ιστορικό αλλαγών")
    history_entries = st.session_state.undo_stack.get(name) or []
    if not history_entries:
        st.sidebar.caption("Καμία αλλαγή ακόμα σε αυτό το dataset.")
    else:
        history_df = pd.DataFrame([
            {"Ώρα": e["timestamp"].strftime("%H:%M:%S"), "Αλλαγή": e["description"]}
            for e in history_entries   # ήδη παλαιότερο -> νεότερο (διαδοχική σειρά)
        ])
        st.sidebar.dataframe(history_df, width="stretch", height=180, hide_index=True)
