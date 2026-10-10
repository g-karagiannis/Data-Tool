"""Display language ΕΛ/EN: every text exists in both languages, the switch sits top right,
the app opens in Greek and the choice lasts for the whole session."""
import re
import string
import threading

import pytest
from streamlit.testing.v1 import AppTest

from conftest import APP_PATH
from modules import i18n

GREEK = re.compile(r"[Ͱ-Ͽἀ-῿]")


def placeholders(text: str) -> set:
    return {field for _, field, _, _ in string.Formatter().parse(text) if field is not None}


@pytest.mark.parametrize("key", sorted(i18n.TEXTS))
def test_every_text_has_both_languages_with_the_same_placeholders(key):
    versions = i18n.TEXTS[key]
    assert versions["el"].strip() and versions["en"].strip()
    assert placeholders(versions["el"]) == placeholders(versions["en"])
    assert not GREEK.search(versions["en"]), versions["en"]


def test_a_text_is_given_in_the_language_of_the_run():
    i18n.set_language("en")
    assert i18n.t("app.title") == "Data Analysis Tool"
    i18n.set_language("xx")                    # unknown -> Greek
    assert i18n.t("app.title") == "Εργαλείο Ανάλυσης Δεδομένων"


def test_each_session_keeps_its_own_language():
    i18n.set_language("el")
    seen = {}

    def other_session():
        i18n.set_language("en")
        seen["other"] = i18n.t("app.title")

    thread = threading.Thread(target=other_session)
    thread.start()
    thread.join()
    assert seen["other"] == "Data Analysis Tool"
    assert i18n.t("app.title") == "Εργαλείο Ανάλυσης Δεδομένων"


def test_a_text_defined_twice_or_without_both_languages_is_refused():
    with pytest.raises(ValueError):
        i18n._merge([{"a": {"el": "α", "en": "a"}}, {"a": {"el": "α", "en": "a"}}])
    with pytest.raises(ValueError):
        i18n._merge([{"b": {"el": "β"}}])


# ---------------------------------------------------------------- the real screen

def app():
    at = AppTest.from_file(str(APP_PATH), default_timeout=120)
    at.run()
    assert not at.exception, at.exception
    return at


def test_the_app_opens_in_greek_with_the_switch_showing_el_and_en():
    at = app()
    switch = at.button_group(key="ui_language")
    assert switch.value == "el"
    assert list(switch.options) == ["ΕΛ", "EN"]
    assert at.title[0].value == "Εργαλείο Ανάλυσης Δεδομένων"
    assert at.info[0].value.startswith("Ανέβασε")


def test_switching_to_english_changes_the_texts_at_once():
    at = app()
    at.button_group(key="ui_language").set_value("en").run()
    assert at.title[0].value == "Data Analysis Tool"
    assert at.info[0].value == "Upload one or more files from the sidebar to get started."
    assert at.session_state["language"] == "en"


def test_the_language_stays_after_clear_all():
    at = app()
    at.button_group(key="ui_language").set_value("en").run()
    state_buttons = [b for b in at.sidebar.button if b.key == "clear_all" or "Καθαρισμός" in b.label
                     or "Clear" in b.label]
    state_buttons[0].click().run()
    assert at.session_state["language"] == "en"
    assert at.title[0].value == "Data Analysis Tool"
