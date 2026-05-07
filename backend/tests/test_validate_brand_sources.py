from scripts.validate_brand_sources import canonicalize_candidate_url, dedupe_strings, filter_brands


def test_canonicalize_candidate_url_keeps_rss_xml_variants() -> None:
    assert canonicalize_candidate_url("https://openai.com/news/rss.xml") == "https://openai.com/news/rss.xml"
    assert canonicalize_candidate_url("https://blogs.microsoft.com/feed.xml") == "https://blogs.microsoft.com/feed"


def test_dedupe_strings_keeps_first_case_variant() -> None:
    values = ["OpenAI", "openai", "OpenAI ", "Apple"]
    assert dedupe_strings(values) == ["OpenAI", "Apple"]


def test_filter_brands_matches_alias() -> None:
    results = filter_brands(["小米", "Apple"])
    names = [item.name for item in results]
    assert "Xiaomi" in names
    assert "Apple" in names
