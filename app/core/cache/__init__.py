"""Shared cache platform: disk, memo, singleflight, SWR, GeoJSON quantize."""

from app.core.cache.disk import cache_dir, cache_key, prune_namespace, read_json, write_json
from app.core.cache.geojson_quantize import quantize_geojson
from app.core.cache.memo import memo_clear, memo_get, memo_set
from app.core.cache.singleflight import singleflight
from app.core.cache.swr import swr_get

__all__ = [
    "cache_dir",
    "cache_key",
    "memo_clear",
    "memo_get",
    "memo_set",
    "prune_namespace",
    "quantize_geojson",
    "read_json",
    "singleflight",
    "swr_get",
    "write_json",
]
