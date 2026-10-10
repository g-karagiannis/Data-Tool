"""Tab View: προεπισκόπηση δεδομένων και επισκόπηση στηλών (τύπος, κενές τιμές, Min/Max)."""
import pandas as pd
import streamlit as st

from modules import data_cleaner as dc


def render(df: pd.DataFrame) -> None:
    st.subheader("Προεπισκόπηση δεδομένων")
    st.dataframe(df, width="stretch", height=400)

    st.subheader("Επισκόπηση στηλών")
    date_cols = df.select_dtypes(include="datetime").columns.tolist()
    if len(date_cols) >= 2:
        date_tie_col = st.selectbox(
            "Στήλη ημερομηνίας για tie-break στα Min/Max κειμένου (όταν 2+ τιμές ισοβαθμούν)",
            date_cols, key="text_minmax_tie_col",
        )
    elif len(date_cols) == 1:
        date_tie_col = date_cols[0]
    else:
        date_tie_col = None
    st.dataframe(dc.profile(df, date_tie_col), width="stretch")
