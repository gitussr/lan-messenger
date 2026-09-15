"""Where each peer keeps its files on disk.

Paths must never be relative to the working directory: a packaged .exe is often
launched from a folder the user can't write to (Program Files, a network share,
a zip preview), which makes sqlite3 fail with "unable to open database file".
"""
from __future__ import annotations

import os
import re

APP_DIR_NAME = "LAN Messenger"

_INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED_NAMES = {"CON", "PRN", "AUX", "NUL"} | {f"{p}{i}" for p in ("COM", "LPT") for i in range(1, 10)}


def safe_name(username: str) -> str:
    """Map a display name to something usable as a Windows filename component."""
    name = _INVALID_CHARS.sub("_", username).strip().rstrip(". ")
    if not name:
        return "anonymous"
    if name.split(".")[0].upper() in _RESERVED_NAMES:
        name = f"_{name}"
    return name


def data_dir() -> str:
    """Per-user writable app data folder, e.g. %LOCALAPPDATA%\\LAN Messenger."""
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), ".local", "share")
    path = os.path.join(base, APP_DIR_NAME)
    os.makedirs(path, exist_ok=True)
    return path


def db_path(username: str) -> str:
    return os.path.join(data_dir(), f"{safe_name(username)}_chat_history.db")


def downloads_dir(username: str) -> str:
    """Received files go somewhere the user will look: ~/Downloads/LAN Messenger/<name>."""
    return os.path.join(os.path.expanduser("~"), "Downloads", APP_DIR_NAME, safe_name(username))
