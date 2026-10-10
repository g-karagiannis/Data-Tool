"""Architecture rules: logic modules (modules/) never touch the screen.

- modules/*.py must not import streamlit or anything from ui/ — they are plain functions
  on data, usable and testable without the app.
- ui/*.py and app.py may import both streamlit and modules/.
"""
import ast

import pytest

from conftest import PROJECT_ROOT

FORBIDDEN_IN_MODULES = {"streamlit", "ui"}
LOGIC_FILES = sorted((PROJECT_ROOT / "modules").rglob("*.py"))   # και οι υποφάκελοι (modules/texts/)


def imported_top_level_names(source: str) -> set:
    """First part of every imported module name, including imports inside functions."""
    names = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module.split(".")[0])
    return names


def test_the_checker_sees_imports_anywhere_in_a_file():
    source = (
        "import streamlit as st\n"
        "from ui import state\n"
        "def f():\n"
        "    from arch import arch_model\n"
        "    import plotly.graph_objects as go\n"
    )
    assert imported_top_level_names(source) == {"streamlit", "ui", "arch", "plotly"}


def test_there_are_logic_modules_to_check():
    assert {"econometrics.py", "query_builder.py", "upload_plan.py"} <= {p.name for p in LOGIC_FILES}


@pytest.mark.parametrize("path", LOGIC_FILES, ids=lambda p: p.relative_to(PROJECT_ROOT / "modules").as_posix())
def test_logic_modules_do_not_import_the_screen(path):
    imported = imported_top_level_names(path.read_text(encoding="utf-8"))
    assert not imported & FORBIDDEN_IN_MODULES, f"{path.name} imports {sorted(imported & FORBIDDEN_IN_MODULES)}"
