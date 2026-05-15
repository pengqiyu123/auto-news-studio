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

from backend.app.store import StudioStore
from backend.app.store_mixins import BrowserMixin
import backend.app.store_mixins.browser_mixin as browser_mixin_module


def _make_store() -> tuple[StudioStore, Path]:
    temp_root = Path(tempfile.mkdtemp(prefix="browser-mixin-"))
    store = StudioStore(data_file=temp_root / "data" / "state.json")
    return store, temp_root


def test_studio_store_browser_methods_are_bound_from_mixin() -> None:
    store, temp_root = _make_store()
    try:
        assert StudioStore.get_douyin_config is BrowserMixin.get_douyin_config
        assert StudioStore.get_douyin_browser_session is BrowserMixin.get_douyin_browser_session
        assert StudioStore.update_douyin_browser_session is BrowserMixin.update_douyin_browser_session
        assert StudioStore.open_douyin_browser_dashboard is BrowserMixin.open_douyin_browser_dashboard
        assert StudioStore.check_douyin_browser_session is BrowserMixin.check_douyin_browser_session
        assert StudioStore.open_douyin_article_publish is BrowserMixin.open_douyin_article_publish
        assert StudioStore.inspect_douyin_article_structure is BrowserMixin.inspect_douyin_article_structure
        assert StudioStore.fill_douyin_article is BrowserMixin.fill_douyin_article
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_fill_douyin_article_prefers_douyin_copy(monkeypatch) -> None:
    store, temp_root = _make_store()
    try:
        state = store._upgrade_state(store._read())
        state["briefs"] = [
            {
                "id": "brief-1",
                "event_id": "evt-1",
                "deep_dive_id": "dd-1",
                "brief_level": "article",
                "stage": "prepared",
                "title": "公众号长标题：这是一个很长的分析版标题",
                "summary": "公众号摘要",
                "one_line": "一句话",
                "why_it_matters": "为什么重要",
                "facts": [],
                "quotes": [],
                "timeline": [],
                "entity_names": [],
                "source_links": [],
                "risk_notes": [],
                "prompt_package_markdown": "pkg",
                "douyin_prompt_package_markdown": "douyin-pkg",
                "wechat_markdown": "# 公众号长标题：这是一个很长的分析版标题\n\n这是一段公众号正文。",
                "wechat_html": "<section></section>",
                "douyin_title": "抖音短标题",
                "douyin_summary": "抖音短摘要",
                "douyin_markdown": "# 抖音短标题\n\n这是一段抖音正文。",
                "updated_at": "2026-05-15T00:00:00+08:00",
            }
        ]
        store._write(state)

        captured: dict[str, object] = {}

        def fake_fill(channel, browser_state, payload):
            captured.update(payload)
            return browser_state, [], ["ok"]

        monkeypatch.setattr(browser_mixin_module, "fill_douyin_article_from_brief", fake_fill)

        result = store.fill_douyin_article(browser_mixin_module.DouyinArticleFillPayload(brief_id="brief-1"))

        assert result.id == "brief-1"
        assert captured["title"] == "抖音短标题"
        assert captured["summary"] == "抖音短摘要"
        assert captured["markdown"] == "# 抖音短标题\n\n这是一段抖音正文。"
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_fill_douyin_article_regenerates_low_quality_summary(monkeypatch) -> None:
    store, temp_root = _make_store()
    try:
        state = store._upgrade_state(store._read())
        state["briefs"] = [
            {
                "id": "brief-1",
                "event_id": "evt-1",
                "deep_dive_id": "dd-1",
                "brief_level": "article",
                "stage": "prepared",
                "title": "国行Switch今晚22点关服：不是主机报废，而是数字能力正式收尾",
                "summary": "今晚22点，国行 Nintendo Switch 的网络相关运营服务正式停止。真正被关掉的不是主机本身，而是数字购买、兑换和下载能力。",
                "one_line": "2026年5月15日22时，国行 Nintendo Switch 网络相关运营服务正式停止。",
                "why_it_matters": "机器还能玩，但数字内容窗口会关闭。",
                "facts": [],
                "quotes": [],
                "timeline": [],
                "entity_names": [],
                "source_links": [],
                "risk_notes": [],
                "prompt_package_markdown": "pkg",
                "douyin_prompt_package_markdown": "douyin-pkg",
                "wechat_markdown": "# 国行Switch今晚22点关服\n\n这是一段公众号正文。",
                "wechat_html": "<section></section>",
                "douyin_title": "国行Switch今晚22点关服",
                "douyin_summary": "国行 Nintendo Switch 的网络相关运营服务正式",
                "douyin_markdown": "# 国行Switch今晚22点关服\n\n这是一段抖音正文。",
                "updated_at": "2026-05-15T00:00:00+08:00",
            }
        ]
        store._write(state)

        captured: dict[str, object] = {}

        def fake_fill(channel, browser_state, payload):
            captured.update(payload)
            return browser_state, [], ["ok"]

        monkeypatch.setattr(browser_mixin_module, "fill_douyin_article_from_brief", fake_fill)

        result = store.fill_douyin_article(browser_mixin_module.DouyinArticleFillPayload(brief_id="brief-1"))

        assert result.id == "brief-1"
        assert captured["summary"] == "国行Switch的网络服务停止"
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)
