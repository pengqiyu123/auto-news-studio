from __future__ import annotations

import sys
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

from backend.app.sources import discover_sources


def test_source_registry_includes_missing_maomu_cn_ai_media_sources() -> None:
    sources = discover_sources()
    by_key = {item["key"]: item for item in sources}

    assert by_key["rss-zhidx"]["name"] == "智东西"
    assert by_key["rss-zhidx"]["url"] == "https://zhidx.com/rss"

    assert by_key["rss-tmtpost"]["name"] == "钛媒体"
    assert by_key["rss-tmtpost"]["url"] == "https://www.tmtpost.com/rss.xml"

    assert by_key["rss-qbitai"]["name"] == "量子位"
    assert by_key["rss-qbitai"]["url"] == "https://www.qbitai.com/feed"
