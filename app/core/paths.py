"""Project / install path resolution (dev tree vs frozen Windows exe)."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def is_frozen() -> bool:
    """True when running from a PyInstaller (or similar) bundle."""
    return bool(getattr(sys, "frozen", False)) and hasattr(sys, "_MEIPASS")


def bundle_root() -> Path:
    """Root of shipped code/assets (``sys._MEIPASS`` when frozen, else repo root)."""
    if is_frozen():
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parents[2]


def user_data_dir() -> Path:
    """Writable app data: ``%LOCALAPPDATA%\\Homebuy`` when frozen, else ``./data``."""
    override = (os.getenv("HOMEBUY_DATA_DIR") or "").strip()
    if override:
        return Path(override).expanduser().resolve()
    if is_frozen():
        local = os.environ.get("LOCALAPPDATA")
        base = Path(local) if local else Path.home() / "AppData" / "Local"
        return (base / "Homebuy").resolve()
    return (bundle_root() / "data").resolve()


def env_file() -> Path:
    """``.env`` location — user data when frozen, repo root in development."""
    if is_frozen():
        return user_data_dir() / ".env"
    return bundle_root() / ".env"


def package_data_file(*parts: str) -> Path:
    """Read-only JSON/tables shipped under ``app/data/``."""
    return bundle_root() / "app" / "data" / Path(*parts)


def static_dir() -> Path:
    """Theme fonts and other static assets under ``app/static/``."""
    return bundle_root() / "app" / "static"


# Eager aliases used like former ``db.DATA_DIR`` / ``ROOT``.
ROOT = bundle_root()
DATA_DIR = user_data_dir()
UPLOADS_DIR = DATA_DIR / "uploads"


def refresh_data_dirs() -> None:
    """Recompute writable dirs after tests monkeypatch env (rare)."""
    global ROOT, DATA_DIR, UPLOADS_DIR
    ROOT = bundle_root()
    DATA_DIR = user_data_dir()
    UPLOADS_DIR = DATA_DIR / "uploads"
