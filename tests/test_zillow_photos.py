from app.core.zillow_photos import extract_photo_urls


SAMPLE_HTML = """
<html><body>
<img src="https://photos.zillowstatic.com/fp/abc123def456abc123def456abc123de-p_e.jpg"/>
<img src="https://photos.zillowstatic.com/fp/abc123def456abc123def456abc123de-cc_ft_384.jpg"/>
<img src="https://photos.zillowstatic.com/fp/abc123def456abc123def456abc123de-o_a.jpg"/>
<img src="https://photos.zillowstatic.com/fp/aaa111bbb222ccc333ddd444eee555ff-sc_192_128.jpg"/>
<img src="https://photos.zillowstatic.com/fp/fff000eee111ddd222ccc333bbb444aa-cc_ft_1536.jpg"/>
</body></html>
"""


def test_extract_prefers_high_res_and_dedupes():
    urls = extract_photo_urls(SAMPLE_HTML)
    assert len(urls) == 2
    assert urls[0].endswith("-o_a.jpg")
    assert any("cc_ft_1536" in u for u in urls)


def test_extract_skips_ui_thumbs_only():
    html = (
        '<img src="https://photos.zillowstatic.com/fp/'
        'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-sc_192_128.jpg"/>'
    )
    assert extract_photo_urls(html) == []
