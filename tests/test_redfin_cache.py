"""Redfin ZIP market ingest — process memo, singleflight, gzip disk cache."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from app.core.cache import cache_dir, memo_clear, memo_get, read_json


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("HOMEBUY_DATA_DIR", str(tmp_path))
    from app.core import paths

    monkeypatch.setattr(paths, "DATA_DIR", Path(tmp_path))
    paths.refresh_data_dirs()
    memo_clear()
    yield
    memo_clear()


def test_load_zip_market_bundle_singleflight(monkeypatch):
    from app.core import redfin_sales as rs

    calls = {"n": 0}

    def fake_uncached():
        calls["n"] += 1
        time.sleep(0.05)
        return {
            "zips": {"90210": {"median_sale_price": 1.0, "homes_sold": 10}},
            "homes_sold_p75": 10.0,
        }

    monkeypatch.setattr(rs, "_load_bundle_uncached", fake_uncached)

    out: list[dict] = []

    def w():
        out.append(rs.load_zip_market_bundle())

    threads = [threading.Thread(target=w) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert calls["n"] == 1
    assert len(out) == 4
    assert all(o["zips"]["90210"]["homes_sold"] == 10 for o in out)


def test_load_zip_market_bundle_memo_avoids_reload(monkeypatch):
    from app.core import redfin_sales as rs

    calls = {"n": 0}

    def fake_uncached():
        calls["n"] += 1
        return {
            "zips": {"90066": {"median_sale_price": 1.0, "homes_sold": 20}},
            "homes_sold_p75": 12.0,
        }

    monkeypatch.setattr(rs, "_load_bundle_uncached", fake_uncached)

    first = rs.load_zip_market_bundle()
    second = rs.load_zip_market_bundle()
    assert calls["n"] == 1
    assert first is second or first == second
    assert memo_get("redfin", rs._ZIP_MARKET_CACHE_KEY) is not None


def test_redfin_write_gzip_on_ingest(monkeypatch):
    from app.core import redfin_sales as rs

    sample = {
        "90210": {
            "median_sale_price": 2_000_000.0,
            "period_end": "2025-06-30",
            "homes_sold": 15,
            "state_code": "CA",
        }
    }
    monkeypatch.setattr(rs, "_download_redfin_zip_medians", lambda: sample)

    bundle = rs._load_bundle_uncached()
    assert "90210" in bundle["zips"]
    gz = cache_dir("redfin") / f"{rs._ZIP_MARKET_CACHE_KEY}.json.gz"
    assert gz.is_file()
    disk = read_json("redfin", rs._ZIP_MARKET_CACHE_KEY, max_age_s=rs.CACHE_MAX_AGE_S)
    assert disk is not None
    assert disk["zips"]["90210"]["homes_sold"] == 15
    assert disk["homes_sold_p75"] == 15.0
