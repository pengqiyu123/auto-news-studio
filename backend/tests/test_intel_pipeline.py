from backend.app.intel_pipeline import _should_merge, canonical_link, jaccard, title_dedupe_key


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
