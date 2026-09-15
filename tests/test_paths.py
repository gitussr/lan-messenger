import os

import paths
from storage import Storage


def test_safe_name_replaces_invalid_windows_filename_chars():
    assert paths.safe_name('a:b/c\\d*e?f"g<h>i|j') == "a_b_c_d_e_f_g_h_i_j"


def test_safe_name_handles_empty_trailing_dots_and_reserved_names():
    assert paths.safe_name("   ") == "anonymous"
    assert paths.safe_name("bob. ") == "bob"
    assert paths.safe_name("con") == "_con"
    assert paths.safe_name("COM1.txt") == "_COM1.txt"
    assert paths.safe_name("alice") == "alice"


def test_db_path_is_absolute_and_openable_regardless_of_cwd(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "appdata"))
    unwritable_cwd = tmp_path / "cwd"
    unwritable_cwd.mkdir()
    monkeypatch.chdir(unwritable_cwd)

    path = paths.db_path("who?:me")

    assert os.path.isabs(path)
    assert os.path.dirname(path) == str(tmp_path / "appdata" / paths.APP_DIR_NAME)
    assert os.path.basename(path) == "who__me_chat_history.db"
    Storage(db_path=path).close()
