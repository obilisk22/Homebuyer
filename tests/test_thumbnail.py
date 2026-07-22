from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from app.core.thumbnail import (
    PhotoCandidate,
    keyword_score,
    pick_thumbnail_photo_id,
    resolve_library_thumbnail_url,
    score_photo,
)


def test_avoids_floorplan_by_caption():
    candidates = [
        PhotoCandidate(1, "1/a.jpg", caption="Floor plan", sort_order=0),
        PhotoCandidate(2, "1/b.jpg", caption="Front exterior", sort_order=1),
        PhotoCandidate(3, "1/c.jpg", caption="Living room", sort_order=2),
    ]
    assert pick_thumbnail_photo_id(candidates) == 2


def test_avoids_map_url_tokens():
    candidates = [
        PhotoCandidate(
            1,
            "1/map.jpg",
            source_url="https://photos.example.com/fp/abc-map.jpg",
            sort_order=0,
        ),
        PhotoCandidate(2, "1/house.jpg", caption="Zillow photo 2", sort_order=1),
    ]
    assert pick_thumbnail_photo_id(candidates) == 2


def test_prefers_earlier_listing_order_without_labels():
    candidates = [
        PhotoCandidate(10, "1/late.jpg", caption="Zillow photo 5", sort_order=4),
        PhotoCandidate(11, "1/early.jpg", caption="Zillow photo 1", sort_order=0),
        PhotoCandidate(12, "1/mid.jpg", caption="Zillow photo 3", sort_order=2),
    ]
    assert pick_thumbnail_photo_id(candidates) == 11


def test_keyword_score_exterior_beats_generic():
    exterior = PhotoCandidate(1, "x.jpg", caption="Curb appeal exterior")
    interior = PhotoCandidate(2, "y.jpg", caption="Kitchen remodel")
    assert keyword_score(exterior) > keyword_score(interior)


def test_avoids_kitchen_caption_even_when_first():
    # Without interior penalties, early listing order wins over a generic second shot.
    candidates = [
        PhotoCandidate(1, "1/a.jpg", caption="Living room", sort_order=0),
        PhotoCandidate(2, "1/b.jpg", caption="Zillow photo 2", sort_order=1),
    ]
    assert pick_thumbnail_photo_id(candidates) == 2


def test_avoids_bedroom_and_bathroom_keywords():
    candidates = [
        PhotoCandidate(1, "1/a.jpg", caption="Primary bedroom suite", sort_order=0),
        PhotoCandidate(2, "1/b.jpg", caption="Full bathroom", sort_order=1),
        PhotoCandidate(3, "1/c.jpg", caption="Zillow photo 3", sort_order=2),
    ]
    assert pick_thumbnail_photo_id(candidates) == 3


def test_image_heuristic_prefers_landscape_over_floorplan_white(tmp_path: Path):
    outdoor = tmp_path / "outdoor.jpg"
    floorplan = tmp_path / "plan.jpg"

    # Landscape with blue sky band at top.
    sky = Image.new("RGB", (320, 200), (90, 140, 210))
    ground = Image.new("RGB", (320, 140), (70, 110, 60))
    canvas = Image.new("RGB", (320, 240))
    canvas.paste(sky, (0, 0))
    canvas.paste(ground, (0, 100))
    canvas.save(outdoor)

    Image.new("RGB", (240, 240), (252, 252, 252)).save(floorplan)

    candidates = [
        PhotoCandidate(1, "plan.jpg", caption="Zillow photo 1", sort_order=0),
        PhotoCandidate(2, "outdoor.jpg", caption="Zillow photo 2", sort_order=1),
    ]
    assert pick_thumbnail_photo_id(candidates, uploads_root=tmp_path) == 2
    assert score_photo(candidates[1], uploads_root=tmp_path) > score_photo(
        candidates[0], uploads_root=tmp_path
    )


def test_resolve_library_thumbnail_url_prefers_sidecar(tmp_path: Path):
    full = tmp_path / "42" / "zillow_000.jpg"
    full.parent.mkdir(parents=True)
    Image.new("RGB", (80, 60), (10, 20, 30)).save(full)
    thumb = full.with_name("zillow_000_thumb.webp")
    Image.new("RGB", (40, 30), (10, 20, 30)).save(thumb, "WEBP")

    photo = SimpleNamespace(path="42/zillow_000.jpg")
    assert resolve_library_thumbnail_url(photo, uploads_root=tmp_path) == (
        "/uploads/42/zillow_000_thumb.webp"
    )


def test_resolve_library_thumbnail_url_falls_back_to_full(tmp_path: Path):
    full = tmp_path / "7" / "house.jpg"
    full.parent.mkdir(parents=True)
    Image.new("RGB", (80, 60), (1, 2, 3)).save(full)

    photo = SimpleNamespace(path="7/house.jpg")
    assert resolve_library_thumbnail_url(photo, uploads_root=tmp_path) == (
        "/uploads/7/house.jpg"
    )
