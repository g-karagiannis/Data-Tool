"""Advanced (SQL): ελεύθερο SQL SELECT πάνω στο ενεργό dataset (πίνακας `data`)."""
import pandas as pd
import streamlit as st

from modules import data_loader as dl
from ui import state


def render(df: pd.DataFrame, name: str) -> None:
    st.header("Advanced mode — SQL queries")
    st.caption("Γράψε ένα SQL SELECT πάνω στο ενεργό dataset (πίνακας ονομάζεται `data`).")
    default_q = "SELECT * FROM data LIMIT 100"
    query = st.text_area("SQL query", value=default_q, height=120, key="sql_query_text")
    if st.button("Εκτέλεση"):
        try:
            st.session_state.sql_result = dl.query_dataframe(df, query, table_name="data")
        except Exception as e:
            st.session_state.sql_result = None
            st.toast(f"Σφάλμα στο query: {e}")

    if st.session_state.get("sql_result") is not None:
        result = st.session_state.sql_result
        st.dataframe(result, width="stretch")
        st.download_button(
            "Λήψη αποτελέσματος ως CSV",
            result.to_csv(index=False).encode("utf-8-sig"),
            file_name="query_result.csv",
        )
        ac1, ac2 = st.columns(2)
        with ac1:
            if st.button(f"Ενημέρωση ενεργού dataset ('{name}') με το αποτέλεσμα"):
                state.push_undo(name, "Ενημέρωση μέσω SQL (Advanced mode)")
                st.session_state.datasets[name] = result
                st.session_state.sql_result = None
                st.success(f"Το '{name}' ενημερώθηκε — οι νέες στήλες είναι ήδη διαθέσιμες σε όλες τις καρτέλες.")
                st.rerun()
        with ac2:
            save_name = st.text_input("...ή αποθήκευση ως νέο dataset (όνομα)", key="sql_save_name")
            if st.button("Αποθήκευση ως νέο dataset") and save_name:
                st.session_state.datasets[save_name] = result
                st.session_state.sql_result = None
                st.success(f"Αποθηκεύτηκε ως '{save_name}'")
                st.rerun()
    st.divider()
