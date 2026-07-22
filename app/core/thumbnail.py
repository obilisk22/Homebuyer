"""Pick a front-of-house style photo for library card thumbnails."""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps

# Library/header card derivative (sidecar beside Photo.path).
THUMB_LONG_EDGE = 400
THUMB_WEBP_QUALITY = 80
# Stored mid/full file long-edge cap (Photo.path); lightbox uses this file.
MID_LONG_EDGE = 1600

# Caption / URL / path tokens that usually are not curb appeal.
AVOID_KEYWORDS = (
    "floorplan",
    "floor-plan",
    "floor_plan",
    "floor plan",
    "siteplan",
    "site-plan",
    "site plan",
    "blueprint",
    "plat map",
    "diagram",
    "schematic",
    "matterport",
    "3d-tour",
    "3d_tour",
    "-map",
    "/map",
    "logo",
)

# Positive cues when Zillow or the user labeled the shot.
EXTERIOR_KEYWORDS = (
    "exterior",
    "front",
    "facade",
    "façade",
    "curb",
    "street view",
    "elevation",
    "outside",
    "outdoor",
    "yard",
    "driveway",
    "porch",
    "entrance",
    "entry",
    "frontage",
    "garage",
)

# Room / interior captions — prefer almost anything else for library thumbs.
INTERIOR_KEYWORDS = (
    "kitchen",
    "bathroom",
    "bedroom",
    "living",
    "closet",
    "laundry",
    "pantry",
    "ceiling",
    "island",
    "granite",
    "dining",
    "hallway",
    "fireplace",
    "master bath",
    "en-suite",
    "ensuite",
)


@dataclass(frozen=True)
class PhotoCandidate:
    photo_id: int
    path: str
    source_url: str = ""
    caption: str = ""
    sort_order: int = 0


def _text_blob(candidate: PhotoCandidate) -> str:
    return f"{candidate.caption} {candidate.source_url} {candidate.path}".lower()


def keyword_score(candidate: PhotoCandidate) -> float:
    text = _text_blob(candidate)
    score = 0.0
    for kw in AVOID_KEYWORDS:
        if kw in text:
            score -= 100.0
    for kw in INTERIOR_KEYWORDS:
        if kw in text:
            score -= 100.0
    for kw in EXTERIOR_KEYWORDS:
        if kw in text:
            score += 40.0
    return score


def image_score(absolute_path: Path) -> float:
    """Cheap Pillow cues: landscape, skip blank/diagram-like frames, sky hint."""
    try:
        with Image.open(absolute_path) as im:
            rgb = im.convert("RGB")
            width, height = rgb.size
            if width < 8 or height < 8:
                return -50.0

            score = 0.0
            aspect = width / height
            if aspect >= 1.15:
                score += 25.0
            elif aspect < 0.85:
                score -= 15.0

            thumb = rgb.resize((64, 48))
            pixels = list(thumb.get_flattened_data())
            n = len(pixels) or 1

            whiteish = sum(1 for r, g, b in pixels if r > 240 and g > 240 and b > 240)
            if whiteish / n > 0.55:
                # Floor plans / line drawings are often mostly paper-white.
                score -= 80.0

            lums = [0.299 * r + 0.587 * g + 0.114 * b for r, g, b in pixels]
            mean = sum(lums) / n
            variance = sum((x - mean) ** 2 for x in lums) / n
            if variance < 200:
                score -= 20.0

            top = list(thumb.crop((0, 0, 64, 16)).get_flattened_data())
            blueish = sum(1 for r, g, b in top if b > r + 15 and b > g + 5 and b > 80)
            blue_ratio = blueish / len(top)
            if blue_ratio > 0.2:
                score += 20.0

            # Modest indoor cue: non-landscape, no sky top, warm tones.
            warmth = [(r + g) / 2.0 for r, g, b in pixels]
            mean_warmth = sum(warmth) / n
            mean_b = sum(b for _r, _g, b in pixels) / n
            if aspect < 1.15 and blue_ratio <= 0.2 and mean_warmth > 120 and mean_b < mean_warmth - 10:
                score -= 25.0

            return score
    except OSError:
        return 0.0


def listing_order_score(sort_order: int) -> float:
    """Zillow heroes are usually early; do not rely on index 0 alone."""
    return max(0.0, 30.0 - float(sort_order) * 3.0)


def score_photo(candidate: PhotoCandidate, uploads_root: Path | None = None) -> float:
    score = keyword_score(candidate) + listing_order_score(candidate.sort_order)
    if uploads_root is not None:
        path = uploads_root / candidate.path
        if path.is_file():
            score += image_score(path)
    return score


def pick_thumbnail_photo_id(
    candidates: list[PhotoCandidate],
    uploads_root: Path | None = None,
) -> int | None:
    if not candidates:
        return None
    best = max(candidates, key=lambda c: score_photo(c, uploads_root))
    return best.photo_id


def sidecar_thumb_path(image_path: Path) -> Path:
    """`foo.jpg` → `foo_thumb.webp` beside the same directory."""
    return image_path.with_name(f"{image_path.stem}_thumb.webp")


def _fit_long_edge(im: Image.Image, max_edge: int) -> Image.Image:
    width, height = im.size
    long_edge = max(width, height)
    if long_edge <= max_edge:
        return im.copy()
    scale = max_edge / float(long_edge)
    new_size = (max(1, round(width * scale)), max(1, round(height * scale)))
    return im.resize(new_size, Image.Resampling.LANCZOS)


def _save_mid_image(im: Image.Image, dest: Path) -> None:
    suffix = dest.suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        im.convert("RGB").save(dest, format="JPEG", quality=85, optimize=True)
    elif suffix == ".png":
        im.save(dest, format="PNG", optimize=True)
    elif suffix == ".webp":
        im.save(dest, format="WEBP", quality=85)
    elif suffix == ".gif":
        im.save(dest, format="GIF")
    else:
        im.convert("RGB").save(dest, format="JPEG", quality=85, optimize=True)


def write_photo_with_derivatives(dest: Path, data: bytes) -> None:
    """Write mid-size image (cap ~1600) and ``*_thumb.webp`` sidecar (~400).

    On decode failure, writes raw ``data`` and skips the sidecar so import
    never fails on a bad bytes payload.
    """
    try:
        with Image.open(io.BytesIO(data)) as raw:
            raw.load()
            oriented = ImageOps.exif_transpose(raw)
            mid = _fit_long_edge(oriented, MID_LONG_EDGE)
            _save_mid_image(mid, dest)
            thumb = _fit_long_edge(oriented, THUMB_LONG_EDGE)
            thumb_path = sidecar_thumb_path(dest)
            thumb.convert("RGB").save(
                thumb_path, format="WEBP", quality=THUMB_WEBP_QUALITY, method=4
            )
    except OSError:
        dest.write_bytes(data)


def resolve_library_thumbnail_url(
    photo: Any,
    *,
    uploads_root: Path | None = None,
) -> str:
    """Prefer ``stem_thumb.webp`` beside ``Photo.path``; fall back to full."""
    from app.core.paths import UPLOADS_DIR

    root = UPLOADS_DIR if uploads_root is None else uploads_root
    rel = str(getattr(photo, "path", "") or "").replace("\\", "/")
    if not rel:
        return "/uploads/"
    full = root / rel
    thumb = sidecar_thumb_path(full)
    if thumb.is_file():
        thumb_rel = str(thumb.relative_to(root)).replace("\\", "/")
        return f"/uploads/{thumb_rel}"
    return f"/uploads/{rel}"
