from __future__ import annotations

import importlib
import sys
import types


def test_main_does_not_register_background_wechat_draft_poll() -> None:
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

    import backend.app.main as main_module

    main_module = importlib.reload(main_module)

    job_ids = {job.id for job in main_module.scheduler.get_jobs()}
    assert "wechat-draft-poll" not in job_ids
