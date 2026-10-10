"""
Διακόπτης γλώσσας ΕΛ/EN πάνω δεξιά. Η εφαρμογή ανοίγει πάντα στα ελληνικά· η επιλογή μένει
για όλη τη συνεδρία (και μετά τον «Καθαρισμό όλων»).
"""
import streamlit as st

from modules import i18n

KEY = "ui_language"


def apply() -> None:
    """Θέτει τη γλώσσα αυτού του run: η τιμή του διακόπτη (αν πατήθηκε), αλλιώς η αποθηκευμένη."""
    chosen = st.session_state.get(KEY)
    if chosen in i18n.LANGUAGES:
        st.session_state.language = chosen
    i18n.set_language(st.session_state.language)


def switch(container) -> None:
    """Ο διακόπτης ΕΛ | EN. Αν αποεπιλεγεί (ή δεν σχεδιάστηκε σε κάποιο run), ξαναπαίρνει τη
    γλώσσα της συνεδρίας — πριν σχεδιαστεί, όπως επιτρέπει η Streamlit."""
    if st.session_state.get(KEY) not in i18n.LANGUAGES:
        st.session_state[KEY] = st.session_state.language
    container.segmented_control(
        i18n.t("app.language"), list(i18n.LANGUAGES), format_func=i18n.LANGUAGE_LABELS.get,
        key=KEY, label_visibility="collapsed",
    )
