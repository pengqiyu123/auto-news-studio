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
from backend.app.store_mixins import WeChatMixin


def _make_store() -> tuple[StudioStore, Path]:
    temp_root = Path(tempfile.mkdtemp(prefix="wechat-mixin-"))
    store = StudioStore(data_file=temp_root / "data" / "state.json")
    return store, temp_root


def test_studio_store_wechat_methods_are_bound_from_mixin() -> None:
    store, temp_root = _make_store()
    try:
      assert StudioStore.get_wechat_mapping is WeChatMixin.get_wechat_mapping
      assert StudioStore.refresh_wechat_mapping is WeChatMixin.refresh_wechat_mapping
      assert StudioStore.check_wechat_publish_history is WeChatMixin.check_wechat_publish_history
    finally:
      shutil.rmtree(temp_root, ignore_errors=True)


def test_get_wechat_mapping_uses_same_projection_after_split() -> None:
    store, temp_root = _make_store()
    try:
        state = store._upgrade_state(store._read())
        state["briefs"] = [
            {
                "id": "brief-1",
                "title": "示例文章",
                "stage": "synced",
                "delivery_status": "verified",
                "updated_at": "2026-05-12T10:00:00+08:00",
                "wechat_editor_url": "https://mp.weixin.qq.com/s/example",
                "wechat_remote_appmsg_id": "12345",
            }
        ]
        state["browser"]["wechat"]["last_draft_check"] = {
            "checked_at": "2026-05-12T10:05:00+08:00",
            "remote_count": 1,
            "matched_count": 1,
            "missing_count": 0,
            "message": "ok",
            "items": [
                {
                    "title": "示例文章",
                    "url": "https://mp.weixin.qq.com/s/example",
                    "appmsg_id": "12345",
                    "updated_at": "2026-05-12T10:03:00+08:00",
                    "remote_key": "appmsg:12345",
                }
            ],
        }
        store._write(state)

        snapshot = store.get_wechat_mapping()

        assert snapshot.remote_count == 1
        assert snapshot.matched_count == 1
        assert len(snapshot.mapping_rows) == 1
        assert snapshot.mapping_rows[0].local_brief_id == "brief-1"
        assert snapshot.mapping_rows[0].mapping_status == "matched"
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)
