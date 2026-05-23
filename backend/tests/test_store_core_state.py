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
from backend.app.store.core import StoreCore
from backend.app.store.state import StoreCoreStateMixin


def _make_store() -> tuple[StudioStore, Path]:
    temp_root = Path(tempfile.mkdtemp(prefix="store-core-state-"))
    store = StudioStore(data_file=temp_root / "data" / "state.json")
    return store, temp_root


def test_store_core_inherits_state_mixin_methods() -> None:
    store, temp_root = _make_store()
    try:
        assert issubclass(StoreCore, StoreCoreStateMixin)
        assert StoreCore._read is StoreCoreStateMixin._read
        assert StoreCore._write is StoreCoreStateMixin._write
        assert StoreCore._read_live is StoreCoreStateMixin._read_live
        assert StoreCore._upgrade_state is StoreCoreStateMixin._upgrade_state
        assert StoreCore._read_config is StoreCoreStateMixin._read_config
        assert StoreCore._write_config is StoreCoreStateMixin._write_config
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_store_core_state_mixin_preserves_bootstrap_and_read_write_flow() -> None:
    store, temp_root = _make_store()
    try:
        state = store._read_live()
        assert "sources" in state
        assert "channels" in state
        assert "browser" in state
        assert "reference_projects" in state

        state["logs"].append({
            "id": "log-test-1",
            "level": "info",
            "message": "state mixin write path",
            "created_at": "2026-05-13T10:00:00+08:00",
        })
        store._write(state)

        reloaded = store._upgrade_state(store._read())
        assert any(item.get("id") == "log-test-1" for item in reloaded.get("logs", []))

        config = store._read_config()
        assert "wechat" in config
        assert "settings" in config

        config["settings"]["tavily_api_key"] = "test-key"
        store._write_config(config)
        updated_config = store._read_config()
        assert updated_config["settings"]["tavily_api_key"] == "test-key"
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)
