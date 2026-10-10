"""Streamlit settings that must not be lost."""
import tomllib

from streamlit.testing.v1 import AppTest

from conftest import APP_PATH, PROJECT_ROOT
from modules import upload_plan as up

CONFIG = tomllib.loads((PROJECT_ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8"))


def test_app_only_accepts_connections_from_this_computer():
    assert CONFIG["server"]["address"] == "localhost"


def test_uploader_accepts_up_to_200mb_per_file_the_zip_and_dat_limit():
    assert CONFIG["server"]["maxUploadSize"] == 200
    assert CONFIG["server"]["maxUploadSize"] * 1024 * 1024 == up.MAX_LARGE_FILE_BYTES
    at = AppTest.from_file(str(APP_PATH), default_timeout=120)
    at.run()
    assert at.file_uploader(key="file_uploader_0").proto.max_upload_size_mb == 200
