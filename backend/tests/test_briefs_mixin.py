from __future__ import annotations
from pathlib import Path
import shutil
import sys
import tempfile
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
from backend.app.store import get_studio_store_class
from backend.app.store_mixins import BriefsMixin
from backend.app import store_mixins as store_mixins_pkg

StudioStore = get_studio_store_class()


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
        assert StudioStore.publish_brief_wechat_article is BriefsMixin.publish_brief_wechat_article
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


def test_abandon_agent_workflow_marks_session_finished() -> None:
    store, temp_root = _make_store()
    try:
        state = store._upgrade_state(store._read())
        state["agent_workflows"] = [
            {
                "workflow_session_id": "agentwf-abandon-1",
                "status": "running",
                "current_step": "article_saved",
                "event_id": "evt-1",
                "material_brief_id": "brief-material-1",
                "article_brief_id": "brief-article-1",
                "target_platforms": ["wechat"],
                "last_error": None,
                "started_at": "2026-05-13T10:00:00+08:00",
                "updated_at": "2026-05-13T10:01:00+08:00",
                "finished_at": None,
            }
        ]
        store._write(state)

        workflow = store.abandon_agent_workflow("agentwf-abandon-1", triggered_by="dashboard")

        assert workflow.workflow_session_id == "agentwf-abandon-1"
        assert workflow.status == "abandoned"
        assert workflow.finished_at is not None
        assert workflow.last_error == "用户已放弃该 Agent 会话"

        refreshed = store._upgrade_state(store._read())
        assert refreshed["agent_workflows"][0]["status"] == "abandoned"
        assert any("已放弃 Agent 会话" in str(item.get("message") or "") for item in refreshed["logs"])
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
        assert article.douyin_title == "英伟达财报：数据中心收入再创新高"
        assert article.douyin_summary
        assert article.douyin_markdown.startswith("# 英伟达财报：数据中心收入再创新高")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_create_agent_article_normalizes_powershell_literal_newlines() -> None:
    store, temp_root = _make_store()
    try:
        state = store._upgrade_state(store._read())
        state["intel_events"] = [
            {
                "id": "evt-psnl-1",
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
                "id": "dd-psnl-1",
                "event_id": "evt-psnl-1",
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
                event_id="evt-psnl-1",
                title="测试标题",
                article_markdown="# 测试标题`n`n第一段。`n`n## 小标题`n`n第二段。",
                summary="显式摘要优先",
                one_line="一句话结论",
                facts=["事实 1"],
                publish_to_wechat_draft=False,
                publish_to_douyin_article=False,
                triggered_by="agent",
            )
        )

        assert "`n" not in article.wechat_markdown
        assert "<code>n</code>" not in article.wechat_html
        assert "<h2>小标题</h2>" in article.wechat_html
        assert "<p>第一段。</p>" in article.wechat_html
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
                "sources": [
                    {
                        "source_key": "example",
                        "source_name": "Example",
                        "original_link": "https://example.com/openai-funding",
                        "canonical_link": "https://example.com/openai-funding",
                        "title": "OpenAI funding",
                        "fetch_status": "fetched",
                        "extract_status": "extracted",
                        "word_count": 100,
                        "cleaned_full_text": "Thrive Capital 领投，微软继续跟投。",
                        "excerpt": "Thrive Capital 领投",
                        "quotes": [],
                    }
                ],
                "facts": [
                    "Thrive Capital 领投，微软继续跟投",
                    "这笔融资被多家媒体称为 AI 领域重要融资事件",
                    "融资细节仍以官方披露为准",
                    "第四条事实不应进入短讯核心事实段",
                ],
                "quotes": ["OpenAI 表示资金将用于继续扩展 AI 基础设施"],
                "timeline": ["2026-05-13：融资消息披露"],
                "worthiness": {"reason": "值得跟踪 AI 融资格局变化"},
                "updated_at": "2026-05-13T10:00:00+08:00",
            }
        ]
        store._write(state)

        brief = store.create_brief_from_event("evt-brief-1", triggered_by="agent")

        assert brief.summary == "Thrive Capital 领投，微软继续跟投"
        assert brief.brief_level == "rule"
        assert "## 核心事实" in brief.wechat_markdown
        assert "## 这意味着什么" in brief.wechat_markdown
        assert "## 还不确定什么" in brief.wechat_markdown
        assert "## 来源链接" in brief.wechat_markdown
        assert "Thrive Capital 领投，微软继续跟投" in brief.wechat_markdown
        assert "这笔融资被多家媒体称为 AI 领域重要融资事件" in brief.wechat_markdown
        assert "融资细节仍以官方披露为准" in brief.wechat_markdown
        assert "第四条事实不应进入短讯核心事实段" not in brief.wechat_markdown
        assert "值得跟踪 AI 融资格局变化" in brief.wechat_markdown
        assert "https://example.com/openai-funding" in brief.wechat_markdown
        assert "## 写作要求" in brief.prompt_package_markdown
        assert "### 摘要" in brief.prompt_package_markdown
        assert "Thrive Capital 领投，微软继续跟投" in brief.prompt_package_markdown
        assert brief.douyin_markdown
        assert "Thrive Capital 领投，微软继续跟投" in brief.douyin_markdown
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_create_brief_from_event_short_brief_exposes_partial_and_missing_facts() -> None:
    store, temp_root = _make_store()
    try:
        state = store._upgrade_state(store._read())
        state["intel_events"] = [
            {
                "id": "evt-partial-1",
                "title": "某 AI 产品更新",
                "summary": "事件原始摘要",
                "alert_state": "rising",
                "entity_names": [],
                "entity_ids": [],
                "brief_id": None,
                "watchlisted": True,
                "ignored": False,
                "source_count": 1,
            }
        ]
        state["event_deep_dives"] = [
            {
                "id": "dd-partial-1",
                "event_id": "evt-partial-1",
                "status": "partial",
                "sources": [
                    {
                        "source_key": "example",
                        "source_name": "Example",
                        "original_link": "https://example.com/ai-update",
                        "canonical_link": "https://example.com/ai-update",
                        "title": "AI update",
                        "fetch_status": "fetch_failed",
                        "extract_status": "extract_failed",
                        "word_count": 0,
                        "cleaned_full_text": "",
                        "excerpt": "",
                        "quotes": [],
                    }
                ],
                "facts": [],
                "quotes": [],
                "timeline": [],
                "worthiness": {},
                "updated_at": "2026-05-13T10:00:00+08:00",
            }
        ]
        store._write(state)

        brief = store.create_brief_from_event("evt-partial-1", triggered_by="dashboard")

        assert brief.brief_level == "rule"
        assert "暂无足够正文事实，请继续核验。" in brief.wechat_markdown
        assert "仅完成部分正文核验，部分来源抓取或提取失败。" in brief.wechat_markdown
        assert "当前事实仍偏少，建议继续人工核验来源。" in brief.wechat_markdown
        assert "## 还不确定什么" in brief.wechat_markdown
        assert "https://example.com/ai-update" in brief.wechat_markdown
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_create_daily_digest_brief_from_events_generates_one_roundup_and_marks_members() -> None:
    store, temp_root = _make_store()
    try:
        state = store._upgrade_state(store._read())
        state["intel_events"] = [
            {
                "id": "evt-digest-1",
                "title": "华为发布 AI DC 全栈方案",
                "summary": "华为发布 AI DC 数据基础设施全栈方案。",
                "alert_state": "breakout",
                "entity_names": ["华为"],
                "entity_ids": [],
                "tags": ["AI 基础设施", "数据中心"],
                "brief_id": None,
                "watchlisted": False,
                "ignored": False,
                "source_count": 2,
            },
            {
                "id": "evt-digest-2",
                "title": "OpenAI 推出新企业功能",
                "summary": "OpenAI 面向企业用户更新管理能力。",
                "alert_state": "rising",
                "entity_names": ["OpenAI"],
                "entity_ids": [],
                "tags": ["企业 AI", "产品能力"],
                "brief_id": None,
                "watchlisted": False,
                "ignored": False,
                "source_count": 2,
            },
            {
                "id": "evt-digest-3",
                "title": "国产芯片工具链更新",
                "summary": "国产芯片工具链发布新版本。",
                "alert_state": "rising",
                "entity_names": ["芯片工具链"],
                "entity_ids": [],
                "tags": ["芯片", "工具链"],
                "brief_id": None,
                "watchlisted": False,
                "ignored": False,
                "source_count": 1,
            },
            {
                "id": "evt-digest-4",
                "title": "三星 PCIe Gen6 固态硬盘上线官网",
                "summary": "三星首款 PCIe Gen6 固态硬盘 PM1743 上线官网。",
                "alert_state": "new",
                "entity_names": ["三星"],
                "entity_ids": [],
                "tags": ["存储", "硬件"],
                "brief_id": None,
                "watchlisted": False,
                "ignored": False,
                "source_count": 2,
            },
            {
                "id": "evt-digest-5",
                "title": "雷鸟发布 V4 AI 拍摄眼镜",
                "summary": "雷鸟发布 V4 AI 拍摄眼镜，强调随身拍摄能力。",
                "alert_state": "new",
                "entity_names": ["雷鸟"],
                "entity_ids": [],
                "tags": ["AI 硬件", "智能眼镜"],
                "brief_id": None,
                "watchlisted": False,
                "ignored": False,
                "source_count": 2,
            },
        ]
        state["event_deep_dives"] = [
            {
                "id": "dd-digest-1",
                "event_id": "evt-digest-1",
                "status": "ready",
                "sources": [
                    {
                        "source_name": "量子位",
                        "canonical_link": "https://example.com/huawei-ai-dc",
                        "original_link": "https://example.com/huawei-ai-dc",
                        "title": "华为 AI DC",
                        "cleaned_full_text": "华为发布 AI DC 数据基础设施全栈方案。",
                        "quotes": [],
                    }
                ],
                "facts": ["华为发布 AI DC 数据基础设施全栈方案", "方案覆盖数据中心训练和推理场景"],
                "quotes": [],
                "timeline": ["2026-05-26：方案发布"],
                "worthiness": {"reason": "数据中心基础设施是 AI 落地的重要环节。"},
                "updated_at": "2026-05-26T10:00:00+08:00",
            },
            {
                "id": "dd-digest-2",
                "event_id": "evt-digest-2",
                "status": "ready",
                "sources": [
                    {
                        "source_name": "TechCrunch",
                        "canonical_link": "https://example.com/openai-enterprise",
                        "original_link": "https://example.com/openai-enterprise",
                        "title": "OpenAI enterprise",
                        "cleaned_full_text": "OpenAI 面向企业用户更新管理能力。",
                        "quotes": [],
                    }
                ],
                "facts": ["OpenAI 面向企业用户更新管理能力", "新功能强调权限和团队管理"],
                "quotes": [],
                "timeline": ["2026-05-26：功能更新"],
                "worthiness": {"reason": "企业 AI 管理能力正在成为产品竞争点。"},
                "updated_at": "2026-05-26T10:05:00+08:00",
            },
            {
                "id": "dd-digest-3",
                "event_id": "evt-digest-3",
                "status": "partial",
                "sources": [
                    {
                        "source_name": "IT之家",
                        "canonical_link": "https://example.com/chip-toolchain",
                        "original_link": "https://example.com/chip-toolchain",
                        "title": "国产芯片工具链",
                        "cleaned_full_text": "",
                        "quotes": [],
                    }
                ],
                "facts": ["国产芯片工具链发布新版本"],
                "quotes": [],
                "timeline": ["2026-05-26：版本更新"],
                "worthiness": {},
                "updated_at": "2026-05-26T10:10:00+08:00",
            },
            {
                "id": "dd-digest-4",
                "event_id": "evt-digest-4",
                "status": "ready",
                "sources": [
                    {
                        "source_name": "IT之家",
                        "canonical_link": "https://example.com/samsung-pcie-gen6",
                        "original_link": "https://example.com/samsung-pcie-gen6",
                        "title": "三星 PCIe Gen6 固态硬盘",
                        "cleaned_full_text": "三星首款 PCIe Gen6 固态硬盘 PM1743 上线官网。",
                        "quotes": [],
                    }
                ],
                "facts": ["三星首款 PCIe Gen6 固态硬盘 PM1743 上线官网"],
                "quotes": [],
                "timeline": ["2026-05-26：官网信息更新"],
                "worthiness": {"reason": "PCIe Gen6 存储进入产品化披露阶段。"},
                "updated_at": "2026-05-26T10:15:00+08:00",
            },
            {
                "id": "dd-digest-5",
                "event_id": "evt-digest-5",
                "status": "ready",
                "sources": [
                    {
                        "source_name": "Example",
                        "canonical_link": "https://example.com/rayneo-v4",
                        "original_link": "https://example.com/rayneo-v4",
                        "title": "雷鸟 V4 AI 拍摄眼镜",
                        "cleaned_full_text": "雷鸟发布 V4 AI 拍摄眼镜，强调随身拍摄能力。",
                        "quotes": [],
                    }
                ],
                "facts": ["雷鸟发布 V4 AI 拍摄眼镜，强调随身拍摄能力"],
                "quotes": [],
                "timeline": ["2026-05-26：新品发布"],
                "worthiness": {"reason": "AI 眼镜继续进入消费硬件场景。"},
                "updated_at": "2026-05-26T10:20:00+08:00",
            },
        ]
        store._write(state)

        brief = store.create_daily_digest_brief_from_events(
            ["evt-digest-1", "evt-digest-2", "evt-digest-3", "evt-digest-4", "evt-digest-5"],
            triggered_by="scheduler",
        )

        assert brief.brief_level == "rule"
        assert brief.event_id == "evt-digest-1"
        assert brief.deep_dive_id == "dd-digest-1"
        assert brief.title.startswith("今日科技速递")
        assert "今日筛选出 5 条值得关注的科技动态" in brief.why_it_matters
        assert "华为、OpenAI、芯片工具链" in brief.why_it_matters
        assert "AI 基础设施" in brief.why_it_matters
        assert "1 条处于爆发状态" in brief.why_it_matters
        assert "这些事件分别覆盖 AI 基础设施、产品能力或产业链变化" not in brief.why_it_matters
        assert "# 今日科技速递" in brief.wechat_markdown
        assert "今天值得关注的科技动态有 3 条" not in brief.wechat_markdown
        assert brief.wechat_markdown.splitlines()[2] == brief.why_it_matters
        assert "## 1. 华为发布 AI DC 全栈方案" in brief.wechat_markdown
        assert "## 2. OpenAI 推出新企业功能" in brief.wechat_markdown
        assert "## 3. 国产芯片工具链更新" in brief.wechat_markdown
        assert "## 4. 三星 PCIe Gen6 固态硬盘上线官网" in brief.wechat_markdown
        assert "## 5. 雷鸟发布 V4 AI 拍摄眼镜" in brief.wechat_markdown
        assert "https://example.com/huawei-ai-dc" in brief.wechat_markdown
        assert "https://example.com/openai-enterprise" in brief.wechat_markdown
        assert "https://example.com/chip-toolchain" in brief.wechat_markdown
        assert "https://example.com/samsung-pcie-gen6" in brief.wechat_markdown
        assert "https://example.com/rayneo-v4" in brief.wechat_markdown
        assert brief.douyin_markdown
        assert brief.douyin_title.startswith("今日5条科技要闻")
        assert "朋友们，今天咱们来盘一盘" in brief.douyin_markdown
        assert "首先是华为发布 AI DC 全栈方案" in brief.douyin_markdown
        assert "第二条，OpenAI 推出新企业功能" in brief.douyin_markdown
        assert "第三条，国产芯片工具链更新" in brief.douyin_markdown
        assert "第四条，三星 PCIe Gen6 固态硬盘上线官网" in brief.douyin_markdown
        assert "最后一条，雷鸟发布 V4 AI 拍摄眼镜" in brief.douyin_markdown
        assert "评论区" in brief.douyin_markdown

        refreshed = store._upgrade_state(store._read())
        assert len(refreshed["briefs"]) == 1
        member_brief_ids = {item["id"]: item.get("brief_id") for item in refreshed["intel_events"]}
        assert member_brief_ids == {
            "evt-digest-1": brief.id,
            "evt-digest-2": brief.id,
            "evt-digest-3": brief.id,
            "evt-digest-4": brief.id,
            "evt-digest-5": brief.id,
        }
        assert all(item.get("brief_status") == "prepared" for item in refreshed["intel_events"])
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_create_douyin_daily_news_digest_requires_five_short_news_items() -> None:
    store, temp_root = _make_store()
    try:
        state = store._upgrade_state(store._read())
        state["intel_events"] = []
        state["event_deep_dives"] = []
        titles = [
            "华为发布 AI DC 全栈方案",
            "OpenAI 推出新企业功能",
            "国产芯片工具链更新",
            "三星首款 PCIe Gen6 固态硬盘 PM1743 上线官网：28.4GB/s 顺序读",
            "房地产垂类大模型发布",
        ]
        for index, title in enumerate(titles, start=1):
            event_id = f"evt-douyin-digest-{index}"
            state["intel_events"].append(
                {
                    "id": event_id,
                    "title": title,
                    "summary": f"{title}。",
                    "alert_state": "new",
                    "entity_names": [title.split()[0]],
                    "entity_ids": [],
                    "tags": ["科技要闻"],
                    "brief_id": None,
                    "watchlisted": False,
                    "ignored": False,
                    "source_count": 1,
                    "composite_score": 100 - index,
                    "audience_fit_score": 80,
                    "velocity_score": 70,
                    "coverage_score": 70,
                    "freshness_score": 70,
                }
            )
            state["event_deep_dives"].append(
                {
                    "id": f"dd-douyin-digest-{index}",
                    "event_id": event_id,
                    "status": "ready",
                    "success_count": 1,
                    "sources": [
                        {
                            "source_name": "Example",
                            "canonical_link": f"https://example.com/douyin-digest-{index}",
                            "original_link": f"https://example.com/douyin-digest-{index}",
                            "title": title,
                    "cleaned_full_text": f"{title} 已经披露关键进展，后续还要观察落地节奏。",
                            "quotes": [],
                        }
                    ],
                    "facts": (
                        [
                            "事件覆盖 1 个平台、1 个来源，成员数 4",
                            "IT之家提到：三星半导体现已在官网列出其首款 PCIe Gen6 固态硬盘 PM1763",
                            "IT之家提到：三星半导体现已在官网列出其首款 PCIe Gen6 固态硬盘 PM1743",
                        ]
                        if index == 4
                        else [
                            f"事件覆盖 1 个平台、1 个来源，成员数 {index}",
                            f"驱动之家提到：{title} 的已核验事实",
                        ]
                    ),
                    "quotes": [],
                    "timeline": [],
                    "worthiness": {"reason": "事件已进入深挖池，且更贴近公众号大众科技受众，可继续生成简报。"},
                    "updated_at": "2026-05-26T10:00:00+08:00",
                }
            )
        store._write(state)

        brief = store.create_douyin_daily_news_digest(triggered_by="douyin")

        assert brief.title.startswith("今日5条科技要闻")
        assert brief.douyin_title.startswith("今日5条科技要闻")
        assert "朋友们，今天咱们来盘一盘" in brief.douyin_markdown
        assert "首先是华为发布 AI DC 全栈方案" in brief.douyin_markdown
        assert "第二条，OpenAI 推出新企业功能" in brief.douyin_markdown
        assert "第三条，国产芯片工具链更新" in brief.douyin_markdown
        assert "第四条，三星首款 PCIe Gen6 固态硬盘 PM1743 上线官网：28.4GB/s 顺序读" in brief.douyin_markdown
        assert "顺！序读" not in brief.douyin_markdown
        assert "PM1763" not in brief.douyin_markdown
        assert "消耗量增，" not in brief.douyin_markdown
        assert "最后一条，房地产垂类大模型发布" in brief.douyin_markdown
        assert "评论区" in brief.douyin_markdown
        assert "1 个平台同时出现" not in brief.douyin_markdown
        assert "事件覆盖" not in brief.douyin_markdown
        assert "成员数" not in brief.douyin_markdown
        assert "驱动之家提到" not in brief.douyin_markdown
        assert "事件已进入深挖池" not in brief.douyin_markdown
        assert "来源仍偏少" not in brief.douyin_markdown
        assert "还不确定：来源仍偏少" not in brief.douyin_markdown
        assert "\n\n\n" not in brief.douyin_markdown
        assert brief.workflow_mode == "traditional"
        assert brief.brief_level == "rule"

        refreshed = store._upgrade_state(store._read())
        included_events = [item for item in refreshed["intel_events"] if item.get("brief_id") == brief.id]
        assert len(included_events) == 5
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_create_douyin_daily_news_digest_rejects_fewer_than_five_items() -> None:
    store, temp_root = _make_store()
    try:
        state = store._upgrade_state(store._read())
        state["intel_events"] = []
        state["event_deep_dives"] = []
        for index in range(1, 4):
            event_id = f"evt-douyin-short-{index}"
            state["intel_events"].append(
                {
                    "id": event_id,
                    "title": f"科技要闻 {index}",
                    "summary": f"科技要闻 {index}。",
                    "alert_state": "new",
                    "entity_names": [],
                    "entity_ids": [],
                    "tags": ["科技"],
                    "brief_id": None,
                    "watchlisted": False,
                    "ignored": False,
                    "source_count": 1,
                    "composite_score": 90 - index,
                }
            )
            state["event_deep_dives"].append(
                {
                    "id": f"dd-douyin-short-{index}",
                    "event_id": event_id,
                    "status": "ready",
                    "success_count": 1,
                    "sources": [
                        {
                            "source_name": "Example",
                            "canonical_link": f"https://example.com/douyin-short-{index}",
                            "original_link": f"https://example.com/douyin-short-{index}",
                            "title": f"科技要闻 {index}",
                            "cleaned_full_text": f"科技要闻 {index}。",
                            "quotes": [],
                        }
                    ],
                    "facts": [f"科技要闻 {index} 的已核验事实"],
                    "quotes": [],
                    "timeline": [],
                    "worthiness": {"reason": "适合纳入今日科技要闻。"},
                    "updated_at": "2026-05-26T10:00:00+08:00",
                }
            )
        store._write(state)

        with pytest.raises(ValueError, match="至少需要 5 条"):
            store.create_douyin_daily_news_digest(triggered_by="douyin")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_create_daily_digest_brief_reuses_today_digest_when_member_events_overlap() -> None:
    store, temp_root = _make_store()
    try:
        state = store._upgrade_state(store._read())
        specs = [
            ("evt-digest-overlap-1", "华为发布 AI DC 全栈方案", "breakout", ["华为"], ["AI 基础设施"]),
            ("evt-digest-overlap-2", "OpenAI 推出新企业功能", "rising", ["OpenAI"], ["企业 AI"]),
            ("evt-digest-overlap-3", "国产芯片工具链更新", "rising", ["芯片工具链"], ["芯片"]),
            ("evt-digest-overlap-4", "机器人公司发布新产品", "rising", ["机器人公司"], ["机器人"]),
            ("evt-digest-overlap-5", "三星 PCIe Gen6 固态硬盘上线官网", "new", ["三星"], ["存储"]),
            ("evt-digest-overlap-6", "雷鸟发布 V4 AI 拍摄眼镜", "new", ["雷鸟"], ["AI 硬件"]),
        ]
        state["intel_events"] = []
        state["event_deep_dives"] = []
        for event_id, title, alert_state, entities, tags in specs:
            state["intel_events"].append(
                {
                    "id": event_id,
                    "title": title,
                    "summary": f"{title}。",
                    "alert_state": alert_state,
                    "entity_names": entities,
                    "entity_ids": [],
                    "tags": tags,
                    "brief_id": None,
                    "watchlisted": False,
                    "ignored": False,
                    "source_count": 2,
                }
            )
            state["event_deep_dives"].append(
                {
                    "id": f"dd-{event_id}",
                    "event_id": event_id,
                    "status": "ready",
                    "sources": [
                        {
                            "source_name": "Example",
                            "canonical_link": f"https://example.com/{event_id}",
                            "original_link": f"https://example.com/{event_id}",
                            "title": title,
                            "cleaned_full_text": f"{title}。",
                            "quotes": [],
                        }
                    ],
                    "facts": [f"{title} 的已核验事实"],
                    "quotes": [],
                    "timeline": [],
                    "worthiness": {"reason": "该事件值得纳入今日速递。"},
                    "updated_at": "2026-05-26T10:00:00+08:00",
                }
            )
        store._write(state)

        first = store.create_daily_digest_brief_from_events(
            [
                "evt-digest-overlap-1",
                "evt-digest-overlap-2",
                "evt-digest-overlap-3",
                "evt-digest-overlap-4",
                "evt-digest-overlap-5",
            ],
            triggered_by="dashboard",
        )
        second = store.create_daily_digest_brief_from_events(
            [
                "evt-digest-overlap-2",
                "evt-digest-overlap-3",
                "evt-digest-overlap-4",
                "evt-digest-overlap-5",
                "evt-digest-overlap-6",
            ],
            triggered_by="dashboard",
        )

        assert second.id == first.id
        assert second.wechat_markdown != first.wechat_markdown

        refreshed = store._upgrade_state(store._read())
        assert len(refreshed["briefs"]) == 1
        events_by_id = {item["id"]: item for item in refreshed["intel_events"]}
        assert events_by_id["evt-digest-overlap-1"].get("brief_id") is None
        assert events_by_id["evt-digest-overlap-2"].get("brief_id") == first.id
        assert events_by_id["evt-digest-overlap-3"].get("brief_id") == first.id
        assert events_by_id["evt-digest-overlap-4"].get("brief_id") == first.id
        assert events_by_id["evt-digest-overlap-5"].get("brief_id") == first.id
        assert events_by_id["evt-digest-overlap-6"].get("brief_id") == first.id
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_create_daily_digest_brief_requires_five_qualified_events() -> None:
    store, temp_root = _make_store()
    try:
        state = store._upgrade_state(store._read())
        state["intel_events"] = [
            {
                "id": "evt-digest-single",
                "title": "唯一可写事件",
                "summary": "只有一条可写事件。",
                "alert_state": "breakout",
                "entity_names": [],
                "entity_ids": [],
                "brief_id": None,
                "watchlisted": False,
                "ignored": False,
                "source_count": 1,
            },
            {
                "id": "evt-digest-no-source",
                "title": "缺少来源事件",
                "summary": "这条缺少来源链接。",
                "alert_state": "rising",
                "entity_names": [],
                "entity_ids": [],
                "brief_id": None,
                "watchlisted": False,
                "ignored": False,
                "source_count": 0,
            },
        ]
        state["event_deep_dives"] = [
            {
                "id": "dd-digest-single",
                "event_id": "evt-digest-single",
                "status": "ready",
                "sources": [
                    {
                        "source_name": "Example",
                        "canonical_link": "https://example.com/only-one",
                        "original_link": "https://example.com/only-one",
                        "title": "only one",
                        "cleaned_full_text": "只有一条可写事件。",
                        "quotes": [],
                    }
                ],
                "facts": ["只有一条可写事件"],
                "quotes": [],
                "timeline": [],
                "worthiness": {},
                "updated_at": "2026-05-26T10:00:00+08:00",
            },
            {
                "id": "dd-digest-no-source",
                "event_id": "evt-digest-no-source",
                "status": "ready",
                "sources": [],
                "facts": ["缺少来源链接"],
                "quotes": [],
                "timeline": [],
                "worthiness": {},
                "updated_at": "2026-05-26T10:05:00+08:00",
            },
        ]
        store._write(state)

        try:
            store.create_daily_digest_brief_from_events(
                ["evt-digest-single", "evt-digest-no-source"],
                triggered_by="scheduler",
            )
        except ValueError as exc:
            assert "必须由 5 条合格事件组成" in str(exc)
        else:
            raise AssertionError("Expected daily digest generation to require five qualified events.")

        refreshed = store._upgrade_state(store._read())
        assert refreshed["briefs"] == []
        assert all(not item.get("brief_id") for item in refreshed["intel_events"])
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_get_daily_digest_brief_projects_included_events() -> None:
    store, temp_root = _make_store()
    try:
        state = store._upgrade_state(store._read())
        specs = [
            ("evt-included-1", "华为发布 AI DC 全栈方案", "华为发布 AI DC 数据基础设施全栈方案。", "breakout", ["华为"], 3, "https://example.com/huawei-ai-dc"),
            ("evt-included-2", "OpenAI 推出新企业功能", "OpenAI 面向企业用户更新管理能力。", "rising", ["OpenAI"], 2, "https://example.com/openai-enterprise"),
            ("evt-included-3", "国产芯片工具链更新", "国产芯片工具链发布新版本。", "rising", ["芯片工具链"], 2, "https://example.com/chip-toolchain"),
            ("evt-included-4", "三星 PCIe Gen6 固态硬盘上线官网", "三星首款 PCIe Gen6 固态硬盘 PM1743 上线官网。", "new", ["三星"], 2, "https://example.com/samsung-pcie-gen6"),
            ("evt-included-5", "雷鸟发布 V4 AI 拍摄眼镜", "雷鸟发布 V4 AI 拍摄眼镜。", "new", ["雷鸟"], 2, "https://example.com/rayneo-v4"),
        ]
        state["intel_events"] = []
        state["event_deep_dives"] = []
        for index, (event_id, title, summary, alert_state, entities, source_count, link) in enumerate(specs, start=1):
            state["intel_events"].append(
                {
                    "id": event_id,
                    "title": title,
                    "summary": summary,
                    "representative_link": link,
                    "alert_state": alert_state,
                    "entity_names": entities,
                    "entity_ids": [],
                    "brief_id": None,
                    "deep_dive_id": f"dd-included-{index}",
                    "deep_dive_status": "ready",
                    "watchlisted": False,
                    "ignored": False,
                    "source_count": source_count,
                }
            )
            state["event_deep_dives"].append(
                {
                    "id": f"dd-included-{index}",
                    "event_id": event_id,
                    "status": "ready",
                    "sources": [
                        {
                            "source_name": "Example",
                            "canonical_link": link,
                            "original_link": link,
                            "title": title,
                        }
                    ],
                    "facts": [summary.rstrip("。")],
                    "quotes": [],
                    "timeline": [],
                    "worthiness": {"reason": "该事件值得纳入今日速递。"},
                    "updated_at": f"2026-05-26T10:0{index}:00+08:00",
                }
            )
        store._write(state)

        brief = store.create_daily_digest_brief_from_events(
            [item[0] for item in specs],
            triggered_by="scheduler",
        )
        detail = store.get_brief(brief.id)

        assert [item.event_id for item in detail.included_events] == [item[0] for item in specs]
        assert detail.included_events[0].title == "华为发布 AI DC 全栈方案"
        assert detail.included_events[0].alert_state == "breakout"
        assert detail.included_events[0].source_count == 3
        assert detail.included_events[0].deep_dive_status == "ready"
        assert detail.included_events[0].representative_link == "https://example.com/huawei-ai-dc"

        refreshed = store._upgrade_state(store._read())
        assert "included_events" not in refreshed["briefs"][0]
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


def test_create_daily_digest_brief_marks_only_qualified_members() -> None:
    store, temp_root = _make_store()
    try:
        state = store._upgrade_state(store._read())
        state["intel_events"] = [
            {
                "id": "evt-digest-no-source-first",
                "title": "缺少来源事件",
                "summary": "这条缺少来源链接。",
                "alert_state": "breakout",
                "entity_names": [],
                "entity_ids": [],
                "brief_id": None,
                "watchlisted": False,
                "ignored": False,
                "source_count": 0,
            },
            {
                "id": "evt-digest-good-1",
                "title": "AI 云服务降价",
                "summary": "AI 云服务下调部分推理价格。",
                "alert_state": "breakout",
                "entity_names": ["云服务"],
                "entity_ids": [],
                "brief_id": None,
                "watchlisted": False,
                "ignored": False,
                "source_count": 2,
            },
            {
                "id": "evt-digest-good-2",
                "title": "机器人公司发布新产品",
                "summary": "机器人公司发布面向仓储场景的新产品。",
                "alert_state": "rising",
                "entity_names": ["机器人"],
                "entity_ids": [],
                "brief_id": None,
                "watchlisted": False,
                "ignored": False,
                "source_count": 2,
            },
            {
                "id": "evt-digest-good-3",
                "title": "国产芯片工具链更新",
                "summary": "国产芯片工具链发布新版本。",
                "alert_state": "rising",
                "entity_names": ["芯片工具链"],
                "entity_ids": [],
                "brief_id": None,
                "watchlisted": False,
                "ignored": False,
                "source_count": 2,
            },
            {
                "id": "evt-digest-good-4",
                "title": "三星 PCIe Gen6 固态硬盘上线官网",
                "summary": "三星首款 PCIe Gen6 固态硬盘 PM1743 上线官网。",
                "alert_state": "new",
                "entity_names": ["三星"],
                "entity_ids": [],
                "brief_id": None,
                "watchlisted": False,
                "ignored": False,
                "source_count": 2,
            },
            {
                "id": "evt-digest-good-5",
                "title": "雷鸟发布 V4 AI 拍摄眼镜",
                "summary": "雷鸟发布 V4 AI 拍摄眼镜。",
                "alert_state": "new",
                "entity_names": ["雷鸟"],
                "entity_ids": [],
                "brief_id": None,
                "watchlisted": False,
                "ignored": False,
                "source_count": 2,
            },
        ]
        state["event_deep_dives"] = [
            {
                "id": "dd-digest-no-source-first",
                "event_id": "evt-digest-no-source-first",
                "status": "ready",
                "sources": [],
                "facts": ["缺少来源链接"],
                "quotes": [],
                "timeline": [],
                "worthiness": {},
                "updated_at": "2026-05-26T10:00:00+08:00",
            },
            {
                "id": "dd-digest-good-1",
                "event_id": "evt-digest-good-1",
                "status": "ready",
                "sources": [
                    {
                        "source_name": "Example",
                        "canonical_link": "https://example.com/ai-cloud-price",
                        "original_link": "https://example.com/ai-cloud-price",
                        "title": "AI cloud price",
                        "cleaned_full_text": "AI 云服务下调部分推理价格。",
                        "quotes": [],
                    }
                ],
                "facts": ["AI 云服务下调部分推理价格"],
                "quotes": [],
                "timeline": [],
                "worthiness": {"reason": "推理价格会影响应用成本。"},
                "updated_at": "2026-05-26T10:05:00+08:00",
            },
            {
                "id": "dd-digest-good-2",
                "event_id": "evt-digest-good-2",
                "status": "ready",
                "sources": [
                    {
                        "source_name": "Example",
                        "canonical_link": "https://example.com/robot-product",
                        "original_link": "https://example.com/robot-product",
                        "title": "Robot product",
                        "cleaned_full_text": "机器人公司发布面向仓储场景的新产品。",
                        "quotes": [],
                    }
                ],
                "facts": ["机器人公司发布面向仓储场景的新产品"],
                "quotes": [],
                "timeline": [],
                "worthiness": {"reason": "仓储机器人仍是工业自动化热点。"},
                "updated_at": "2026-05-26T10:10:00+08:00",
            },
            {
                "id": "dd-digest-good-3",
                "event_id": "evt-digest-good-3",
                "status": "ready",
                "sources": [
                    {
                        "source_name": "Example",
                        "canonical_link": "https://example.com/chip-toolchain",
                        "original_link": "https://example.com/chip-toolchain",
                        "title": "国产芯片工具链",
                        "cleaned_full_text": "国产芯片工具链发布新版本。",
                        "quotes": [],
                    }
                ],
                "facts": ["国产芯片工具链发布新版本"],
                "quotes": [],
                "timeline": [],
                "worthiness": {"reason": "芯片工具链影响国产生态建设。"},
                "updated_at": "2026-05-26T10:15:00+08:00",
            },
            {
                "id": "dd-digest-good-4",
                "event_id": "evt-digest-good-4",
                "status": "ready",
                "sources": [
                    {
                        "source_name": "Example",
                        "canonical_link": "https://example.com/samsung-pcie-gen6",
                        "original_link": "https://example.com/samsung-pcie-gen6",
                        "title": "三星 PCIe Gen6 固态硬盘",
                        "cleaned_full_text": "三星首款 PCIe Gen6 固态硬盘 PM1743 上线官网。",
                        "quotes": [],
                    }
                ],
                "facts": ["三星首款 PCIe Gen6 固态硬盘 PM1743 上线官网"],
                "quotes": [],
                "timeline": [],
                "worthiness": {"reason": "PCIe Gen6 存储进入产品化披露阶段。"},
                "updated_at": "2026-05-26T10:20:00+08:00",
            },
            {
                "id": "dd-digest-good-5",
                "event_id": "evt-digest-good-5",
                "status": "ready",
                "sources": [
                    {
                        "source_name": "Example",
                        "canonical_link": "https://example.com/rayneo-v4",
                        "original_link": "https://example.com/rayneo-v4",
                        "title": "雷鸟 V4 AI 拍摄眼镜",
                        "cleaned_full_text": "雷鸟发布 V4 AI 拍摄眼镜。",
                        "quotes": [],
                    }
                ],
                "facts": ["雷鸟发布 V4 AI 拍摄眼镜"],
                "quotes": [],
                "timeline": [],
                "worthiness": {"reason": "AI 眼镜继续进入消费硬件场景。"},
                "updated_at": "2026-05-26T10:25:00+08:00",
            },
        ]
        store._write(state)

        brief = store.create_daily_digest_brief_from_events(
            [
                "evt-digest-no-source-first",
                "evt-digest-good-1",
                "evt-digest-good-2",
                "evt-digest-good-3",
                "evt-digest-good-4",
                "evt-digest-good-5",
            ],
            triggered_by="scheduler",
        )

        assert brief.event_id == "evt-digest-good-1"
        assert brief.deep_dive_id == "dd-digest-good-1"
        assert "缺少来源事件" not in brief.wechat_markdown
        assert "AI 云服务降价" in brief.wechat_markdown
        assert "机器人公司发布新产品" in brief.wechat_markdown
        assert "雷鸟发布 V4 AI 拍摄眼镜" in brief.wechat_markdown

        refreshed = store._upgrade_state(store._read())
        by_id = {item["id"]: item for item in refreshed["intel_events"]}
        assert by_id["evt-digest-no-source-first"].get("brief_id") is None
        assert by_id["evt-digest-good-1"].get("brief_id") == brief.id
        assert by_id["evt-digest-good-2"].get("brief_id") == brief.id
        assert by_id["evt-digest-good-3"].get("brief_id") == brief.id
        assert by_id["evt-digest-good-4"].get("brief_id") == brief.id
        assert by_id["evt-digest-good-5"].get("brief_id") == brief.id
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


def test_sync_brief_wechat_draft_normalizes_legacy_powershell_literal_newlines_before_upload(monkeypatch) -> None:
    store, temp_root = _make_store()
    try:
        state = store._upgrade_state(store._read())
        state["briefs"] = [
            {
                "id": "brief-legacy-1",
                "event_id": "evt-legacy-1",
                "deep_dive_id": "dd-legacy-1",
                "brief_level": "article",
                "stage": "prepared",
                "title": "旧稿标题",
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
                "wechat_markdown": "# 旧稿标题`n`n第一段。`n`n## 小标题`n`n第二段。",
                "wechat_html": "<section><p>旧缓存</p></section>",
                "needs_resync": False,
                "delivery_status": "idle",
                "updated_at": "2026-05-14T10:00:00+08:00",
            }
        ]
        state["intel_events"] = [
            {
                "id": "evt-legacy-1",
                "title": "旧稿标题",
                "summary": "事件摘要",
                "alert_state": "watch",
                "entity_names": [],
                "entity_ids": [],
                "brief_id": "brief-legacy-1",
                "watchlisted": True,
                "ignored": False,
            }
        ]
        state["channels"]["wechat"]["selectors_version"] = "wechat-mp-v1"
        captured: dict[str, object] = {}
        store._write(state)

        def _fake_run_browser_action(action, browser_payload, channel, browser):
            captured["action"] = action
            captured["markdown"] = browser_payload.get("markdown")
            next_browser = {
                **browser,
                "logged_in": True,
                "last_error": None,
                "verification_status": "verified",
                "verification_message": "ok",
                "last_synced_editor_url": "https://mp.weixin.qq.com/cgi-bin/appmsg?t=media/appmsg_edit&appmsgid=100000999",
            }
            return next_browser, [], ["ok"]

        monkeypatch.setattr(store_mixins_pkg.briefs_mixin, "run_browser_action", _fake_run_browser_action)

        result = store.sync_brief_wechat_draft("brief-legacy-1", triggered_by="dashboard")

        assert captured["action"] == "sync_wechat_draft"
        assert captured["markdown"] == "# 旧稿标题\n\n第一段。\n\n## 小标题\n\n第二段。"
        assert result.wechat_markdown == "# 旧稿标题\n\n第一段。\n\n## 小标题\n\n第二段。"
        assert "<code>n</code>" not in result.wechat_html
        assert "<h2>小标题</h2>" in result.wechat_html
        assert result.stage == "synced"
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_publish_brief_wechat_article_stops_at_qrcode_without_marking_published(monkeypatch) -> None:
    store, temp_root = _make_store()
    try:
        state = store._upgrade_state(store._read())
        state["briefs"] = [
            {
                "id": "brief-publish-1",
                "event_id": "evt-publish-1",
                "deep_dive_id": "dd-publish-1",
                "brief_level": "article",
                "stage": "synced",
                "title": "发布测试标题",
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
                "wechat_markdown": "# 发布测试标题\n\n这是一篇准备真实发表的文章正文。",
                "wechat_html": "<section><p>旧缓存</p></section>",
                "needs_resync": False,
                "delivery_status": "verified",
                "record_status": "draft_synced",
                "updated_at": "2026-05-14T10:00:00+08:00",
            }
        ]
        state["intel_events"] = [
            {
                "id": "evt-publish-1",
                "title": "发布测试标题",
                "summary": "事件摘要",
                "alert_state": "watch",
                "entity_names": [],
                "entity_ids": [],
                "brief_id": "brief-publish-1",
                "watchlisted": True,
                "ignored": False,
            }
        ]
        state["channels"]["wechat"]["selectors_version"] = "wechat-mp-v1"
        captured: dict[str, object] = {}
        store._write(state)

        def _fake_run_browser_action(action, browser_payload, channel, browser):
            captured["action"] = action
            captured["markdown"] = browser_payload.get("markdown")
            next_browser = {
                **browser,
                "logged_in": True,
                "last_error": None,
                "verification_status": "wechat_qrcode_required",
                "verification_message": "已到微信验证二维码，请扫码确认。",
                "last_screenshot": "runtime/publish_artifacts/brief-publish-1/qrcode.png",
            }
            return next_browser, ["runtime/publish_artifacts/brief-publish-1/qrcode.png"], ["二维码已出现"]

        monkeypatch.setattr(store_mixins_pkg.briefs_mixin, "run_browser_action", _fake_run_browser_action)

        result = store.publish_brief_wechat_article("brief-publish-1", triggered_by="dashboard")

        assert captured["action"] == "publish_wechat_article"
        assert captured["markdown"] == "# 发布测试标题\n\n这是一篇准备真实发表的文章正文。"
        assert result.stage == "synced"
        assert result.record_status == "draft_synced"
        assert result.record_exception == "pending_confirmation"
        assert result.delivery_status == "pending_confirmation"
        assert result.last_error == "已到微信验证二维码，请扫码确认。"
        refreshed = store._upgrade_state(store._read())
        task = refreshed["publish_tasks"][0]
        assert task["action"] == "publish_wechat_article"
        assert task["status"] == "blocked"
        assert task["artifacts"] == ["runtime/publish_artifacts/brief-publish-1/qrcode.png"]
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
