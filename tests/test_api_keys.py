"""Tests for user API key .env merge helpers."""

from __future__ import annotations

import os
from pathlib import Path

from app.core.api_keys import (
    apply_env_updates,
    build_updates_from_form,
    key_is_set,
)


def test_build_updates_blank_leaves_unchanged():
    updates = build_updates_from_form(
        typed={"GOOGLE_MAPS_API_KEY": "", "CENSUS_API_KEY": "  abc  "},
        clear=set(),
    )
    assert "GOOGLE_MAPS_API_KEY" not in updates
    assert updates["CENSUS_API_KEY"] == "abc"


def test_build_updates_clear_wipes_even_if_typed():
    updates = build_updates_from_form(
        typed={"GEMINI_API_KEY": "should-ignore"},
        clear={"GEMINI_API_KEY"},
    )
    assert updates["GEMINI_API_KEY"] == ""


def test_apply_env_updates_preserves_comments_and_other_keys(tmp_path, monkeypatch):
    path = tmp_path / ".env"
    path.write_text(
        "# keep me\nHOMEBUY_PORT=8080\nGEMINI_API_KEY=old\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("CENSUS_API_KEY", raising=False)

    apply_env_updates(
        {"GEMINI_API_KEY": "new-secret", "CENSUS_API_KEY": "census-1"},
        path=path,
    )
    text = path.read_text(encoding="utf-8")
    assert "# keep me" in text
    assert "HOMEBUY_PORT=8080" in text
    assert "GEMINI_API_KEY=new-secret" in text
    assert "CENSUS_API_KEY=census-1" in text
    assert os.environ["GEMINI_API_KEY"] == "new-secret"
    assert key_is_set("GEMINI_API_KEY")


def test_apply_env_updates_clear(tmp_path, monkeypatch):
    path = tmp_path / ".env"
    path.write_text("GOOGLE_MAPS_API_KEY=xyz\n", encoding="utf-8")
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "xyz")

    apply_env_updates({"GOOGLE_MAPS_API_KEY": ""}, path=path)
    assert "GOOGLE_MAPS_API_KEY=" in path.read_text(encoding="utf-8")
    assert "GOOGLE_MAPS_API_KEY" not in os.environ
    assert not key_is_set("GOOGLE_MAPS_API_KEY")


def test_library_header_wires_api_keys_dialog():
    root = Path(__file__).resolve().parents[1]
    src = (
        root.joinpath("app", "ui", "pages.py").read_text(encoding="utf-8")
        + root.joinpath("app", "ui", "library_page.py").read_text(encoding="utf-8")
    )
    assert "show_api_keys=True" in src
    assert "_open_api_keys_dialog" in src
    assert "vpn_key" in src
