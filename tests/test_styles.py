"""All app CSS lives in styles/app.css and reaches the page exactly once."""
from conftest import PROJECT_ROOT, run_app

CSS_FILE = PROJECT_ROOT / "styles" / "app.css"


def test_page_injects_the_css_file_once(clean_main):
    at = run_app(clean_main)
    style_blocks = [m.value for m in at.markdown if "<style>" in m.value]
    assert len(style_blocks) == 1
    assert CSS_FILE.read_text(encoding="utf-8") in style_blocks[0]


def test_toasts_stay_bottom_left():
    css = CSS_FILE.read_text(encoding="utf-8")
    toast_rule = css[css.index('div[data-testid="stToastContainer"]'):]
    toast_rule = toast_rule[:toast_rule.index("}")]
    for declaration in ("left: 1rem !important", "right: auto !important",
                        "bottom: 1rem !important", "top: auto !important"):
        assert declaration in toast_rule
