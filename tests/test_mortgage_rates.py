"""Tests for Freddie Mac PMMS mortgage-rate helpers."""

from __future__ import annotations

from app.core.mortgage_rates import (
    MortgageRateSnapshot,
    _parse_fred_data_page,
    _parse_pmms_html,
    resolve_interest_rate,
    should_autofill_interest_rate,
)


SAMPLE_PMMS_HTML = """
<html><body>
<p>U.S. weekly mortgage rate averages as of 07/16/2026</p>
<h2>30-year Fixed-Rate Mortgage</h2>
<p>6.55%</p>
<h2>15-year Fixed-Rate Mortgage</h2>
<p>5.93%</p>
</body></html>
"""


def test_parse_pmms_html_extracts_both_rates():
    snap = _parse_pmms_html(SAMPLE_PMMS_HTML)
    assert snap is not None
    assert snap.rate_30y == 6.55
    assert snap.rate_15y == 5.93
    assert snap.as_of == "2026-07-16"


def test_rate_for_term_picks_closer_product():
    snap = MortgageRateSnapshot(rate_30y=6.55, rate_15y=5.93, as_of="2026-07-16")
    assert snap.rate_for_term(15) == 5.93
    assert snap.rate_for_term(30) == 6.55
    assert snap.rate_for_term(20) == 5.93
    assert snap.rate_for_term(25) == 6.55
    assert "15-yr" in snap.source_caption(15)
    assert "30-yr" in snap.source_caption(30)


def test_parse_fred_data_page_last_row():
    text = """
| Date | Value |
| --- | --- |
| 2026-07-09 | 6.49 |
| 2026-07-16 | 6.55 |
"""
    assert _parse_fred_data_page(text) == ("2026-07-16", 6.55)


def test_should_autofill_interest_rate():
    assert should_autofill_interest_rate("")
    assert should_autofill_interest_rate("Freddie Mac PMMS 30-yr FRM · 2026-07-16")
    assert not should_autofill_interest_rate("Manual")


def test_resolve_interest_rate_uses_cache(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    snap = MortgageRateSnapshot(rate_30y=6.1, rate_15y=5.4, as_of="2026-07-16")
    monkeypatch.setattr(
        "app.core.mortgage_rates._fetch_from_pmms",
        lambda: snap,
    )
    monkeypatch.setattr(
        "app.core.mortgage_rates._fetch_from_fred",
        lambda: None,
    )
    rate30, src30 = resolve_interest_rate(30, force_refresh=True)
    rate15, src15 = resolve_interest_rate(15)
    assert rate30 == 6.1
    assert rate15 == 5.4
    assert src30.startswith("Freddie Mac")
    assert "15-yr" in src15
