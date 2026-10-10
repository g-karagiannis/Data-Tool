"""
Γλώσσα εμφάνισης (ΕΛ/EN). Κάθε κείμενο της εφαρμογής έχει ένα κλειδί και δύο εκδοχές, στα
modules/texts/*.py· η t("κλειδί") δίνει την εκδοχή της γλώσσας του τρέχοντος run.

Η γλώσσα κρατιέται σε ContextVar, ώστε κάθε συνεδρία (καρτέλα browser) να έχει τη δική της
ακόμα κι όταν τρέχουν ταυτόχρονα. Καμία εξάρτηση από Streamlit.
"""
from contextvars import ContextVar

from modules.texts import CATALOGUES

LANGUAGES = ("el", "en")
LANGUAGE_LABELS = {"el": "ΕΛ", "en": "EN"}
DEFAULT_LANGUAGE = "el"

_language = ContextVar("language", default=DEFAULT_LANGUAGE)


def _merge(catalogues) -> dict:
    merged = {}
    for catalogue in catalogues:
        for key, versions in catalogue.items():
            if key in merged:
                raise ValueError(f"Το κλειδί κειμένου '{key}' ορίζεται δύο φορές.")
            if set(versions) != set(LANGUAGES):
                raise ValueError(f"Το κλειδί κειμένου '{key}' δεν έχει ακριβώς τις γλώσσες {LANGUAGES}.")
            merged[key] = versions
    return merged


TEXTS = _merge(CATALOGUES)


def set_language(language: str) -> None:
    _language.set(language if language in LANGUAGES else DEFAULT_LANGUAGE)


def get_language() -> str:
    return _language.get()


def t(key: str, **values) -> str:
    """Το κείμενο στη γλώσσα του τρέχοντος run· με values συμπληρώνονται τα {πεδία} του."""
    text = TEXTS[key][_language.get()]
    return text.format(**values) if values else text
