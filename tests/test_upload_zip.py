""".zip uploads: pick a file from inside the zip, which then goes through the same load
settings as a CSV/Excel; the size limit is checked on the uncompressed size."""
import io
import zipfile

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from conftest import APP_PATH, JOIN_FILE, MAIN_FILE, load_like_the_app
from modules import data_loader as dl
from modules import upload_plan as up

MAIN = MAIN_FILE.name
JOIN = JOIN_FILE.name
MB = 1024 * 1024


def make_zip(files: dict) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


# ---------------------------------------------------------------- reading and rules (no UI)

def test_zip_members_lists_files_without_folders_or_macos_extras():
    raw = make_zip({"data/a.csv": b"x,y\n1,2\n", "__MACOSX/data/._a.csv": b"junk", "data/._b.csv": b"junk",
                    "notes.pdf": b"%PDF"})
    assert dl.zip_members(raw) == [("data/a.csv", 8), ("notes.pdf", 4)]


def test_a_file_read_from_a_zip_is_byte_for_byte_the_original():
    content = MAIN_FILE.read_bytes()
    assert dl.read_zip_member(make_zip({MAIN: content}), MAIN) == content


def test_a_damaged_zip_member_raises_instead_of_returning_wrong_data():
    raw = bytearray(make_zip({"a.csv": b"x,y\n" + b"1,2\n" * 1000}))
    middle = len(raw) // 3
    raw[middle] ^= 0xFF
    with pytest.raises(Exception):
        dl.read_zip_member(bytes(raw), "a.csv")


def test_zip_choices_keeps_loadable_types_within_the_uncompressed_limit():
    loadable, skipped = up.zip_choices([("a.csv", 1), ("b.XLSX", 2), ("c.pdf", 3), ("big.csv", 10 * MB + 1)])
    assert loadable == ["a.csv", "b.XLSX"]
    assert [name for name, _ in skipped] == ["c.pdf", "big.csv"]
    assert "10.0MB" in skipped[1][1]


# ---------------------------------------------------------------- the real screen

def empty_app():
    at = AppTest.from_file(str(APP_PATH), default_timeout=120)
    at.run()
    return at


def upload(at, files):
    at.file_uploader(key="file_uploader_0").set_value(
        [(name, content, "application/zip" if name.endswith(".zip") else "text/csv") for name, content in files]
    ).run()
    assert not at.exception, at.exception


def press_load(at):
    at.button(key="load_all").click().run()
    assert not at.exception, at.exception


def test_uploader_accepts_zip_files():
    at = empty_app()
    assert ".zip" in at.file_uploader(key="file_uploader_0").proto.type


def test_a_csv_inside_a_zip_loads_like_the_csv_itself():
    at = empty_app()
    upload(at, [("pack.zip", make_zip({MAIN: MAIN_FILE.read_bytes(), "codebook.pdf": b"%PDF"}))])
    assert at.selectbox(key="zipmember_pack.zip").options == [MAIN]
    assert any("codebook.pdf" in c.value for c in at.caption)
    press_load(at)
    pd.testing.assert_frame_equal(at.session_state["datasets"][f"pack.zip/{MAIN}"], load_like_the_app(MAIN_FILE))
    assert not at.session_state["pending_uploads"]


def test_a_zip_stays_in_the_list_until_every_file_in_it_is_loaded():
    at = empty_app()
    upload(at, [("pack.zip", make_zip({MAIN: MAIN_FILE.read_bytes(), JOIN: JOIN_FILE.read_bytes()}))])
    at.selectbox(key="zipmember_pack.zip").set_value(JOIN).run()
    press_load(at)
    assert set(at.session_state["datasets"]) == {f"pack.zip/{JOIN}"}
    assert at.selectbox(key="zipmember_pack.zip").options == [MAIN]
    press_load(at)
    assert set(at.session_state["datasets"]) == {f"pack.zip/{JOIN}", f"pack.zip/{MAIN}"}
    pd.testing.assert_frame_equal(at.session_state["datasets"][f"pack.zip/{JOIN}"], load_like_the_app(JOIN_FILE))
    assert not at.session_state["pending_uploads"]


def test_a_zip_without_a_loadable_file_leaves_the_list():
    at = empty_app()
    upload(at, [("docs.zip", make_zip({"codebook.pdf": b"%PDF"}))])
    assert not at.session_state["pending_uploads"]
    assert "docs.zip" in at.session_state["done_uploads"]
    assert any("docs.zip" in t.value and "codebook.pdf" in t.value for t in at.toast)


def test_a_file_that_unzips_beyond_10mb_is_never_unzipped():
    huge = b"x,y\n" + b"1,2\n" * (11 * MB // 4)       # compresses to a few KB
    raw = make_zip({"huge.csv": huge})
    assert len(raw) < MB
    at = empty_app()
    upload(at, [("bomb.zip", raw)])
    assert not at.session_state["datasets"]
    assert not at.session_state["pending_uploads"]
    assert any("bomb.zip" in t.value and "huge.csv" in t.value and "11.0MB" in t.value for t in at.toast)


def test_a_csv_inside_a_zip_can_be_combined_with_another_file():
    at = empty_app()
    upload(at, [("pack.zip", make_zip({MAIN: MAIN_FILE.read_bytes()})), (JOIN, JOIN_FILE.read_bytes())])
    at.checkbox(key="combine_pack.zip").check().run()
    at.checkbox(key=f"combine_{JOIN}").check().run()
    press_load(at)
    batch = at.session_state["batch"]
    assert batch["names"] == ["pack.zip", JOIN]
    pd.testing.assert_frame_equal(batch["ready"]["pack.zip"], load_like_the_app(MAIN_FILE))


def test_clear_all_forgets_which_zip_files_were_loaded():
    at = empty_app()
    upload(at, [("pack.zip", make_zip({MAIN: MAIN_FILE.read_bytes(), JOIN: JOIN_FILE.read_bytes()}))])
    press_load(at)
    assert at.session_state["zip_loaded_members"]
    [button] = [b for b in at.sidebar.button if b.label == "Καθαρισμός όλων (νέα ανάλυση)"]
    button.click().run()
    assert at.session_state["zip_loaded_members"] == {}
