"""Protocol-aware LLM runtime with first-class CC-Switch support."""

from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Callable
from typing import Any
from urllib import error as urlerror
from urllib import parse as urlparse
from urllib import request as urlrequest

from openai import (
    APIConnectionError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    InternalServerError,
    NotFoundError,
    OpenAI,
    RateLimitError,
)

logger = logging.getLogger(__name__)

PROVIDER_REGISTRY: dict[str, dict[str, Any]] = {
    "nvidia": {
        "label": "NVIDIA NIM",
        "base_url": "https://integrate.api.nvidia.com/v1",
        "models": [
            "qwen/qwen3.5-122b-a10b",
            "deepseek-ai/deepseek-v4-flash",
            "deepseek-ai/deepseek-v3.1-terminus",
            "z-ai/glm4.7",
            "minimaxai/minimax-m2.7",
            "deepseek-ai/deepseek-v4-pro",
        ],
    },
    "deepseek": {
        "label": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
        "models": ["deepseek-chat", "deepseek-reasoner"],
    },
    "openrouter": {
        "label": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1",
        "models": [
            "deepseek/deepseek-v3.2",
            "anthropic/claude-sonnet-4",
            "openai/gpt-4o",
            "google/gemini-2.5-flash",
        ],
    },
    "doubao": {
        "label": "豆包 (火山引擎)",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "models": ["doubao-seed-1-8-251228", "doubao-1-5-pro-32k-250115"],
    },
    "glm": {
        "label": "智谱 GLM",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "models": ["glm-4.7-flash", "glm-4-plus", "glm-4-flash", "glm-4-air"],
    },
    "siliconflow": {
        "label": "SiliconFlow",
        "base_url": "https://api.siliconflow.cn/v1",
        "models": [
            "THUDM/GLM-4-9B-0414",
            "deepseek-ai/DeepSeek-V3",
            "deepseek-ai/DeepSeek-R1-0528-Qwen3-8B",
            "Qwen/Qwen3-8B",
            "THUDM/GLM-Z1-9B-0414",
            "Qwen/Qwen3.5-4B",
        ],
    },
    "qwen": {
        "label": "通义千问",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "models": ["qwen-turbo", "qwen-plus", "qwen-max"],
    },
    "openai": {
        "label": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "models": ["gpt-4o", "gpt-4o-mini", "o3-mini"],
    },
}

SUPPORTED_API_FORMATS = {"openai_chat", "openai_responses", "anthropic", "gemini_native"}
KNOWN_COMPAT_SUFFIXES = (
    "/api/claudecode",
    "/api/anthropic",
    "/apps/anthropic",
    "/api/coding",
    "/claudecode",
    "/anthropic",
    "/step_plan",
    "/coding",
    "/claude",
)
KNOWN_API_TERMINALS = (
    "/v1/chat/completions",
    "/chat/completions",
    "/v1/responses",
    "/responses",
    "/v1/messages",
    "/messages",
)


class LLMRouteError(RuntimeError):
    def __init__(
        self,
        probe_status: str,
        probe_message: str,
        *,
        endpoint: str = "",
        resolved_format: str = "",
        resolved_model: str = "",
        retryable: bool = False,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(probe_message)
        self.probe_status = probe_status
        self.probe_message = probe_message
        self.endpoint = endpoint
        self.resolved_format = resolved_format
        self.resolved_model = resolved_model
        self.retryable = retryable
        self.cause = cause


def _clean_str(value: Any) -> str:
    return str(value or "").strip()


def _clean_url(value: Any) -> str:
    return _clean_str(value).rstrip("/")


def _dedupe_keep_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for raw in values:
        value = _clean_str(raw)
        if not value or value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return unique


def _looks_like_html(text: str) -> bool:
    snippet = text.lstrip().lower()
    return snippet.startswith("<!doctype html") or snippet.startswith("<html") or "<html" in snippet[:200]


def _truncate_text(text: str, max_chars: int = 160) -> str:
    value = _clean_str(text)
    if len(value) <= max_chars:
        return value
    return value[:max_chars].rstrip() + "..."


def _normalize_cc_api_format(raw: Any, app_type: str = "", provider_key: str = "") -> str:
    value = _clean_str(raw).lower()
    if value in SUPPORTED_API_FORMATS:
        return value
    app_type = _clean_str(app_type).lower()
    provider_key = _clean_str(provider_key).lower()
    if app_type == "codex":
        return "openai_responses"
    if app_type == "gemini":
        return "gemini_native"
    if app_type == "claude":
        return "anthropic"
    if provider_key in PROVIDER_REGISTRY:
        return "openai_chat"
    return "openai_chat"


def _format_probe_label(status: str) -> str:
    labels = {
        "verified": "已验证，可用于稿件生成",
        "html_homepage": "返回了网页首页，不是 API 接口",
        "auth_failed": "认证失败，请检查 API Key",
        "protocol_mismatch": "协议不匹配，请检查端点和格式",
        "model_missing": "缺少可用模型",
        "connection_failed": "连接失败，请检查端点可达性",
        "rate_limited": "请求被限流",
        "request_failed": "请求失败",
    }
    return labels.get(status, status or "请求失败")


def _strip_compat_suffix(base_url: str) -> str:
    for suffix in KNOWN_COMPAT_SUFFIXES:
        if base_url.endswith(suffix):
            return base_url[: -len(suffix)].rstrip("/")
    return base_url


def _strip_api_terminal(base_url: str) -> str:
    for suffix in KNOWN_API_TERMINALS:
        if base_url.endswith(suffix):
            return base_url[: -len(suffix)].rstrip("/")
    return base_url


def _build_openai_endpoint(base_url: str, api_format: str) -> str:
    base = _clean_url(base_url)
    if not base:
        return ""
    base_root = _strip_api_terminal(base)
    if api_format == "openai_chat":
        if base.endswith("/v1/chat/completions") or base.endswith("/chat/completions"):
            return base
        if base_root.endswith("/v1"):
            return f"{base_root}/chat/completions"
        return f"{base_root}/v1/chat/completions"
    if api_format == "openai_responses":
        if base.endswith("/v1/responses") or base.endswith("/responses"):
            return base
        if base_root.endswith("/v1"):
            return f"{base_root}/responses"
        return f"{base_root}/v1/responses"
    return ""


def _build_anthropic_endpoint(base_url: str) -> str:
    base = _clean_url(base_url)
    if not base:
        return ""
    base_root = _strip_api_terminal(base)
    if base.endswith("/v1/messages") or base.endswith("/messages"):
        return base
    if base_root.endswith("/v1"):
        return f"{base_root}/messages"
    return f"{base_root}/v1/messages"


def _build_gemini_endpoint(base_url: str, model_id: str, is_full_url: bool) -> str:
    base = _clean_url(base_url)
    if not base or not model_id:
        return ""
    if ":generateContent" in base:
        return base
    quoted_model = urlparse.quote(model_id, safe="/-_.")
    if is_full_url or "/models/" in base:
        if base.endswith(quoted_model):
            return f"{base}:generateContent"
        return f"{base}/models/{quoted_model}:generateContent"
    if base.endswith("/v1beta"):
        return f"{base}/models/{quoted_model}:generateContent"
    if base.endswith("/v1"):
        return f"{base}/models/{quoted_model}:generateContent"
    return f"{base}/v1beta/models/{quoted_model}:generateContent"


def _build_endpoint(base_url: str, api_format: str, model_id: str, is_full_url: bool) -> str:
    base = _clean_url(base_url)
    if not base:
        return ""
    if is_full_url:
        return _build_gemini_endpoint(base, model_id, True) if api_format == "gemini_native" else base
    if api_format == "openai_chat":
        return _build_openai_endpoint(base, api_format)
    if api_format == "openai_responses":
        return _build_openai_endpoint(base, api_format)
    if api_format == "anthropic":
        return _build_anthropic_endpoint(base)
    if api_format == "gemini_native":
        return _build_gemini_endpoint(base, model_id, False)
    return base


def _openai_base_url_from_endpoint(endpoint: str, api_format: str) -> str:
    value = _clean_url(endpoint)
    suffixes = {
        "openai_chat": ("/v1/chat/completions", "/chat/completions"),
        "openai_responses": ("/v1/responses", "/responses"),
    }
    for suffix in suffixes.get(api_format, ()):
        if value.endswith(suffix):
            return value[: -len(suffix)] or value
    return value


def _build_models_url_candidates(base_url: str) -> list[str]:
    root = _clean_url(base_url)
    if not root:
        return []
    candidates: list[str] = []
    if root.endswith("/v1"):
        candidates.append(f"{root}/models")
    else:
        candidates.append(f"{root}/v1/models")
    stripped = _strip_compat_suffix(root)
    if stripped and stripped != root:
        if stripped.endswith("/v1"):
            candidates.append(f"{stripped}/models")
        else:
            candidates.append(f"{stripped}/v1/models")
        candidates.append(f"{stripped}/models")
    return _dedupe_keep_order(candidates)


def _score_model_candidate(model_id: str) -> tuple[int, int, str]:
    model = _clean_str(model_id).lower()
    score = 0
    if not model:
        return (-999, 0, "")
    if "claude-sonnet-4-6" in model:
        score += 180
    elif "claude-sonnet-4" in model:
        score += 170
    elif "claude-opus-4-6" in model:
        score += 168
    elif "claude-opus-4" in model:
        score += 160
    elif "claude-3-7-sonnet" in model:
        score += 150
    elif "claude-3-5-sonnet" in model:
        score += 145
    elif "claude-3-5-haiku" in model:
        score += 130
    elif "claude-3" in model:
        score += 110
    elif "gpt-5" in model:
        score += 170
    elif "gpt-4.1" in model or "gpt-4o" in model:
        score += 145
    elif "gemini-2.5" in model:
        score += 145
    elif "gemini" in model:
        score += 115
    elif "glm-5" in model or "glm-4.5" in model:
        score += 130
    elif "glm-4.7" in model:
        score += 125
    elif "deepseek" in model:
        score += 120

    if "claude-2" in model or "claude-instant" in model:
        score -= 120
    if "deprecated" in model or "legacy" in model:
        score -= 80

    numbers = [int(item) for item in re.findall(r"\d+", model)]
    freshness = numbers[0] if numbers else 0
    return (score, freshness, model_id)


def _resolve_openai_model_candidates(provider: dict[str, Any], route: dict[str, Any], timeout: float, service: LLMService) -> list[str]:
    explicit = _clean_str(route.get("model"))
    if explicit:
        return [explicit]
    candidates = ["default"]
    discovered = service._discover_openai_models(provider, route, timeout)
    if discovered:
        candidates.append(discovered[0])
    return _dedupe_keep_order(candidates)


def _http_json_request(
    method: str,
    url: str,
    *,
    headers: dict[str, str],
    payload: dict[str, Any] | None = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    body = None
    request_headers = dict(headers)
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json")
    req = urlrequest.Request(url, data=body, headers=request_headers, method=method.upper())
    try:
        with urlrequest.urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            if _looks_like_html(raw):
                raise LLMRouteError("html_homepage", "返回了网页首页，不是 API 接口", endpoint=url)
            try:
                data = json.loads(raw) if raw else {}
            except json.JSONDecodeError as exc:
                raise LLMRouteError(
                    "protocol_mismatch",
                    f"响应不是有效 JSON：{_truncate_text(raw)}",
                    endpoint=url,
                    cause=exc,
                ) from exc
            return data
    except urlerror.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        if _looks_like_html(raw):
            raise LLMRouteError("html_homepage", "返回了网页首页，不是 API 接口", endpoint=url, cause=exc) from exc
        status = getattr(exc, "code", 0)
        if status in {401, 403}:
            raise LLMRouteError("auth_failed", f"认证失败（HTTP {status}）", endpoint=url, cause=exc) from exc
        if status in {404, 405}:
            raise LLMRouteError("protocol_mismatch", f"端点或协议不匹配（HTTP {status}）", endpoint=url, cause=exc) from exc
        if status in {400, 422}:
            message = _truncate_text(raw)
            if "model" in message.lower():
                raise LLMRouteError("model_missing", message, endpoint=url, cause=exc) from exc
            raise LLMRouteError("request_failed", message or f"请求失败（HTTP {status}）", endpoint=url, cause=exc) from exc
        if status == 429:
            raise LLMRouteError("rate_limited", "请求被限流", endpoint=url, retryable=True, cause=exc) from exc
        raise LLMRouteError(
            "connection_failed",
            f"请求失败（HTTP {status}）：{_truncate_text(raw)}",
            endpoint=url,
            retryable=status >= 500,
            cause=exc,
        ) from exc
    except urlerror.URLError as exc:
        raise LLMRouteError("connection_failed", f"连接失败：{exc.reason}", endpoint=url, retryable=True, cause=exc) from exc
    except TimeoutError as exc:
        raise LLMRouteError("connection_failed", "请求超时", endpoint=url, retryable=True, cause=exc) from exc


def _extract_openai_chat_content(response: Any) -> tuple[str, int, int]:
    if isinstance(response, str):
        return response, 0, 0
    content = ""
    if hasattr(response, "choices") and response.choices:
        content = response.choices[0].message.content or ""
    usage = getattr(response, "usage", None)
    input_tokens = int(getattr(usage, "prompt_tokens", 0) or 0) if usage else 0
    output_tokens = int(getattr(usage, "completion_tokens", 0) or 0) if usage else 0
    return content, input_tokens, output_tokens


def _extract_openai_responses_content(response: Any) -> tuple[str, int, int]:
    if isinstance(response, str):
        return response, 0, 0
    content = _clean_str(getattr(response, "output_text", ""))
    if not content and hasattr(response, "output"):
        pieces: list[str] = []
        for item in getattr(response, "output", []) or []:
            for part in getattr(item, "content", []) or []:
                text = _clean_str(getattr(part, "text", ""))
                if text:
                    pieces.append(text)
        content = "\n".join(pieces).strip()
    usage = getattr(response, "usage", None)
    input_tokens = int(getattr(usage, "input_tokens", 0) or 0) if usage else 0
    output_tokens = int(getattr(usage, "output_tokens", 0) or 0) if usage else 0
    return content, input_tokens, output_tokens


def _extract_anthropic_content(payload: dict[str, Any]) -> tuple[str, int, int]:
    parts = payload.get("content", [])
    text_parts = [
        _clean_str(part.get("text"))
        for part in parts
        if isinstance(part, dict) and _clean_str(part.get("type")) in {"text", ""}
    ]
    usage = payload.get("usage", {}) if isinstance(payload.get("usage"), dict) else {}
    return (
        "\n".join([part for part in text_parts if part]).strip(),
        int(usage.get("input_tokens", 0) or 0),
        int(usage.get("output_tokens", 0) or 0),
    )


def _extract_gemini_content(payload: dict[str, Any]) -> tuple[str, int, int]:
    candidates = payload.get("candidates", [])
    parts: list[str] = []
    for candidate in candidates if isinstance(candidates, list) else []:
        content = candidate.get("content", {}) if isinstance(candidate, dict) else {}
        for part in content.get("parts", []) if isinstance(content, dict) else []:
            text = _clean_str(part.get("text")) if isinstance(part, dict) else ""
            if text:
                parts.append(text)
    usage = payload.get("usageMetadata", {}) if isinstance(payload.get("usageMetadata"), dict) else {}
    return (
        "\n".join(parts).strip(),
        int(usage.get("promptTokenCount", 0) or 0),
        int(usage.get("candidatesTokenCount", 0) or 0),
    )


def _messages_to_text(messages: list[dict[str, str]]) -> tuple[str, str]:
    system_parts: list[str] = []
    other_parts: list[str] = []
    for message in messages:
        role = _clean_str(message.get("role")) or "user"
        content = _clean_str(message.get("content"))
        if not content:
            continue
        if role == "system":
            system_parts.append(content)
        else:
            other_parts.append(f"{role}: {content}")
    return "\n\n".join(system_parts).strip(), "\n\n".join(other_parts).strip()


def _extract_openai_embedded_error(response: Any) -> str:
    success = getattr(response, "success", None)
    code = getattr(response, "code", None)
    msg = _clean_str(getattr(response, "msg", ""))
    if success is False:
        return msg or f"请求失败（code={code})"
    if code and not getattr(response, "choices", None) and not getattr(response, "output", None):
        return msg or f"请求失败（code={code})"
    error = getattr(response, "error", None)
    if isinstance(error, dict):
        return _clean_str(error.get("message") or error.get("msg") or "")
    return ""


class LLMService:
    """Manages LLM calls across multiple providers and tasks."""

    def __init__(self, llm_config: dict[str, Any] | None = None):
        self._providers: dict[str, dict[str, Any]] = {}
        self._tasks: dict[str, dict[str, Any]] = {}
        self._usage: dict[str, dict[str, int]] = {}
        if llm_config:
            self._load_config(llm_config)

    def _load_config(self, config: dict[str, Any]) -> None:
        self._providers = {p["key"]: p for p in config.get("providers", []) if p.get("enabled")}
        self._tasks = {t["task_key"]: t for t in config.get("tasks", [])}
        self._usage = config.get("usage_today", {})

    def is_available(self) -> bool:
        return bool(self._providers)

    def get_available_provider_keys(self) -> list[str]:
        return list(self._providers.keys())

    def get_models_for_provider(self, provider_key: str) -> list[str]:
        if provider_key not in self._providers:
            return []
        registry = PROVIDER_REGISTRY.get(provider_key, {})
        return registry.get("models", [])

    def _discover_openai_models(self, provider: dict[str, Any], route: dict[str, Any], timeout: float) -> list[str]:
        discovered: list[str] = []
        for url in _build_models_url_candidates(_openai_base_url_from_endpoint(route["endpoint"], route["format"])):
            try:
                payload = _http_json_request(
                    "GET",
                    url,
                    headers={"Authorization": f"Bearer {provider['api_key']}"},
                    timeout=timeout,
                )
            except LLMRouteError:
                continue
            models = payload.get("data", []) if isinstance(payload, dict) else []
            for item in models if isinstance(models, list) else []:
                model_id = _clean_str(item.get("id")) if isinstance(item, dict) else ""
                if model_id:
                    discovered.append(model_id)
            if discovered:
                break
        unique = _dedupe_keep_order(discovered)
        ranked = sorted(unique, key=_score_model_candidate, reverse=True)
        return ranked[:8]

    def _build_route_candidates(self, provider: dict[str, Any], *, prefer_verified: bool) -> list[dict[str, Any]]:
        declared_format = _normalize_cc_api_format(
            provider.get("cc_api_format"),
            app_type=_clean_str(provider.get("cc_app_type")),
            provider_key=_clean_str(provider.get("key")),
        )
        explicit_model = _clean_str(provider.get("model_id"))
        verified_endpoint = _clean_str(provider.get("cc_last_verified_endpoint"))
        verified_format = _normalize_cc_api_format(
            provider.get("cc_last_verified_format") or declared_format,
            app_type=_clean_str(provider.get("cc_app_type")),
            provider_key=_clean_str(provider.get("key")),
        )
        verified_model = _clean_str(provider.get("cc_last_verified_model"))
        is_full_url = bool(provider.get("cc_is_full_url"))
        auto_select = False
        if provider.get("source") == "cc-switch":
            auto_flag = provider.get("cc_endpoint_auto_select")
            auto_select = auto_flag is not False

        raw_candidates = _dedupe_keep_order(
            list(provider.get("cc_endpoint_candidates", []) or [])
            + [
                _clean_str(provider.get("cc_base_url_raw")),
                _clean_str(provider.get("cc_usage_base_url")),
                _clean_str(provider.get("base_url")),
            ]
        )

        routes: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()

        def add_route(endpoint: str, api_format: str, model_id: str, *, verified: bool) -> None:
            endpoint = _clean_str(endpoint)
            api_format = _normalize_cc_api_format(api_format, _clean_str(provider.get("cc_app_type")), _clean_str(provider.get("key")))
            model_id = _clean_str(model_id)
            if not endpoint:
                return
            key = (endpoint, api_format, model_id)
            if key in seen:
                return
            seen.add(key)
            routes.append({
                "endpoint": endpoint,
                "format": api_format,
                "model": model_id,
                "verified": verified,
            })

        if prefer_verified and verified_endpoint:
            add_route(verified_endpoint, verified_format, verified_model or explicit_model, verified=True)

        formats = [declared_format]
        if auto_select and declared_format != "gemini_native":
            for alt in ("openai_chat", "openai_responses", "anthropic"):
                if alt not in formats:
                    formats.append(alt)

        for base in raw_candidates:
            for api_format in formats:
                endpoint = _build_endpoint(base, api_format, verified_model or explicit_model, is_full_url)
                add_route(endpoint, api_format, verified_model or explicit_model, verified=False)

        if not routes and provider.get("base_url"):
            add_route(
                _build_endpoint(_clean_str(provider.get("base_url")), declared_format, explicit_model, False),
                declared_format,
                explicit_model,
                verified=False,
            )
        return routes

    def _invoke_openai_with_model_fallback(
        self,
        provider: dict[str, Any],
        route: dict[str, Any],
        *,
        api_format: str,
        timeout: float,
        invoke_request: Callable[[OpenAI, str], Any],
        extract_content: Callable[[Any], tuple[str, int, int]],
    ) -> dict[str, Any]:
        model_candidates = _resolve_openai_model_candidates(provider, route, timeout, self)
        model_candidates = [candidate for candidate in model_candidates if _clean_str(candidate)]
        if not model_candidates:
            raise LLMRouteError(
                "model_missing",
                "缺少模型，未能从服务端发现可用模型",
                endpoint=route["endpoint"],
                resolved_format=route["format"],
            )
        client = OpenAI(
            base_url=_openai_base_url_from_endpoint(route["endpoint"], api_format),
            api_key=provider["api_key"],
            timeout=timeout,
        )
        last_error: LLMRouteError | None = None
        for model_id in model_candidates:
            try:
                response = invoke_request(client, model_id)
            except AuthenticationError as exc:
                raise LLMRouteError("auth_failed", "认证失败，请检查 API Key", endpoint=route["endpoint"], resolved_format=route["format"], resolved_model=model_id, cause=exc) from exc
            except RateLimitError as exc:
                raise LLMRouteError("rate_limited", f"请求被限流：{exc}", endpoint=route["endpoint"], resolved_format=route["format"], resolved_model=model_id, retryable=True, cause=exc) from exc
            except InternalServerError as exc:
                err = LLMRouteError("request_failed", _clean_str(exc) or "服务端返回异常", endpoint=route["endpoint"], resolved_format=route["format"], resolved_model=model_id, retryable=True, cause=exc)
                if not route["model"] and model_id == "default":
                    last_error = err
                    continue
                raise err from exc
            except (APIConnectionError, APITimeoutError) as exc:
                raise LLMRouteError("connection_failed", f"连接失败：{exc}", endpoint=route["endpoint"], resolved_format=route["format"], resolved_model=model_id, retryable=True, cause=exc) from exc
            except NotFoundError as exc:
                last_error = LLMRouteError("model_missing", f"模型不可用：{exc}", endpoint=route["endpoint"], resolved_format=route["format"], resolved_model=model_id, cause=exc)
                continue
            except BadRequestError as exc:
                message = _clean_str(exc)
                status = "model_missing" if ("model" in message.lower() or "模型" in message) else "protocol_mismatch"
                err = LLMRouteError(status, message or _format_probe_label(status), endpoint=route["endpoint"], resolved_format=route["format"], resolved_model=model_id, cause=exc)
                if status == "model_missing" and not route["model"]:
                    last_error = err
                    continue
                raise err from exc

            embedded_error = _extract_openai_embedded_error(response)
            if embedded_error:
                status = "protocol_mismatch" if "not_found" in embedded_error.lower() or "404" in embedded_error.lower() else "request_failed"
                if ("不支持的模型" in embedded_error or "unsupported model" in embedded_error.lower()) and not route["model"]:
                    last_error = LLMRouteError("model_missing", embedded_error, endpoint=route["endpoint"], resolved_format=route["format"], resolved_model=model_id)
                    continue
                err = LLMRouteError(status, embedded_error, endpoint=route["endpoint"], resolved_format=route["format"], resolved_model=model_id)
                raise err

            content, input_tokens, output_tokens = extract_content(response)
            if _looks_like_html(content):
                raise LLMRouteError("html_homepage", "返回了网页首页，不是 API 接口", endpoint=route["endpoint"], resolved_format=route["format"], resolved_model=model_id)
            if not content:
                err = LLMRouteError("protocol_mismatch", "响应里没有有效文本内容", endpoint=route["endpoint"], resolved_format=route["format"], resolved_model=model_id)
                if not route["model"]:
                    last_error = err
                    continue
                raise err
            return {
                "content": content.strip(),
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "resolved_model": model_id,
            }

        if last_error:
            raise last_error
        raise LLMRouteError("model_missing", "缺少可用模型", endpoint=route["endpoint"], resolved_format=route["format"])

    def _invoke_openai_chat(
        self,
        provider: dict[str, Any],
        route: dict[str, Any],
        messages: list[dict[str, str]],
        *,
        temperature: float,
        max_tokens: int,
        timeout: float,
    ) -> dict[str, Any]:
        return self._invoke_openai_with_model_fallback(
            provider,
            route,
            api_format="openai_chat",
            timeout=timeout,
            invoke_request=lambda client, model_id: client.chat.completions.create(
                    model=model_id,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                ),
            extract_content=_extract_openai_chat_content,
        )

    def _invoke_openai_responses(
        self,
        provider: dict[str, Any],
        route: dict[str, Any],
        messages: list[dict[str, str]],
        *,
        temperature: float,
        max_tokens: int,
        timeout: float,
    ) -> dict[str, Any]:
        system_text, input_text = _messages_to_text(messages)
        return self._invoke_openai_with_model_fallback(
            provider,
            route,
            api_format="openai_responses",
            timeout=timeout,
            invoke_request=lambda client, model_id: client.responses.create(
                **{
                    "model": model_id,
                    "input": input_text or "user: Hi",
                    "temperature": temperature,
                    "max_output_tokens": max_tokens,
                    **({"instructions": system_text} if system_text else {}),
                }
            ),
            extract_content=_extract_openai_responses_content,
        )

    def _invoke_anthropic(
        self,
        provider: dict[str, Any],
        route: dict[str, Any],
        messages: list[dict[str, str]],
        *,
        temperature: float,
        max_tokens: int,
        timeout: float,
    ) -> dict[str, Any]:
        model_id = route["model"] or _clean_str(provider.get("model_id")) or _clean_str(provider.get("cc_last_verified_model"))
        if not model_id:
            raise LLMRouteError("model_missing", "缺少模型，请先填写模型 ID", endpoint=route["endpoint"], resolved_format=route["format"])
        system_text, _ = _messages_to_text(messages)
        payload = {
            "model": model_id,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [
                {"role": _clean_str(message.get("role")) or "user", "content": _clean_str(message.get("content"))}
                for message in messages
                if _clean_str(message.get("role")) != "system" and _clean_str(message.get("content"))
            ],
        }
        if system_text:
            payload["system"] = system_text
        data = _http_json_request(
            "POST",
            route["endpoint"],
            headers={
                "x-api-key": provider["api_key"],
                "Authorization": f"Bearer {provider['api_key']}",
                "anthropic-version": "2023-06-01",
            },
            payload=payload,
            timeout=timeout,
        )
        content, input_tokens, output_tokens = _extract_anthropic_content(data)
        if not content:
            raise LLMRouteError("protocol_mismatch", "Anthropic 响应中没有可读文本", endpoint=route["endpoint"], resolved_format=route["format"], resolved_model=model_id)
        return {
            "content": content,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "resolved_model": model_id,
        }

    def _invoke_gemini(
        self,
        provider: dict[str, Any],
        route: dict[str, Any],
        messages: list[dict[str, str]],
        *,
        temperature: float,
        max_tokens: int,
        timeout: float,
    ) -> dict[str, Any]:
        model_id = route["model"] or _clean_str(provider.get("model_id")) or _clean_str(provider.get("cc_last_verified_model"))
        if not model_id:
            raise LLMRouteError("model_missing", "缺少模型，请先填写模型 ID", endpoint=route["endpoint"], resolved_format=route["format"])
        system_text, input_text = _messages_to_text(messages)
        endpoint = route["endpoint"] or _build_gemini_endpoint(_clean_str(provider.get("base_url")), model_id, bool(provider.get("cc_is_full_url")))
        key_query = "key=" + urlparse.quote(provider["api_key"], safe="")
        final_endpoint = endpoint + ("&" if "?" in endpoint else "?") + key_query
        prompt = (system_text + "\n\n" + input_text).strip() if system_text else (input_text or "Hi")
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }
        try:
            data = _http_json_request(
                "POST",
                final_endpoint,
                headers={},
                payload=payload,
                timeout=timeout,
            )
        except LLMRouteError as exc:
            raise LLMRouteError(
                exc.probe_status,
                exc.probe_message,
                endpoint=endpoint,
                resolved_format=route["format"],
                resolved_model=model_id,
                retryable=exc.retryable,
                cause=exc,
            ) from exc
        content, input_tokens, output_tokens = _extract_gemini_content(data)
        if not content:
            raise LLMRouteError("protocol_mismatch", "Gemini 响应中没有可读文本", endpoint=endpoint, resolved_format=route["format"], resolved_model=model_id)
        return {
            "content": content,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "resolved_model": model_id,
            "resolved_endpoint": endpoint,
        }

    def _invoke_route(
        self,
        provider: dict[str, Any],
        route: dict[str, Any],
        messages: list[dict[str, str]],
        *,
        temperature: float,
        max_tokens: int,
        timeout: float,
    ) -> dict[str, Any]:
        if route["format"] == "openai_chat":
            result = self._invoke_openai_chat(provider, route, messages, temperature=temperature, max_tokens=max_tokens, timeout=timeout)
        elif route["format"] == "openai_responses":
            result = self._invoke_openai_responses(provider, route, messages, temperature=temperature, max_tokens=max_tokens, timeout=timeout)
        elif route["format"] == "anthropic":
            result = self._invoke_anthropic(provider, route, messages, temperature=temperature, max_tokens=max_tokens, timeout=timeout)
        elif route["format"] == "gemini_native":
            result = self._invoke_gemini(provider, route, messages, temperature=temperature, max_tokens=max_tokens, timeout=timeout)
        else:
            raise LLMRouteError("protocol_mismatch", f"不支持的协议格式：{route['format']}", endpoint=route["endpoint"], resolved_format=route["format"])
        result.setdefault("resolved_endpoint", route["endpoint"])
        result.setdefault("resolved_format", route["format"])
        return result

    def _try_provider_routes(
        self,
        provider: dict[str, Any],
        messages: list[dict[str, str]],
        *,
        temperature: float,
        max_tokens: int,
        timeout: float,
    ) -> dict[str, Any]:
        last_error: LLMRouteError | None = None
        for route in self._build_route_candidates(provider, prefer_verified=True):
            try:
                return self._invoke_route(provider, route, messages, temperature=temperature, max_tokens=max_tokens, timeout=timeout)
            except LLMRouteError as exc:
                last_error = exc
                logger.warning(
                    "LLM route failed provider=%s format=%s endpoint=%s reason=%s",
                    provider.get("key"),
                    route.get("format"),
                    route.get("endpoint"),
                    exc.probe_message,
                )
                continue
        if last_error:
            raise last_error
        raise LLMRouteError("connection_failed", "未找到可用的请求端点")

    def generate(
        self,
        task_key: str,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        if task_key in {"outline", "title", "summary"} and task_key not in self._tasks and "article" in self._tasks:
            task_key = "article"
        task = self._tasks.get(task_key)
        if not task:
            raise ValueError(f"Task {task_key} is not configured. Available: {list(self._tasks.keys())}")

        provider_key = task.get("provider_key", "")
        if not provider_key:
            raise ValueError(f"Task {task_key} has no provider assigned")

        provider = self._providers.get(provider_key)
        if not provider:
            raise ValueError(f"Provider {provider_key} is not configured or disabled")

        fallback_provider_key = task.get("fallback_provider_key", "") or ""
        fallback_provider = self._providers.get(fallback_provider_key) if fallback_provider_key else None

        temp = temperature if temperature is not None else task.get("temperature", 0.7)
        tokens = max_tokens if max_tokens is not None else task.get("max_tokens", 4096)
        client_timeout = timeout if timeout is not None else 120.0

        t0 = time.time()
        failover_triggered = False
        used_provider_key = provider_key

        try:
            result = self._try_provider_routes(provider, messages, temperature=temp, max_tokens=tokens, timeout=client_timeout)
        except LLMRouteError as primary_exc:
            if fallback_provider:
                logger.warning(
                    "LLM primary failed for task=%s provider=%s: %s, trying fallback...",
                    task_key,
                    provider_key,
                    primary_exc.probe_message,
                )
                failover_triggered = True
                used_provider_key = fallback_provider_key
                t0 = time.time()
                try:
                    result = self._try_provider_routes(fallback_provider, messages, temperature=temp, max_tokens=tokens, timeout=client_timeout)
                except LLMRouteError as fallback_exc:
                    logger.error(
                        "LLM fallback also failed for task=%s provider=%s: %s",
                        task_key,
                        fallback_provider_key,
                        fallback_exc.probe_message,
                    )
                    raise ValueError(fallback_exc.probe_message) from fallback_exc
            else:
                logger.error(
                    "LLM call failed for task=%s provider=%s: %s",
                    task_key,
                    provider_key,
                    primary_exc.probe_message,
                )
                raise ValueError(primary_exc.probe_message) from primary_exc

        latency_ms = round((time.time() - t0) * 1000, 1)
        self._track_usage(used_provider_key, result.get("input_tokens", 0), result.get("output_tokens", 0))
        logger.info(
            "LLM call succeeded: task=%s provider=%s format=%s model=%s latency=%.0fms failover=%s",
            task_key,
            used_provider_key,
            result.get("resolved_format", ""),
            result.get("resolved_model", ""),
            latency_ms,
            failover_triggered,
        )
        return {
            "content": result.get("content", ""),
            "model": result.get("resolved_model", ""),
            "provider_key": used_provider_key,
            "input_tokens": int(result.get("input_tokens", 0) or 0),
            "output_tokens": int(result.get("output_tokens", 0) or 0),
            "latency_ms": latency_ms,
            "failover_triggered": failover_triggered,
            "resolved_format": result.get("resolved_format", ""),
            "resolved_endpoint": result.get("resolved_endpoint", ""),
        }

    def test_connection(self, provider_key: str) -> dict[str, Any]:
        provider = self._providers.get(provider_key)
        if not provider:
            raise ValueError(f"Provider {provider_key} is not configured or disabled")

        t0 = time.time()
        try:
            result = self._try_provider_routes(
                provider,
                [{"role": "user", "content": "Hi, respond with only: OK"}],
                temperature=0.0,
                max_tokens=32,
                timeout=20.0,
            )
            latency_ms = round((time.time() - t0) * 1000, 1)
            content = _truncate_text(result.get("content", ""))
            return {
                "ok": True,
                "model": result.get("resolved_model", ""),
                "content": content,
                "latency_ms": latency_ms,
                "error": "",
                "probe_status": "verified",
                "probe_message": "已验证，可用于稿件生成",
                "resolved_endpoint": result.get("resolved_endpoint", ""),
                "resolved_format": result.get("resolved_format", ""),
                "resolved_model": result.get("resolved_model", ""),
                "supports_generation": True,
            }
        except LLMRouteError as exc:
            return {
                "ok": False,
                "model": "",
                "content": "",
                "latency_ms": round((time.time() - t0) * 1000, 1),
                "error": exc.probe_message,
                "probe_status": exc.probe_status,
                "probe_message": exc.probe_message,
                "resolved_endpoint": exc.endpoint,
                "resolved_format": exc.resolved_format,
                "resolved_model": exc.resolved_model,
                "supports_generation": False,
            }

    def _track_usage(self, provider_key: str, input_tokens: int, output_tokens: int) -> None:
        today = time.strftime("%Y-%m-%d")
        if today not in self._usage:
            self._usage[today] = {}
        if provider_key not in self._usage[today]:
            self._usage[today][provider_key] = {"input_tokens": 0, "output_tokens": 0, "calls": 0}
        u = self._usage[today][provider_key]
        u["input_tokens"] += input_tokens
        u["output_tokens"] += output_tokens
        u["calls"] += 1

    def get_usage(self) -> dict[str, dict[str, int]]:
        return dict(self._usage)
