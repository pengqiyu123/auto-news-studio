"""Multi-provider LLM abstraction layer.

All major Chinese and international LLM providers expose an OpenAI-compatible
chat completions API, so a single OpenAI SDK client with different base_url
values covers every provider.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from openai import APIConnectionError, APITimeoutError, RateLimitError

logger = logging.getLogger(__name__)

PROVIDER_REGISTRY: dict[str, dict[str, Any]] = {
    "nvidia": {
        "label": "NVIDIA NIM",
        "base_url": "https://integrate.api.nvidia.com/v1",
        "models": [
            "qwen/qwen3.5-122b-a10b",
            "z-ai/glm4.7",
            "minimaxai/minimax-m2.7",
            "z-ai/glm-5.1",
            "deepseek-ai/deepseek-v4-flash",
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
            "THUDM/GLM-Z1-9B-0414",
            "deepseek-ai/DeepSeek-R1-0528-Qwen3-8B",
            "Qwen/Qwen3-8B",
            "Qwen/Qwen3.5-4B",
            "THUDM/GLM-4.1V-9B-Thinking",
            "deepseek-ai/DeepSeek-V3",
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

DEFAULT_TASK_CONFIGS: dict[str, dict[str, Any]] = {
    "judgement": {"label": "初步判断", "temperature": 0.2, "max_tokens": 2048},
    "outline": {"label": "大纲生成", "temperature": 0.4, "max_tokens": 2048},
    "article": {"label": "正文撰写", "temperature": 0.7, "max_tokens": 4096},
    "title": {"label": "标题优化", "temperature": 0.8, "max_tokens": 512},
    "summary": {"label": "摘要生成", "temperature": 0.5, "max_tokens": 1024},
}


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

    def _get_client(self, provider_key: str):
        from openai import OpenAI

        provider = self._providers.get(provider_key)
        if not provider:
            raise ValueError(f"Provider {provider_key} is not configured or disabled")

        registry = PROVIDER_REGISTRY.get(provider_key, {})
        base_url = provider.get("base_url") or registry.get("base_url", "")
        api_key = provider.get("api_key", "")
        if not api_key:
            raise ValueError(f"Provider {provider_key} has no API key configured")

        return OpenAI(base_url=base_url, api_key=api_key, timeout=120.0)

    def generate(
        self,
        task_key: str,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        """Dispatch a generation request to the configured model for a task.

        Returns a dict with keys: content, model, provider_key, input_tokens,
        output_tokens, latency_ms.
        """
        task = self._tasks.get(task_key)
        if not task:
            raise ValueError(f"Task {task_key} is not configured. Available: {list(self._tasks.keys())}")

        provider_key = task.get("provider_key", "")
        model_id = task.get("model_id", "")
        if not provider_key or not model_id:
            raise ValueError(f"Task {task_key} has no provider or model assigned")

        temp = temperature if temperature is not None else task.get("temperature", 0.7)
        tokens = max_tokens if max_tokens is not None else task.get("max_tokens", 4096)

        client = self._get_client(provider_key)
        t0 = time.time()

        try:
            response = client.chat.completions.create(
                model=model_id,
                messages=messages,
                temperature=temp,
                max_tokens=tokens,
            )
        except (RateLimitError, APIConnectionError, APITimeoutError) as exc:
            logger.error("LLM call failed for provider=%s model=%s: %s", provider_key, model_id, exc)
            raise

        latency_ms = round((time.time() - t0) * 1000, 1)
        content = ""
        input_tokens = 0
        output_tokens = 0

        if response.choices:
            content = response.choices[0].message.content or ""
        if response.usage:
            input_tokens = response.usage.prompt_tokens or 0
            output_tokens = response.usage.completion_tokens or 0

        self._track_usage(provider_key, input_tokens, output_tokens)

        logger.info(
            "LLM call succeeded: task=%s provider=%s model=%s in=%d out=%d latency=%.0fms",
            task_key, provider_key, model_id, input_tokens, output_tokens, latency_ms,
        )

        return {
            "content": content,
            "model": model_id,
            "provider_key": provider_key,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "latency_ms": latency_ms,
        }

    def test_connection(self, provider_key: str) -> dict[str, Any]:
        """Test connectivity for a provider by sending a minimal request."""
        client = self._get_client(provider_key)
        provider = self._providers[provider_key]
        model_id = provider.get("model_id", "")

        registry = PROVIDER_REGISTRY.get(provider_key, {})
        if not model_id and registry.get("models"):
            model_id = registry["models"][0]

        if not model_id:
            return {"ok": False, "error": "No model available for this provider"}

        t0 = time.time()
        try:
            response = client.chat.completions.create(
                model=model_id,
                messages=[{"role": "user", "content": "Hi, respond with only: OK"}],
                temperature=0.0,
                max_tokens=16,
            )
            latency_ms = round((time.time() - t0) * 1000, 1)
            content = response.choices[0].message.content if response.choices else ""
            return {"ok": True, "model": model_id, "content": content[:50], "latency_ms": latency_ms}
        except RateLimitError as exc:
            return {"ok": False, "error": f"Rate limited: {exc}"}
        except APIConnectionError as exc:
            return {"ok": False, "error": f"Connection failed: {exc}"}
        except APITimeoutError as exc:
            return {"ok": False, "error": f"Timeout: {exc}"}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

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
