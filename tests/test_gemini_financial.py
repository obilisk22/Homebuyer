from app.core.gemini_financial import (
    FINANCIAL_PROMPT_VERSION,
    ZillowListingRef,
    build_financial_fingerprint,
    build_financial_prompt,
    zillow_urls_digest,
)


def test_fingerprint_is_url_based():
    fp = build_financial_fingerprint(
        subject_zillow_url="https://www.zillow.com/homedetails/a_1_zpid/",
        peer_refs=[],
    )
    assert fp.startswith(f"{FINANCIAL_PROMPT_VERSION}|")
    assert len(fp) > len(FINANCIAL_PROMPT_VERSION) + 2


def test_fingerprint_changes_when_peers_change():
    subject = "https://www.zillow.com/homedetails/a_1_zpid/"
    a = build_financial_fingerprint(subject_zillow_url=subject, peer_refs=[])
    peers = [
        ZillowListingRef(
            property_id=2,
            zillow_url="https://www.zillow.com/homedetails/b_2_zpid/",
            label="Peer",
        )
    ]
    b = build_financial_fingerprint(subject_zillow_url=subject, peer_refs=peers)
    assert a != b


def test_fingerprint_stable_for_same_urls():
    subject = "https://www.zillow.com/homedetails/a_1_zpid/"
    peers = [
        ZillowListingRef(property_id=9, zillow_url="https://zillow.com/x_9_zpid/", label="X"),
        ZillowListingRef(property_id=2, zillow_url="https://zillow.com/y_2_zpid/", label="Y"),
    ]
    a = build_financial_fingerprint(subject_zillow_url=subject, peer_refs=peers)
    b = build_financial_fingerprint(subject_zillow_url=subject, peer_refs=list(reversed(peers)))
    assert a == b


def test_zillow_urls_digest_empty():
    assert zillow_urls_digest("") == "empty"


def test_prompt_lists_zillow_urls_and_opinion_sections():
    peers = [
        ZillowListingRef(
            property_id=2,
            zillow_url="https://www.zillow.com/homedetails/peer_2_zpid/",
            label="10 Peer St",
        )
    ]
    prompt = build_financial_prompt(
        subject_zillow_url="https://www.zillow.com/homedetails/subj_1_zpid/",
        subject_label="123 Main St",
        peer_refs=peers,
    )
    lower = prompt.lower()
    assert "https://www.zillow.com/homedetails/subj_1_zpid/" in prompt
    assert "https://www.zillow.com/homedetails/peer_2_zpid/" in prompt
    assert "10 Peer St" in prompt
    assert "url context" in lower
    assert "why the numbers look like this" in lower
    assert "buy vs rent" in lower
    assert "market" in lower
    # Must not ship app calculator dumps
    assert "cash to close" not in lower
    assert "piti calculator" not in lower


def test_prompt_requires_subject_url():
    try:
        build_financial_prompt(subject_zillow_url="")
        assert False, "expected ValueError"
    except ValueError:
        pass
