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
