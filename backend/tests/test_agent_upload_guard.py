from copy import deepcopy
from pathlib import Path
import tempfile
import shutil
import sys
import types

import pytest

if "trafilatura" not in sys.modules:
    trafilatura_stub = types.ModuleType("trafilatura")
    trafilatura_stub.extract = lambda *args, **kwargs: ""
    sys.modules["trafilatura"] = trafilatura_stub

if "readability" not in sys.modules:
    readability_stub = types.ModuleType("readability")

    class _Document:
        def __init__(self, html: str) -> None:
            self._html = html

        def summary(self, html_partial: bool = True) -> str:
            return self._html

    readability_stub.Document = _Document
    sys.modules["readability"] = readability_stub

if "openai" not in sys.modules:
    openai_stub = types.ModuleType("openai")

    class _OpenAIError(Exception):
        pass

    class _OpenAI:
        def __init__(self, *args, **kwargs) -> None:
            pass

    openai_stub.APIConnectionError = _OpenAIError
    openai_stub.APITimeoutError = _OpenAIError
    openai_stub.AuthenticationError = _OpenAIError
    openai_stub.BadRequestError = _OpenAIError
    openai_stub.InternalServerError = _OpenAIError
    openai_stub.NotFoundError = _OpenAIError
    openai_stub.OpenAI = _OpenAI
    openai_stub.RateLimitError = _OpenAIError
    sys.modules["openai"] = openai_stub

from backend.app.models import AgentArticlePayload
from backend.app.store import StudioStore


def _make_store_and_state() -> tuple[StudioStore, dict, Path]:
    temp_root = Path(tempfile.mkdtemp(prefix="agent-guard-"))
    store = StudioStore(data_file=temp_root / "data" / "state.json")
    state = store._upgrade_state(store._read())
    state["intel_events"] = [
        {
            "id": "evt-1",
            "title": "Test Event",
            "summary": "summary",
            "alert_state": "watch",
            "entity_names": [],
            "entity_ids": [],
            "brief_id": None,
        }
    ]
    state["event_deep_dives"] = [
        {
            "id": "dd-1",
            "event_id": "evt-1",
            "status": "ready",
            "sources": [],
            "worthiness": {"reason": "worth watching"},
            "updated_at": "2026-05-06T00:00:00+08:00",
        }
    ]
    return store, state, temp_root


def test_agent_article_upload_rejected_while_scheduler_running(monkeypatch: pytest.MonkeyPatch) -> None:
    store, state, temp_root = _make_store_and_state()
    state["runtime"]["scheduler_running"] = True
    state["runtime"]["control_state"] = "running"
    state["runtime"]["current_cycle"] = "collecting"
    state["runtime"]["automation_run"] = {
        "status": "running",
        "stage": "collecting",
        "heartbeat_at": "2026-05-06T17:40:00+08:00",
    }

    monkeypatch.setattr(store, "_read", lambda: deepcopy(state))
    monkeypatch.setattr(store, "_write", lambda payload: None)

    payload = AgentArticlePayload(
        event_id="evt-1",
        title="Agent Article",
        article_markdown="# Agent Article\n\nbody",
        publish_to_wechat_draft=True,
        triggered_by="agent",
    )

    with pytest.raises(ValueError, match="当前自动调度器正在运行"):
        store.create_agent_article(payload)
    shutil.rmtree(temp_root, ignore_errors=True)


def test_agent_article_defaults_to_save_only(monkeypatch: pytest.MonkeyPatch) -> None:
    store, state, temp_root = _make_store_and_state()
    state["event_deep_dives"][0]["sources"] = [
        {
            "source_name": "Example",
            "canonical_link": "https://example.com/default-save-only",
            "original_link": "https://example.com/default-save-only",
            "title": "Test Event",
            "cleaned_full_text": "Test Event 摘要。",
            "quotes": [],
        }
    ]
    state["event_deep_dives"][0]["facts"] = ["Test Event 摘要"]
    store._write(state)
    calls: list[str] = []

    def fake_sync_brief_wechat_draft(brief_id: str, triggered_by: str = "dashboard"):
        calls.append(f"{brief_id}:{triggered_by}")
        raise AssertionError("Default Agent article save must not upload to WeChat")

    monkeypatch.setattr(store, "sync_brief_wechat_draft", fake_sync_brief_wechat_draft)

    payload = AgentArticlePayload(
        event_id="evt-1",
        title="Agent Article",
        article_markdown="# Agent Article\n\nbody",
        triggered_by="agent",
        driver_label="codex",
    )

    result = store.create_agent_article(payload)

    assert result.brief_level == "article"
    assert result.workflow_mode == "agent"
    assert calls == []
    shutil.rmtree(temp_root, ignore_errors=True)


def test_agent_article_douyin_publish_uses_daily_news_digest(monkeypatch: pytest.MonkeyPatch) -> None:
    store, state, temp_root = _make_store_and_state()
    state["intel_events"][0]["source_count"] = 2
    state["intel_events"][0]["worth_to_brief"] = True
    state["intel_events"][0]["composite_score"] = 100
    state["event_deep_dives"][0]["success_count"] = 1
    state["event_deep_dives"][0]["sources"] = [
        {
            "source_name": "Example",
            "canonical_link": "https://example.com/news-1",
            "original_link": "https://example.com/news-1",
            "title": "Test Event",
            "cleaned_full_text": "Test Event 摘要。",
            "quotes": [],
        }
    ]
    state["event_deep_dives"][0]["facts"] = ["Test Event 摘要"]
    for index in range(2, 6):
        event_id = f"evt-{index}"
        state["intel_events"].append(
            {
                "id": event_id,
                "title": f"科技要闻 {index}",
                "summary": f"科技要闻 {index} 摘要。",
                "alert_state": "rising",
                "entity_names": [f"公司{index}"],
                "entity_ids": [],
                "tags": ["科技"],
                "brief_id": None,
                "ignored": False,
                "source_count": 2,
                "worth_to_brief": True,
                "composite_score": 100 - index,
            }
        )
        state["event_deep_dives"].append(
            {
                "id": f"dd-{index}",
                "event_id": event_id,
                "status": "ready",
                "success_count": 1,
                "sources": [
                    {
                        "source_name": "Example",
                        "canonical_link": f"https://example.com/news-{index}",
                        "original_link": f"https://example.com/news-{index}",
                        "title": f"科技要闻 {index}",
                        "cleaned_full_text": f"科技要闻 {index} 摘要。",
                        "quotes": [],
                    }
                ],
                "facts": [f"科技要闻 {index} 摘要"],
                "quotes": [],
                "timeline": [],
                "worthiness": {"reason": "适合纳入今日科技要闻。"},
                "updated_at": "2026-05-06T00:00:00+08:00",
            }
        )
    store._write(state)
    calls: list[tuple[str, str | None]] = []

    def fake_open_douyin_article_publish():
        calls.append(("open", None))
        return types.SimpleNamespace(last_error=None)

    def fake_fill_douyin_article(payload):
        calls.append(("fill", payload.brief_id))
        assert payload.brief_id
        return store.get_brief(str(payload.brief_id))

    def fake_get_douyin_browser_session():
        calls.append(("check", None))
        return types.SimpleNamespace(last_error=None)

    monkeypatch.setattr(store, "open_douyin_article_publish", fake_open_douyin_article_publish)
    monkeypatch.setattr(store, "fill_douyin_article", fake_fill_douyin_article)
    monkeypatch.setattr(store, "get_douyin_browser_session", fake_get_douyin_browser_session)

    payload = AgentArticlePayload(
        event_id="evt-1",
        title="Agent Article",
        article_markdown="# Agent Article\n\nbody",
        publish_to_wechat_draft=False,
        publish_to_douyin_article=True,
        triggered_by="agent",
        driver_label="codex",
    )

    result = store.create_agent_article(payload)
    saved_state = store._upgrade_state(store._read())
    article_records = [
        item
        for item in saved_state.get("briefs", [])
        if isinstance(item, dict) and str(item.get("brief_level") or "") == "article"
    ]

    assert result.title == "Agent Article"
    assert article_records
    assert article_records[0]["title"] == "Agent Article"
    digest_records = [
        item
        for item in saved_state.get("briefs", [])
        if isinstance(item, dict) and str(item.get("title") or "").startswith("今日5条科技要闻")
    ]
    assert digest_records
    assert calls[1][1] == digest_records[0]["id"]
    digest_markdown = str(digest_records[0].get("douyin_markdown") or "")
    assert "朋友们，今天咱们来盘一盘" in digest_markdown
    assert "首先是" in digest_markdown
    assert "最后一条" in digest_markdown
    assert "评论区" in digest_markdown
    assert "事件已进入深挖池" not in digest_markdown
    assert calls[0][0] == "open"
    assert calls[1][0] == "fill"
    assert calls[2][0] == "check"
    shutil.rmtree(temp_root, ignore_errors=True)


def test_douyin_daily_news_pipeline_starts_from_source_sync_and_fills_digest(monkeypatch: pytest.MonkeyPatch) -> None:
    store, state, temp_root = _make_store_and_state()
    state["intel_events"] = []
    state["event_deep_dives"] = []
    for index in range(1, 6):
        event_id = f"evt-douyin-pipeline-{index}"
        state["intel_events"].append(
            {
                "id": event_id,
                "title": f"科技要闻 {index}",
                "summary": f"科技要闻 {index} 摘要。",
                "alert_state": "new",
                "entity_names": [f"公司{index}"],
                "entity_ids": [],
                "tags": ["科技"],
                "brief_id": None,
                "ignored": False,
                "source_count": 2,
                "worth_to_brief": True,
                "composite_score": 100 - index,
            }
        )
        state["event_deep_dives"].append(
            {
                "id": f"dd-douyin-pipeline-{index}",
                "event_id": event_id,
                "status": "ready",
                "success_count": 1,
                "sources": [
                    {
                        "source_name": "Example",
                        "canonical_link": f"https://example.com/pipeline-{index}",
                        "original_link": f"https://example.com/pipeline-{index}",
                        "title": f"科技要闻 {index}",
                        "cleaned_full_text": f"科技要闻 {index} 摘要。",
                        "quotes": [],
                    }
                ],
                "facts": [f"科技要闻 {index} 摘要"],
                "quotes": [],
                "timeline": [],
                "worthiness": {"reason": "适合纳入今日科技要闻。"},
                "updated_at": "2026-05-06T00:00:00+08:00",
            }
        )
    store._write(state)
    calls: list[tuple[str, str | None]] = []

    def fake_sync_sources(*, triggered_by: str = "dashboard"):
        calls.append(("sync", triggered_by))
        return types.SimpleNamespace(raw_count=5, normalized_count=5, event_count=5, synced_at="2026-05-06T00:00:00+08:00", warnings=[])

    def fake_deep_dive(event_id: str, **kwargs):
        calls.append(("deep_dive", event_id))
        return store.get_event_deep_dive(event_id)

    def fake_open_douyin_article_publish():
        calls.append(("open", None))
        return types.SimpleNamespace(last_error=None)

    def fake_fill_douyin_article(payload):
        calls.append(("fill", payload.brief_id))
        assert payload.brief_id
        return store.get_brief(str(payload.brief_id))

    def fake_get_douyin_browser_session():
        calls.append(("check", None))
        return types.SimpleNamespace(last_error=None)

    monkeypatch.setattr(store, "sync_sources", fake_sync_sources)
    monkeypatch.setattr(store, "create_event_deep_dive", fake_deep_dive)
    monkeypatch.setattr(store, "open_douyin_article_publish", fake_open_douyin_article_publish)
    monkeypatch.setattr(store, "fill_douyin_article", fake_fill_douyin_article)
    monkeypatch.setattr(store, "get_douyin_browser_session", fake_get_douyin_browser_session)

    result = store.run_douyin_daily_news_pipeline(triggered_by="douyin")
    saved_state = store._upgrade_state(store._read())
    article_records = [
        item
        for item in saved_state.get("briefs", [])
        if isinstance(item, dict) and str(item.get("brief_level") or "") == "article"
    ]

    assert result.title.startswith("今日5条科技要闻")
    assert "朋友们，今天咱们来盘一盘" in result.douyin_markdown
    assert "首先是科技要闻 1" in result.douyin_markdown
    assert "最后一条，科技要闻 5" in result.douyin_markdown
    assert "评论区" in result.douyin_markdown
    assert article_records == []
    assert calls[0] == ("sync", "douyin")
    assert [call[0] for call in calls].count("deep_dive") == 5
    assert calls[-3][0] == "open"
    assert calls[-2][0] == "fill"
    assert calls[-1][0] == "check"
    shutil.rmtree(temp_root, ignore_errors=True)


def test_agent_cannot_upload_rule_brief_via_traditional_draft_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    store, state, temp_root = _make_store_and_state()
    state["briefs"] = [
        {
            "id": "brief-rule-1",
            "event_id": "evt-1",
            "deep_dive_id": "dd-1",
            "brief_level": "rule",
            "stage": "prepared",
            "title": "Rule Brief",
            "one_line": "summary",
            "why_it_matters": "reason",
            "facts": [],
            "quotes": [],
            "timeline": [],
            "entity_names": [],
            "source_links": [],
            "risk_notes": [],
            "prompt_package_markdown": "pkg",
            "wechat_markdown": "# short brief",
            "wechat_html": "<h1>short brief</h1>",
            "updated_at": "2026-05-06T00:00:00+08:00",
        }
    ]

    monkeypatch.setattr(store, "_read", lambda: deepcopy(state))
    monkeypatch.setattr(store, "_write", lambda payload: None)

    with pytest.raises(ValueError, match="Agent 模式禁止上传传统简报"):
        store.sync_brief_wechat_draft("brief-rule-1", triggered_by="agent")
    shutil.rmtree(temp_root, ignore_errors=True)


def test_agent_wechat_short_digest_upload_requires_five_items() -> None:
    store, state, temp_root = _make_store_and_state()
    state["event_deep_dives"][0]["sources"] = [
        {
            "source_name": "Example",
            "canonical_link": "https://example.com/one-news",
            "original_link": "https://example.com/one-news",
            "title": "Test Event",
            "cleaned_full_text": "Test Event 摘要。",
            "quotes": [],
        }
    ]
    state["event_deep_dives"][0]["facts"] = ["Test Event 摘要"]
    store._write(state)

    payload = AgentArticlePayload(
        event_id="evt-1",
        title="今日科技速递｜单条测试",
        article_markdown=(
            "# 今日科技速递｜单条测试\n\n"
            "一句话：这其实只有一个信息点。\n\n"
            "## 核心事实\n\n"
            "Test Event 摘要。\n\n"
            "## 这意味着什么\n\n"
            "这不是五条信息合集。"
        ),
        publish_to_wechat_draft=True,
        publish_to_douyin_article=False,
        triggered_by="agent",
        driver_label="codex-short-brief",
    )

    with pytest.raises(ValueError, match="微信短讯必须由 5 条信息组成"):
        store.create_agent_article(payload)
    shutil.rmtree(temp_root, ignore_errors=True)
