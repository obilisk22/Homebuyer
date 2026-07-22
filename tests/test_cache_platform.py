from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest

from app.core.cache import (
    cache_dir,
    cache_key,
    memo_clear,
    memo_get,
    memo_set,
    prune_namespace,
    quantize_geojson,
    read_json,
    singleflight,
    write_json,
)


@pytest.fixture(autouse=True)
def _isolate_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("HOMEBUY_DATA_DIR", str(tmp_path))
    # paths.DATA_DIR is resolved at import in some modules — re-bind cache root if needed
    from app.core import paths
    monkeypatch.setattr(paths, "DATA_DIR", Path(tmp_path))
    memo_clear()
    yield
    memo_clear()


def test_disk_roundtrip_and_ttl(tmp_path):
    write_json("t", "k1", {"a": 1})
    assert read_json("t", "k1", max_age_s=60) == {"a": 1}
    path = cache_dir("t") / "k1.json"
    # expire by rewriting mtime
    older = time.time() - 120
    import os
    os.utime(path, (older, older))
    assert read_json("t", "k1", max_age_s=60) is None


def test_gzip_roundtrip():
    write_json("t", "gz", {"n": list(range(50))}, gzip=True)
    assert (cache_dir("t") / "gz.json.gz").is_file()
    assert read_json("t", "gz", max_age_s=60)["n"][0] == 0


def test_memo_ttl():
    memo_set("m", "x", 42, ttl_s=0.2)
    assert memo_get("m", "x") == 42
    time.sleep(0.25)
    assert memo_get("m", "x") is None


def test_singleflight_coalesces():
    calls = {"n": 0}
    barrier = threading.Barrier(3)

    def factory():
        calls["n"] += 1
        time.sleep(0.1)
        return "ok"

    results = []

    def worker():
        barrier.wait()
        results.append(singleflight("sf", "one", factory))

    threads = [threading.Thread(target=worker) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results == ["ok", "ok", "ok"]
    assert calls["n"] == 1


def test_quantize_geojson_shrinks_coords():
    fc = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"zone_code": "R1"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [-118.123456789, 34.123456789],
                            [-118.123456780, 34.123456780],
                            [-118.12, 34.12],
                            [-118.123456789, 34.123456789],
                        ]
                    ],
                },
            }
        ],
    }
    out = quantize_geojson(fc, precision=5)
    ring = out["features"][0]["geometry"]["coordinates"][0]
    assert ring[0] == [-118.12346, 34.12346]
    assert json.dumps(out) != json.dumps(fc)


def test_cache_key_stable():
    assert cache_key("a", "b") == cache_key("a", "b")
    assert cache_key("a", "b") != cache_key("a", "c")


def test_prune_namespace_removes_old():
    write_json("oldns", "a", {"x": 1})
    path = cache_dir("oldns") / "a.json"
    older = time.time() - 9999
    import os
    os.utime(path, (older, older))
    assert prune_namespace("oldns", max_age_s=60) >= 1
    assert read_json("oldns", "a") is None
