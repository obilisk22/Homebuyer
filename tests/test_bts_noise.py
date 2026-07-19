"""BTS noise tile helpers (TODO-041)."""

from app.core.bts_noise import (
    BTS_NOISE_TILE_URL,
    NOISE_STATUS_DISCLAIMER,
    noise_tile_layer_args,
)


def test_noise_tile_layer_args():
    url, opts = noise_tile_layer_args()
    assert "{z}" in url and "{y}" in url and "{x}" in url
    assert "NTAD_Noise_2020" in url
    assert opts.get("opacity", 0) > 0
    assert "BTS" in (opts.get("attribution") or "")
    assert "screening" in NOISE_STATUS_DISCLAIMER.lower() or "parcel" in NOISE_STATUS_DISCLAIMER.lower()
    assert BTS_NOISE_TILE_URL == url
