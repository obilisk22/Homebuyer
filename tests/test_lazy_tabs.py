"""Task 8: lazy property tabs + ensure_financial off the UI thread."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_property_page_lazy_mounts_modules():
    src = (ROOT / "app" / "ui" / "property_page.py").read_text(encoding="utf-8")
    assert "mounted" in src
    assert "ensure_tab" in src
    # Must not eagerly render every module inside the tab_panel loop.
    assert not re.search(
        r"for\s+mod\s+in\s+modules:\s*\n\s+with\s+ui\.tab_panel\([^)]+\):\s*\n"
        r"\s+panel\s*=\s*ui\.column\(\)[^\n]*\n\s+mod\.render\(prop,\s*panel\)",
        src,
    )
    assert "on_value_change" in src


def test_ensure_tab_marks_mounted_only_after_successful_render():
    src = (ROOT / "app" / "ui" / "property_page.py").read_text(encoding="utf-8")
    match = re.search(
        r"async def ensure_tab\(mod_id: str\) -> None:(.*?)(?=\n        async def |\n        tabs\.)",
        src,
        re.DOTALL,
    )
    assert match, "ensure_tab body not found"
    body = match.group(1)
    assert "mounted.add(mod_id)" in body
    add_pos = body.index("mounted.add(mod_id)")
    await_pos = body.rfind("await result")
    assert add_pos > await_pos, "mounted.add must run after await result"
    assert "except Exception" in body
    assert "retry_tab" in body


def test_ui_jobs_has_ensure_financial_job():
    src = (ROOT / "app" / "core" / "ui_jobs.py").read_text(encoding="utf-8")
    assert "def ensure_financial_job(" in src
    assert "ensure_financial(" in src


def test_financial_render_uses_ensure_financial_job_via_io_bound():
    src = (ROOT / "app" / "modules" / "financial.py").read_text(encoding="utf-8")
    assert "ensure_financial_job" in src
    assert re.search(r"await\s+run\.io_bound\(\s*ensure_financial_job", src)
    # Sync ensure_financial must not run at the top of render (PMMS on UI thread).
    assert "PropertyService(session).ensure_financial(" not in src


def test_ensure_financial_job_runs_ensure_financial(tmp_path, monkeypatch):
    from app.core import ui_jobs
    from app.core.db import get_session, init_db
    from app.core.models import Property
    from app.core.property_service import PropertyService

    monkeypatch.setenv("HOMEBUY_DATA_DIR", str(tmp_path))
    init_db()

    called: list[int] = []
    orig = PropertyService.ensure_financial

    def _wrap(self, prop):
        called.append(int(prop.id))
        return orig(self, prop)

    monkeypatch.setattr(PropertyService, "ensure_financial", _wrap)

    with get_session() as session:
        prop = Property(address="1 Test St", zillow_url="https://zillow.com/homedetails/1_zpid/")
        session.add(prop)
        session.commit()
        session.refresh(prop)
        pid = int(prop.id)

    ui_jobs.ensure_financial_job(pid)
    assert called == [pid]

    with get_session() as session:
        prop = session.get(Property, pid)
        assert prop is not None
        assert prop.financial is not None
