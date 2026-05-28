from backend.app.intel.entity_extractor import extract_entities_with_context
from backend.app.intel.pipeline import _audience_fit_score, _should_merge, build_intel_state, canonical_link, jaccard, title_dedupe_key


def test_canonical_link_removes_tracking_query_keys() -> None:
    link = "https://Example.com/news/story/?utm_source=x&from=wechat&id=42#section"
    assert canonical_link(link) == "https://example.com/news/story?id=42"


def test_title_dedupe_key_normalizes_punctuation_and_case() -> None:
    left = "OpenAI: GPT-5 发布！"
    right = "openai gpt5 发布"
    assert title_dedupe_key(left) == title_dedupe_key(right)


def test_jaccard_returns_zero_for_empty_sets() -> None:
    assert jaccard(set(), set()) == 0.0


def test_should_merge_prefers_exact_title_dedupe_match() -> None:
    left = {
        "canonical_link": "",
        "title_dedupe_key": title_dedupe_key("DeepSeek-TUI：在终端里跑 AI 编程 Agent"),
        "dedupe_key": "left",
        "title_tokens": ["deepseek", "tui", "agent"],
        "anchor_tokens": ["deepseek-tui"],
        "published_at": "2026-05-05T10:00:00+00:00",
        "tags": ["ai"],
        "platform": "github",
        "entity_ids": ["deepseek"],
    }
    right = {
        "canonical_link": "",
        "title_dedupe_key": title_dedupe_key("DeepSeek TUI 在终端里跑 AI 编程 Agent"),
        "dedupe_key": "right",
        "title_tokens": ["deepseek", "tui", "agent"],
        "anchor_tokens": ["deepseek-tui"],
        "published_at": "2026-05-05T11:00:00+00:00",
        "tags": ["ai"],
        "platform": "github",
        "entity_ids": ["deepseek"],
    }
    assert _should_merge(left, right) is True


def test_should_merge_rejects_low_similarity_cross_theme_items() -> None:
    left = {
        "canonical_link": "",
        "title_dedupe_key": "",
        "dedupe_key": "left",
        "title_tokens": ["openai", "health"],
        "anchor_tokens": ["openai"],
        "published_at": "2026-05-05T10:00:00+00:00",
        "tags": ["ai"],
        "platform": "rss",
        "entity_ids": ["openai"],
    }
    right = {
        "canonical_link": "",
        "title_dedupe_key": "",
        "dedupe_key": "right",
        "title_tokens": ["uber", "earnings"],
        "anchor_tokens": ["uber"],
        "published_at": "2026-05-07T10:00:00+00:00",
        "tags": ["finance"],
        "platform": "reddit",
        "entity_ids": ["uber"],
    }
    assert _should_merge(left, right) is False


def test_audience_fit_score_prefers_mainstream_tech_topics() -> None:
    mainstream = {
        "title": "苹果 iPhone 18 芯片升级，AI 手机竞争再升温",
        "summary": "新一代手机、芯片和端侧 AI 成为焦点",
        "entity_names": ["Apple"],
        "tags": ["hardware", "ai", "mobile"],
        "platform_count": 2,
        "source_count": 2,
    }
    niche = {
        "title": "NGINX CVE 漏洞影响 rewrite worker",
        "summary": "底层运维与安全配置细节",
        "entity_names": ["NGINX"],
        "tags": ["tech"],
        "platform_count": 1,
        "source_count": 1,
    }
    assert _audience_fit_score(mainstream) > _audience_fit_score(niche)


def test_entity_extraction_uses_precise_aliases_and_watchlist_context() -> None:
    watchlist = [{"entity_name": "OnePlus", "entity_type": "ORG", "watchlisted": True}]
    phone_watchlist = [
        {"entity_name": "HONOR", "entity_type": "ORG", "watchlisted": True},
        {"entity_name": "OnePlus", "entity_type": "ORG", "watchlisted": True},
        {"entity_name": "ZTE", "entity_type": "ORG", "watchlisted": True},
    ]

    assert [item["entity_name"] for item in extract_entities_with_context("Samsung Galaxy S26 Ultra privacy display")] == ["Samsung"]
    assert [item["entity_name"] for item in extract_entities_with_context("三星首款 PCIe Gen6 固态硬盘 PM1743 上线官网")] == ["Samsung"]
    assert [item["entity_name"] for item in extract_entities_with_context("Apple Updates Trade-In Values for iPhone")] == ["Apple"]
    assert [item["entity_name"] for item in extract_entities_with_context("苹果官网更新以旧换新估价 iPhone 等多款产品价值上调")] == ["Apple"]
    assert extract_entities_with_context("荣耀 600 Pro 青苹果图赏") == []
    assert [item["entity_name"] for item in extract_entities_with_context("OnePlus 15 gets a camera update", watchlist=watchlist)] == ["OnePlus"]
    assert [item["entity_name"] for item in extract_entities_with_context("荣耀 600 Pro 青苹果图赏", watchlist=phone_watchlist)] == ["HONOR"]
    assert [item["entity_name"] for item in extract_entities_with_context("一加 13 系统更新开始推送", watchlist=phone_watchlist)] == ["OnePlus"]
    assert [item["entity_name"] for item in extract_entities_with_context("中兴 Axon 新机通过认证", watchlist=phone_watchlist)] == ["ZTE"]


def test_build_intel_state_preserves_entities_from_official_sources() -> None:
    raw_items = [
        {
            "id": "raw-samsung-official",
            "source_key": "rss-samsung-newsroom-global",
            "source_name": "Samsung Newsroom Global",
            "source_kind": "rss",
            "title": "Next-gen Odyssey gaming monitors launch globally",
            "summary": "The new gaming monitor lineup adds higher refresh rates.",
            "link": "https://news.samsung.com/global/odyssey",
            "published_at": "2026-05-24T08:00:00+00:00",
            "collected_at": "2026-05-24T08:05:00+00:00",
        },
        {
            "id": "raw-oneplus-watchlist",
            "source_key": "rss-phone-news",
            "source_name": "Phone News",
            "source_kind": "rss",
            "title": "OnePlus 15 camera update starts rolling out",
            "summary": "The update improves low-light shots.",
            "link": "https://example.com/oneplus-15-camera",
            "published_at": "2026-05-24T08:10:00+00:00",
            "collected_at": "2026-05-24T08:12:00+00:00",
        },
        {
            "id": "raw-honor-official",
            "source_key": "yt-honor",
            "source_name": "HONOR",
            "source_kind": "monitor",
            "title": "New camera system launches this week",
            "summary": "The new phone brings upgraded portraits.",
            "link": "https://example.com/honor-camera",
            "published_at": "2026-05-24T08:15:00+00:00",
            "collected_at": "2026-05-24T08:16:00+00:00",
        },
    ]
    sources = {
        "rss-samsung-newsroom-global": {"key": "rss-samsung-newsroom-global", "name": "Samsung Newsroom Global", "kind": "rss", "platform": "rss", "weight": 0.9},
        "rss-phone-news": {"key": "rss-phone-news", "name": "Phone News", "kind": "rss", "platform": "rss", "weight": 0.7},
        "yt-honor": {"key": "yt-honor", "name": "HONOR", "kind": "monitor", "platform": "youtube", "weight": 0.8},
    }

    intel = build_intel_state(
        raw_items,
        sources,
        entity_watchlist=[
            {"entity_name": "OnePlus", "entity_type": "ORG", "watchlisted": True},
            {"entity_name": "HONOR", "entity_type": "ORG", "watchlisted": True},
        ],
        captured_at="2026-05-24T08:30:00+00:00",
    )

    discovery_by_id = {item["raw_item_id"]: item for item in intel["discovery_items"]}
    assert discovery_by_id["raw-samsung-official"]["entity_names"] == ["Samsung"]
    assert discovery_by_id["raw-oneplus-watchlist"]["entity_names"] == ["OnePlus"]
    assert discovery_by_id["raw-honor-official"]["entity_names"] == ["HONOR"]
    event_names = {name for event in intel["intel_events"] for name in event.get("entity_names", [])}
    assert {"Samsung", "OnePlus", "HONOR"} <= event_names
