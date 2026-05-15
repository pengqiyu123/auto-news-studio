from __future__ import annotations

from pathlib import Path
import shutil
import sys
import tempfile
import types

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
from backend.app.store_mixins import BriefsMixin
from backend.app import store_mixins as store_mixins_pkg


def _make_store() -> tuple[StudioStore, Path]:
    temp_root = Path(tempfile.mkdtemp(prefix="briefs-mixin-"))
    store = StudioStore(data_file=temp_root / "data" / "state.json")
    return store, temp_root


def test_studio_store_brief_methods_are_bound_from_mixin() -> None:
    store, temp_root = _make_store()
    try:
        assert StudioStore.create_brief_from_event is BriefsMixin.create_brief_from_event
        assert StudioStore.create_agent_article is BriefsMixin.create_agent_article
        assert StudioStore.list_briefs is BriefsMixin.list_briefs
        assert StudioStore.sync_brief_wechat_draft is BriefsMixin.sync_brief_wechat_draft
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_list_briefs_projects_record_status_after_split() -> None:
    store, temp_root = _make_store()
    try:
        state = store._upgrade_state(store._read())
        state["briefs"] = [
            {
                "id": "brief-article-1",
                "event_id": "evt-1",
                "deep_dive_id": "dd-1",
                "brief_level": "article",
                "stage": "synced",
                "title": "示例 AI 长文",
                "one_line": "一句话结论",
                "why_it_matters": "值得关注",
                "facts": ["事实 1"],
                "quotes": [],
                "timeline": [],
                "entity_names": [],
                "source_links": ["https://example.com/1"],
                "risk_notes": [],
                "prompt_package_markdown": "pkg",
                "wechat_markdown": "# 示例 AI 长文",
                "wechat_html": "<h1>示例 AI 长文</h1>",
                "wechat_editor_url": "https://mp.weixin.qq.com/s/example",
                "wechat_remote_appmsg_id": "appmsg-1",
                "updated_at": "2026-05-12T10:00:00+08:00",
                "delivery_status": "verified",
            }
        ]
        state["browser"]["wechat"]["last_draft_check"] = {
            "checked_at": "2026-05-12T10:05:00+08:00",
            "remote_count": 1,
            "matched_count": 1,
            "missing_count": 0,
            "message": "ok",
            "check_ok": True,
            "items": [
                {
                    "title": "示例 AI 长文",
                    "url": "https://mp.weixin.qq.com/s/example",
                    "appmsg_id": "appmsg-1",
                    "updated_at": "2026-05-12T10:04:00+08:00",
                    "remote_key": "appmsg:appmsg-1",
                }
            ],
        }
        store._write(state)

        items, total, page, page_size, has_more, stage_counts, record_counts = store.list_briefs(
            page=1,
            page_size=20,
            stage="draft_synced",
        )

        assert total == 1
        assert page == 1
        assert page_size == 20
        assert has_more is False
        assert stage_counts.all == 1
        assert record_counts.all == 1
        assert record_counts.draft_synced == 1
        assert items[0].id == "brief-article-1"
        assert items[0].record_status == "draft_synced"
        assert items[0].draft_remote_updated_at == "2026-05-12T10:04:00+08:00"
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_agent_brief_and_article_share_workflow_session() -> None:
    store, temp_root = _make_store()
    try:
        state = store._upgrade_state(store._read())
        state["intel_events"] = [
            {
                "id": "evt-1",
                "title": "Agent Event",
                "summary": "summary",
                "alert_state": "watch",
                "entity_names": [],
                "entity_ids": [],
                "brief_id": None,
                "watchlisted": True,
                "ignored": False,
            }
        ]
        state["event_deep_dives"] = [
            {
                "id": "dd-1",
                "event_id": "evt-1",
                "status": "ready",
                "sources": [],
                "facts": ["fact"],
                "quotes": [],
                "timeline": [],
                "worthiness": {"reason": "worth watching"},
                "updated_at": "2026-05-13T10:00:00+08:00",
            }
        ]
        store._write(state)

        material = store.create_brief_from_event("evt-1", triggered_by="agent")
        article = store.create_agent_article(
            AgentArticlePayload(
                event_id="evt-1",
                title="Agent Article",
                article_markdown="# Agent Article\n\nbody",
                publish_to_wechat_draft=False,
                publish_to_douyin_article=False,
                triggered_by="agent",
            )
        )
        workflows = store.list_agent_workflows()

        assert material.workflow_mode == "agent"
        assert article.workflow_mode == "agent"
        assert material.workflow_session_id
        assert material.workflow_session_id == article.workflow_session_id
        assert workflows
        assert workflows[0].workflow_session_id == material.workflow_session_id
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_create_agent_article_optimizes_title_and_rewrites_markdown_heading() -> None:
    store, temp_root = _make_store()
    try:
        state = store._upgrade_state(store._read())
        state["intel_events"] = [
            {
                "id": "evt-title-1",
                "title": "AI Event",
                "summary": "summary",
                "alert_state": "watch",
                "entity_names": [],
                "entity_ids": [],
                "brief_id": None,
                "watchlisted": True,
                "ignored": False,
            }
        ]
        state["event_deep_dives"] = [
            {
                "id": "dd-title-1",
                "event_id": "evt-title-1",
                "status": "ready",
                "sources": [],
                "facts": ["数据中心收入再创新高"],
                "quotes": [],
                "timeline": [],
                "worthiness": {"reason": "worth watching"},
                "updated_at": "2026-05-13T10:00:00+08:00",
            }
        ]
        store._write(state)

        article = store.create_agent_article(
            AgentArticlePayload(
                event_id="evt-title-1",
                title="英伟达财报",
                article_markdown="# 英伟达财报\n\n数据中心收入再创新高，市场预期继续上修。",
                one_line="数据中心收入再创新高，市场预期继续上修。",
                facts=["数据中心收入再创新高", "毛利率维持高位"],
                publish_to_wechat_draft=False,
                publish_to_douyin_article=False,
                triggered_by="agent",
            )
        )

        assert article.title == "英伟达财报：数据中心收入再创新高"
        assert article.summary == "数据中心收入再创新高，市场预期继续上修"
        assert article.wechat_markdown.startswith("# 英伟达财报：数据中心收入再创新高")
        assert article.douyin_title == "英伟达财报"
        assert article.douyin_summary
        assert article.douyin_markdown.startswith("# 英伟达财报")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_create_brief_from_event_generates_summary_and_writing_guide_prompt() -> None:
    store, temp_root = _make_store()
    try:
        state = store._upgrade_state(store._read())
        state["intel_events"] = [
            {
                "id": "evt-brief-1",
                "title": "OpenAI 新融资",
                "summary": "事件原始摘要",
                "alert_state": "watch",
                "entity_names": [],
                "entity_ids": [],
                "brief_id": None,
                "watchlisted": True,
                "ignored": False,
            }
        ]
        state["event_deep_dives"] = [
            {
                "id": "dd-brief-1",
                "event_id": "evt-brief-1",
                "status": "ready",
                "sources": [],
                "facts": ["Thrive Capital 领投，微软继续跟投"],
                "quotes": [],
                "timeline": [],
                "worthiness": {"reason": "值得跟踪 AI 融资格局变化"},
                "updated_at": "2026-05-13T10:00:00+08:00",
            }
        ]
        store._write(state)

        brief = store.create_brief_from_event("evt-brief-1", triggered_by="agent")

        assert brief.summary == "Thrive Capital 领投，微软继续跟投"
        assert "## 写作要求" in brief.prompt_package_markdown
        assert "### 摘要" in brief.prompt_package_markdown
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_create_agent_article_prefers_explicit_summary_payload() -> None:
    store, temp_root = _make_store()
    try:
        state = store._upgrade_state(store._read())
        state["intel_events"] = [
            {
                "id": "evt-summary-1",
                "title": "AI Event",
                "summary": "事件默认摘要",
                "alert_state": "watch",
                "entity_names": [],
                "entity_ids": [],
                "brief_id": None,
                "watchlisted": True,
                "ignored": False,
            }
        ]
        state["event_deep_dives"] = [
            {
                "id": "dd-summary-1",
                "event_id": "evt-summary-1",
                "status": "ready",
                "sources": [],
                "facts": ["事实 1"],
                "quotes": [],
                "timeline": [],
                "worthiness": {"reason": "worth watching"},
                "updated_at": "2026-05-13T10:00:00+08:00",
            }
        ]
        store._write(state)

        article = store.create_agent_article(
            AgentArticlePayload(
                event_id="evt-summary-1",
                title="测试标题",
                article_markdown="# 测试标题\n\n正文",
                summary="显式摘要优先",
                one_line="一句话结论",
                facts=["事实 1"],
                publish_to_wechat_draft=False,
                publish_to_douyin_article=False,
                triggered_by="agent",
            )
        )

        assert article.summary == "显式摘要优先"
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_sync_brief_wechat_draft_refreshes_cached_wechat_html_before_revision_check() -> None:
    store, temp_root = _make_store()
    try:
        state = store._upgrade_state(store._read())
        state["briefs"] = [
            {
                "id": "brief-refresh-1",
                "event_id": "evt-refresh-1",
                "deep_dive_id": "dd-refresh-1",
                "brief_level": "article",
                "stage": "synced",
                "title": "缓存刷新标题",
                "summary": "这是显式摘要",
                "one_line": "一句话",
                "why_it_matters": "原因",
                "facts": [],
                "quotes": [],
                "timeline": [],
                "entity_names": [],
                "source_links": [],
                "risk_notes": [],
                "prompt_package_markdown": "pkg",
                "wechat_markdown": "# 缓存刷新标题\n\n正文里有 **加粗**。",
                "wechat_html": "<section><p>旧缓存</p></section>",
                "needs_resync": False,
                "delivery_status": "verified",
                "updated_at": "2026-05-14T10:00:00+08:00",
            }
        ]
        state["channels"]["wechat"]["selectors_version"] = "wechat-mp-v1"
        state["browser"]["wechat"]["logged_in"] = False
        store._write(state)

        result = store.sync_brief_wechat_draft("brief-refresh-1", triggered_by="dashboard")

        assert "<strong>加粗</strong>" in result.wechat_html
        assert result.summary == "这是显式摘要"
        assert result.stage != "synced"
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_create_agent_article_persists_workflow_before_generating_deep_dive() -> None:
    store, temp_root = _make_store()
    original_fetch = store_mixins_pkg.briefs_mixin.fetch_and_extract_link
    original_event_inputs = StudioStore._event_deep_dive_inputs
    try:
        state = store._upgrade_state(store._read())
        state["intel_events"] = [
            {
                "id": "evt-2",
                "title": "Agent Event Without Deep Dive",
                "summary": "summary",
                "alert_state": "watch",
                "entity_names": ["Microsoft"],
                "entity_ids": [],
                "brief_id": None,
                "watchlisted": False,
                "ignored": False,
                "representative_link": "https://example.com/event",
                "source_names": ["Example"],
            }
        ]
        store._write(state)

        def _fake_fetch(item: dict, *, timeout_seconds: float) -> dict:
            return {
                "source_name": str(item.get("source_name") or "Example"),
                "title": str(item.get("title") or "Example Title"),
                "canonical_link": str(item.get("canonical_link") or "https://example.com/source"),
                "original_link": str(item.get("original_link") or "https://example.com/source"),
                "extract_status": "extracted",
                "cleaned_full_text": "Example full text for agent deep dive generation.",
                "quotes": ["Example quote"],
            }

        def _fake_event_inputs(self, state: dict, event: dict) -> list[dict]:
            return [
                {
                    "source_name": "Example",
                    "title": "Example Title",
                    "canonical_link": "https://example.com/source",
                    "original_link": "https://example.com/source",
                    "published_at": "2026-05-13T00:00:00+00:00",
                }
            ]

        store_mixins_pkg.briefs_mixin.fetch_and_extract_link = _fake_fetch
        StudioStore._event_deep_dive_inputs = _fake_event_inputs

        article = store.create_agent_article(
            AgentArticlePayload(
                event_id="evt-2",
                title="Agent Article With Generated Deep Dive",
                article_markdown="# Agent Article\n\nbody",
                facts=["fact 1"],
                publish_to_wechat_draft=False,
                publish_to_douyin_article=False,
                triggered_by="agent",
            )
        )
        workflows = store.list_agent_workflows()
        deep_dive = store.get_event_deep_dive("evt-2")

        assert article.workflow_mode == "agent"
        assert article.workflow_session_id
        assert deep_dive.status in {"ready", "partial"}
        assert workflows
        assert workflows[0].workflow_session_id == article.workflow_session_id
        assert workflows[0].article_brief_id == article.id
    finally:
        store_mixins_pkg.briefs_mixin.fetch_and_extract_link = original_fetch
        StudioStore._event_deep_dive_inputs = original_event_inputs
        shutil.rmtree(temp_root, ignore_errors=True)


def test_delete_brief_removes_local_record_and_event_pointer() -> None:
    store, temp_root = _make_store()
    try:
        state = store._upgrade_state(store._read())
        state["intel_events"] = [
            {
                "id": "evt-delete-1",
                "title": "Delete me",
                "summary": "summary",
                "alert_state": "watch",
                "entity_names": [],
                "entity_ids": [],
                "brief_id": "brief-delete-1",
                "watchlisted": True,
                "ignored": False,
            }
        ]
        state["briefs"] = [
            {
                "id": "brief-delete-1",
                "event_id": "evt-delete-1",
                "deep_dive_id": "dd-delete-1",
                "brief_level": "article",
                "stage": "prepared",
                "title": "Delete me",
                "summary": "summary",
                "one_line": "one line",
                "why_it_matters": "why",
                "facts": [],
                "quotes": [],
                "timeline": [],
                "entity_names": [],
                "source_links": [],
                "risk_notes": [],
                "prompt_package_markdown": "pkg",
                "wechat_markdown": "# Delete me\n\nbody",
                "wechat_html": "<h1>Delete me</h1>",
                "updated_at": "2026-05-14T10:00:00+08:00",
                "delivery_status": "idle",
            }
        ]
        store._write(state)

        result = store.delete_brief("brief-delete-1", remote="false", triggered_by="test")
        assert result.ok is True

        refreshed = store._upgrade_state(store._read())
        assert refreshed["briefs"] == []
        assert refreshed["intel_events"][0]["brief_id"] is None
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)
