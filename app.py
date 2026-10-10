from pathlib import Path

import streamlit as st

from modules.i18n import t
from ui import advanced_sql
from ui import language
from ui import sidebar
from ui import state
from ui import tab_analysis as analysis
from ui import tab_pipeline as pipeline
from ui import tab_view as view
from ui import tab_workshop as workshop
from ui import upload

CSS_FILE = Path(__file__).resolve().parent / "styles" / "app.css"

state.init_state()
language.apply()   # πρώτα η γλώσσα: όλα τα κείμενα από εδώ και κάτω τη χρησιμοποιούν

st.set_page_config(page_title=t("app.title"), layout="wide")

# Όλο το CSS της εφαρμογής (θέση των toast, λεπτομέρειες σκούρου θέματος) ζει στο styles/app.css.
st.markdown(f"<style>\n{CSS_FILE.read_text(encoding='utf-8')}\n</style>", unsafe_allow_html=True)

title_col, language_col = st.columns([6, 1], vertical_alignment="center")
title_col.title(t("app.title"))
language.switch(language_col.container(horizontal_alignment="right"))

mode = sidebar.mode_choice()

# ---------------------------------------------------------------- ΦΟΡΤΩΣΗ
uploaded = upload.sidebar_section()
upload.receive_files(uploaded)
upload.load_settings()
upload.combination_screen()

if not st.session_state.datasets:
    if st.session_state.pending_uploads or st.session_state.batch:
        st.info(t("app.finish_loading"))
    else:
        st.info(t("app.upload_to_start"))
    st.stop()

name, df = sidebar.active_dataset()

# ============================================================== ADVANCED
if mode == "Advanced (SQL)":
    advanced_sql.render(df, name)

sidebar.change_history(name)

# ============================================================== TABS
tab_view, tab_clean, tab_stats, tab_workshop = st.tabs(
    ["View", "Pipeline", "Analysis", "Workshop"]
)

with tab_view:
    view.render(df)

with tab_clean:
    pipeline.render(name)

with tab_stats:
    analysis.render(df, name)

with tab_workshop:
    workshop.render(df, name)
