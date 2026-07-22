"""Tests for path resolution and native launch flags."""

from __future__ import annotations

import os
from pathlib import Path

from app.core import paths
from app.main import want_native


def test_user_data_dir_defaults_to_repo_data(monkeypatch):
    monkeypatch.delenv("HOMEBUY_DATA_DIR", raising=False)
    monkeypatch.setattr(paths, "is_frozen", lambda: False)
    root = Path(__file__).resolve().parents[1]
    assert paths.user_data_dir() == (root / "data").resolve()


def test_user_data_dir_respects_override(monkeypatch, tmp_path):
    monkeypatch.setenv("HOMEBUY_DATA_DIR", str(tmp_path / "custom"))
    assert paths.user_data_dir() == (tmp_path / "custom").resolve()


def test_package_data_file_points_at_app_data():
    p = paths.package_data_file("home_insurance_rates.json")
    assert p.name == "home_insurance_rates.json"
    assert p.is_file()
    assert "app" in p.parts and "data" in p.parts


def test_want_native_cli_and_env(monkeypatch):
    monkeypatch.delenv("HOMEBUY_NATIVE", raising=False)
    monkeypatch.setattr("app.main.is_frozen", lambda: False)
    assert want_native([]) is False
    assert want_native(["--native"]) is True
    assert want_native(["--browser"]) is False
    assert want_native(["--native", "--browser"]) is False  # --browser wins

    monkeypatch.setenv("HOMEBUY_NATIVE", "1")
    assert want_native([]) is True
    monkeypatch.setenv("HOMEBUY_NATIVE", "0")
    assert want_native([]) is False


def test_want_native_frozen_default(monkeypatch):
    monkeypatch.delenv("HOMEBUY_NATIVE", raising=False)
    monkeypatch.setattr("app.main.is_frozen", lambda: True)
    assert want_native([]) is True
    assert want_native(["--browser"]) is False


def test_env_file_dev_is_repo_dotenv():
    assert paths.env_file() == paths.bundle_root() / ".env"


def test_overlay_cache_uses_data_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("HOMEBUY_DATA_DIR", str(tmp_path))
    import app.core.overlay_cache as oc
    import app.core.paths as p

    p.refresh_data_dirs()
    d = oc.cache_dir("unit_test")
    assert d == tmp_path / "cache" / "unit_test"
    assert d.is_dir()


def test_native_run_skips_browser_port():
    """Native must not bind HOMEBUY_PORT (8080) so it can coexist with browser."""
    src = Path(__file__).resolve().parents[1].joinpath("app", "main.py").read_text(
        encoding="utf-8"
    )
    assert "HOMEBUY_NATIVE_PORT" in src
    assert "Do not reuse HOMEBUY_PORT" in src


def test_native_chrome_matches_theme_bg():
    from app.core.native_chrome import NATIVE_BG, configure_native_window_args
    from app.ui.theme import COLORS

    assert NATIVE_BG == COLORS["bg"]
    args: dict = {}
    configure_native_window_args(args)
    assert args["background_color"] == COLORS["bg"]
    assert args["title"] == "Homebuy"


def test_hex_to_colorref_bgr():
    from app.core.native_chrome import _hex_to_colorref

    # #0B0D10 → R=0x0B G=0x0D B=0x10 → 0x00100D0B
    assert _hex_to_colorref("#0B0D10") == 0x00100D0B
