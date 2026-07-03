from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import HTTPException, Request
from pydantic import BaseModel, ValidationError

from ..store import StudioStore

RUNTIME_DIR = Path(__file__).resolve().parents[3] / "runtime"
_store: StudioStore | None = None

_JSON_FALLBACK_ENCODINGS = (
    "utf-8",
    "utf-8-sig",
    "utf-16",
    "utf-16-le",
    "utf-16-be",
    "utf-32",
    "utf-32-le",
    "utf-32-be",
    "gb18030",
    "gbk",
)


def set_store(store: StudioStore) -> None:
    global _store
    _store = store


def get_store() -> StudioStore:
    global _store
    if _store is None:
        _store = StudioStore()
    return _store


def http_from_value_error(exc: ValueError) -> HTTPException:
    message = str(exc)
    if message.startswith("未找到"):
        status_code = 404
    elif message.startswith("当前自动调度器正在运行"):
        status_code = 409
    elif message.startswith("Agent 模式禁止上传传统简报"):
        status_code = 409
    else:
        status_code = 400
    return HTTPException(status_code=status_code, detail=message)


def decode_json_body(raw_body: bytes) -> Any:
    if not raw_body or not raw_body.strip():
        raise HTTPException(status_code=400, detail="请求体不能为空。")

    for encoding in _JSON_FALLBACK_ENCODINGS:
        try:
            decoded = raw_body.decode(encoding)
        except UnicodeDecodeError:
            continue
        try:
            return json.loads(decoded)
        except json.JSONDecodeError:
            continue

    raise HTTPException(
        status_code=400,
        detail="JSON 请求体解析失败。请优先使用 UTF-8 编码；在 Windows 下用 curl/PowerShell 发送中文正文时，也可改为 UTF-8 文件再上传。",
    )


async def parse_request_model(request: Request, model_type: type[BaseModel]) -> BaseModel:
    payload_data = decode_json_body(await request.body())
    try:
        return model_type.model_validate(payload_data)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc
