"""Redfin Data Center ZIP median sale price → ZCTA choropleth (no API key).

Downloads the public Redfin zip-code market tracker TSV (gzip on S3), keeps a
slim cache of the latest monthly **All Residential** ``median_sale_price`` per
ZIP, then joins those prices to Census TIGER ZCTA polygons near the pin.

National TSV is large; we stream it once and cache ``zip → price`` JSON under
``data/cache/redfin/`` (~7 day TTL). ZCTA geometry is bbox-queried like ACS
tracts (no nationwide polygon download).

Missing joins (ZIP in Redfin but no ZCTA poly, or poly with no sale) keep a
muted fill and a popup noting the gap.
"""

from __future__ import annotations

import csv
import gzip
import io
import re
from typing import Any
from urllib.request import urlopen

import requests

from app.core.census_acs import fill_color_for_breaks
from app.core.overlay_cache import cache_dir, cache_key, read_json, write_json

REQUEST_TIMEOUT_S = 120
CACHE_MAX_AGE_S = 7 * 24 * 3600
DEFAULT_HALF_SPAN_DEG = 0.06

REDFIN_ZIP_TSV_URL = (
    "https://redfin-public-data.s3.us-west-2.amazonaws.com/"
    "redfin_market_tracker/zip_code_market_tracker.tsv000.gz"
)

TIGER_ZCTA_QUERY_URL = (
    "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/"
    "PUMA_TAD_TAZ_UGA_ZCTA/MapServer/1/query"
)

# Sale-price breaks tuned for CA coastal metros; muted for missing.
SALE_BREAKS: list[tuple[float, str]] = [
    (400_000, "#1a237e"),
    (700_000, "#00838f"),
    (1_000_000, "#00E5FF"),
    (1_500_000, "#B8FF3C"),
    (2_500_000, "#FFC107"),
    (10**12, "#FF2BD6"),
]

SALE_LEGEND: list[tuple[str, str]] = [
    ("<$400k", "#1a237e"),
    ("$400–700k", "#00838f"),
    ("$700k–1M", "#00E5FF"),
    ("$1–1.5M", "#B8FF3C"),
    ("$1.5–2.5M", "#FFC107"),
    ("$2.5M+", "#FF2BD6"),
]

_ZIP_RE = re.compile(r"(\d{5})")


def parse_zip_from_region(region: str) -> str | None:
    """Extract 5-digit ZIP from Redfin ``region`` (e.g. ``Zip Code: 90066``)."""
    if not region:
        return None
    m = _ZIP_RE.search(str(region))
    return m.group(1) if m else None


def _parse_price(raw: object) -> float | None:
    if raw is None or raw == "":
        return None
    try:
        val = float(str(raw).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    if val <= 0:
        return None
    return val


def parse_redfin_zip_rows(
    rows: list[dict[str, str]],
    *,
    property_type: str = "All Residential",
    period_duration: int | None = 30,
) -> dict[str, dict[str, Any]]:
    """Build ``zip → {median_sale_price, period_end, ...}`` keeping newest period.

    Prefers monthly rows (``period_duration == 30``) when that column exists.
    """
    best: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        ptype = (row.get("property_type") or row.get("property_type_id") or "").strip()
        if property_type and ptype and ptype != property_type:
            continue
        if period_duration is not None and "period_duration" in row:
            try:
                dur = int(float(row["period_duration"]))
            except (TypeError, ValueError):
                continue
            if dur != period_duration:
                continue
        zip_code = parse_zip_from_region(row.get("region") or row.get("postal_code") or "")
        if not zip_code and row.get("region_name"):
            zip_code = parse_zip_from_region(row["region_name"])
        if not zip_code:
            continue
        price = _parse_price(row.get("median_sale_price"))
        if price is None:
            continue
        period_end = (row.get("period_end") or row.get("period_begin") or "").strip()
        prev = best.get(zip_code)
        if prev is None or period_end >= str(prev.get("period_end") or ""):
            best[zip_code] = {
                "median_sale_price": price,
                "period_end": period_end,
                "state_code": (row.get("state_code") or "").strip(),
            }
    return best


def _ingest_redfin_reader(reader: csv.DictReader) -> dict[str, dict[str, Any]]:
    """One-row-at-a-time ingest (never materializes the full TSV)."""
    best: dict[str, dict[str, Any]] = {}
    for row in reader:
        if not isinstance(row, dict):
            continue
        ptype = (row.get("property_type") or "").strip()
        if ptype and ptype != "All Residential":
            continue
        if "period_duration" in row and row["period_duration"] not in ("", None):
            try:
                if int(float(row["period_duration"])) != 30:
                    continue
            except (TypeError, ValueError):
                continue
        zip_code = parse_zip_from_region(row.get("region") or "")
        if not zip_code:
            continue
        price = _parse_price(row.get("median_sale_price"))
        if price is None:
            continue
        period_end = (row.get("period_end") or "").strip()
        prev = best.get(zip_code)
        if prev is None or period_end >= str(prev.get("period_end") or ""):
            best[zip_code] = {
                "median_sale_price": price,
                "period_end": period_end,
                "state_code": (row.get("state_code") or "").strip(),
            }
    return best


def _stream_redfin_zip_medians() -> dict[str, dict[str, Any]]:
    """Download + stream-parse Redfin ZIP TSV → slim zip map (cached)."""
    key = "zip_medians_all_residential_monthly"
    cached = read_json("redfin", key, max_age_s=CACHE_MAX_AGE_S)
    if isinstance(cached, dict) and isinstance(cached.get("zips"), dict) and cached["zips"]:
        return {str(k): dict(v) for k, v in cached["zips"].items()}

    cache_dir("redfin")
    last_err: Exception | None = None
    best: dict[str, dict[str, Any]] = {}
    try:
        resp = requests.get(REDFIN_ZIP_TSV_URL, stream=True, timeout=REQUEST_TIMEOUT_S)
        resp.raise_for_status()
        raw = gzip.GzipFile(fileobj=resp.raw)
        text = io.TextIOWrapper(raw, encoding="utf-8", errors="replace")
        best = _ingest_redfin_reader(csv.DictReader(text, delimiter="\t"))
    except Exception as exc:  # noqa: BLE001
        last_err = exc
        try:
            with urlopen(REDFIN_ZIP_TSV_URL, timeout=REQUEST_TIMEOUT_S) as fh:  # noqa: S310
                with gzip.GzipFile(fileobj=fh) as gz:
                    text = io.TextIOWrapper(gz, encoding="utf-8", errors="replace")
                    best = _ingest_redfin_reader(csv.DictReader(text, delimiter="\t"))
        except Exception as exc2:  # noqa: BLE001
            raise RuntimeError(
                f"Redfin ZIP market tracker download failed: {exc2}"
            ) from (exc2 or last_err)

    if not best:
        raise RuntimeError("Redfin ZIP market tracker returned no usable medians")

    write_json(
        "redfin",
        key,
        {"zips": best, "source": REDFIN_ZIP_TSV_URL, "count": len(best)},
    )
    return best


def load_zip_medians() -> dict[str, dict[str, Any]]:
    """Public entry: cached zip → median sale dict."""
    return _stream_redfin_zip_medians()


def _fetch_zcta_geojson(
    bbox: tuple[float, float, float, float],
) -> dict[str, Any]:
    min_lng, min_lat, max_lng, max_lat = bbox
    key = cache_key(
        "zcta",
        f"{min_lng:.3f}",
        f"{min_lat:.3f}",
        f"{max_lng:.3f}",
        f"{max_lat:.3f}",
    )
    cached = read_json("tiger_zcta", key, max_age_s=CACHE_MAX_AGE_S)
    if isinstance(cached, dict) and cached.get("type") == "FeatureCollection":
        return cached

    geometry = f"{min_lng},{min_lat},{max_lng},{max_lat}"
    last_err: Exception | None = None
    # Layer 1 is ZCTA5 on PUMA_TAD_TAZ_UGA_ZCTA; also try layer 0 if empty.
    for layer_url in (
        TIGER_ZCTA_QUERY_URL,
        TIGER_ZCTA_QUERY_URL.replace("/1/query", "/0/query"),
    ):
        try:
            resp = requests.get(
                layer_url,
                params={
                    "where": "1=1",
                    "geometry": geometry,
                    "geometryType": "esriGeometryEnvelope",
                    "inSR": "4326",
                    "spatialRel": "esriSpatialRelIntersects",
                    "outFields": "ZCTA5,GEOID,BASENAME,NAME",
                    "returnGeometry": "true",
                    "outSR": "4326",
                    "f": "geojson",
                },
                timeout=REQUEST_TIMEOUT_S,
            )
            resp.raise_for_status()
            payload = resp.json()
            if not isinstance(payload, dict):
                raise ValueError("Unexpected TIGER ZCTA response")
            feats = payload.get("features") or []
            if feats:
                write_json("tiger_zcta", key, payload)
                return payload
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            continue
    if last_err:
        raise RuntimeError(f"ZCTA boundary query failed: {last_err}") from last_err
    empty = {"type": "FeatureCollection", "features": []}
    write_json("tiger_zcta", key, empty)
    return empty


def _zcta_id(props: dict[str, Any]) -> str | None:
    for field in ("ZCTA5", "GEOID", "BASENAME", "NAME", "ZCTA5CE20", "ZCTA5CE10"):
        raw = props.get(field)
        if raw is None:
            continue
        z = parse_zip_from_region(str(raw))
        if z:
            return z
    return None


def _fmt_price(value: float | None) -> str:
    if value is None:
        return "—"
    if value >= 1_000_000:
        return f"${value / 1_000_000:.2f}M"
    return f"${value:,.0f}"


def build_redfin_sales_geojson(
    lat: float,
    lng: float,
    *,
    half_span_deg: float = DEFAULT_HALF_SPAN_DEG,
) -> dict[str, Any]:
    """ZCTA FeatureCollection colored by Redfin median sale price."""
    bbox = (
        lng - half_span_deg,
        lat - half_span_deg,
        lng + half_span_deg,
        lat + half_span_deg,
    )
    medians = load_zip_medians()
    geo = _fetch_zcta_geojson(bbox)

    joined = 0
    missing = 0
    features: list[dict[str, Any]] = []
    period_hint = ""
    for feat in geo.get("features") or []:
        props = dict(feat.get("properties") or {})
        zcta = _zcta_id(props)
        info = medians.get(zcta or "") if zcta else None
        price = float(info["median_sale_price"]) if info else None
        if price is not None:
            joined += 1
            if not period_hint:
                period_hint = str(info.get("period_end") or "")
        else:
            missing += 1
        color = fill_color_for_breaks(price, SALE_BREAKS)
        label = _fmt_price(price)
        name = zcta or props.get("NAME") or "ZCTA"
        note = ""
        if price is None:
            note = "<br><i>No Redfin median for this ZIP</i>"
        period = (info or {}).get("period_end") or ""
        period_bit = f"<br>Period ending {period}" if period else ""
        props.update(
            {
                "ZCTA": zcta,
                "median_sale_price": price,
                "fillColor": color,
                "popup": (
                    f"ZIP {name}<br>Median sale: {label}"
                    f"{period_bit}{note}<br>(Redfin Data Center)"
                ),
            }
        )
        features.append(
            {
                "type": "Feature",
                "geometry": feat.get("geometry"),
                "properties": props,
            }
        )

    msg = (
        f"Redfin median sale: {joined} ZCTAs joined"
        + (f", {missing} without sale data" if missing else "")
        + (f" · through {period_hint}" if period_hint else "")
    )
    if not features:
        msg = "No ZCTA polygons near pin for sale-price layer"

    return {
        "type": "FeatureCollection",
        "features": features,
        "meta": {
            "joined": joined,
            "missing": missing,
            "period_end": period_hint,
            "message": msg,
            "source": "Redfin Data Center zip market tracker",
        },
    }
