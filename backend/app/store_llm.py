"""LLM configuration management for StudioStore."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


# Default LLM profiles shipped with the app
DEFAULT_LLM_PROFILES: list[dict[str, Any]] = [
    {
        "id": "nvidia-qwen35-122b",
        "label": "NVIDIA Qwen 122B",
        "description": "主力强模型，实测连通快，适合优先做正式稿。",
        "provider_key": "nvidia",
        "base_url": "https://integrate.api.nvidia.com/v1",
        "api_key": "",
        "model_id": "qwen/qwen3.5-122b-a10b",
        "enabled": False,
    },
    {
        "id": "nvidia-glm47",
        "label": "NVIDIA GLM 4.7",
        "description": "NVIDIA 通道下的 GLM 备选，实测可用且响应很快。",
        "provider_key": "nvidia",
        "base_url": "https://integrate.api.nvidia.com/v1",
        "api_key": "",
        "model_id": "z-ai/glm4.7",
        "enabled": False,
    },
    {
        "id": "nvidia-minimax-m27",
        "label": "NVIDIA MiniMax M2.7",
        "description": "实测可用，接近 10 秒边界，适合作为额外备选。",
        "provider_key": "nvidia",
        "base_url": "https://integrate.api.nvidia.com/v1",
        "api_key": "",
        "model_id": "minimaxai/minimax-m2.7",
        "enabled": False,
    },
    {
        "id": "siliconflow-glm4-9b",
        "label": "SiliconFlow GLM 4 9B",
        "description": "免费且快，适合做稳态兜底。",
        "provider_key": "siliconflow",
        "base_url": "https://api.siliconflow.cn/v1",
        "api_key": "",
        "model_id": "THUDM/GLM-4-9B-0414",
        "enabled": False,
    },
    {
        "id": "siliconflow-glmz1-9b",
        "label": "SiliconFlow GLM Z1 9B",
        "description": "免费备选，实测连通和速度都不错。",
        "provider_key": "siliconflow",
        "base_url": "https://api.siliconflow.cn/v1",
        "api_key": "",
        "model_id": "THUDM/GLM-Z1-9B-0414",
        "enabled": False,
    },
    {
        "id": "siliconflow-deepseek-r1-qwen3-8b",
        "label": "SiliconFlow DeepSeek R1 Qwen3 8B",
        "description": "免费推理型备选，适合做判断和摘要。",
        "provider_key": "siliconflow",
        "base_url": "https://api.siliconflow.cn/v1",
        "api_key": "",
        "model_id": "deepseek-ai/DeepSeek-R1-0528-Qwen3-8B",
        "enabled": False,
    },
    {
        "id": "siliconflow-qwen3-8b",
        "label": "SiliconFlow Qwen3 8B",
        "description": "免费通用备选，适合快速切换测试。",
        "provider_key": "siliconflow",
        "base_url": "https://api.siliconflow.cn/v1",
        "api_key": "",
        "model_id": "Qwen/Qwen3-8B",
        "enabled": False,
    },
]

DEFAULT_LLM_TASK_TEMPLATE: list[dict[str, Any]] = [
    # 3 任务配置：judgement(判断)、translation(翻译)、article(生成)
    # outline/title 合并到 article；summary 改名为 translation
    {"task_key": "judgement", "label": "初步判断", "temperature": 0.2, "max_tokens": 2048, "fallback_provider_key": "", "fallback_model_id": ""},
    {"task_key": "translation", "label": "事件翻译", "temperature": 0.3, "max_tokens": 512, "fallback_provider_key": "", "fallback_model_id": ""},
    {"task_key": "article", "label": "稿件生成", "temperature": 0.7, "max_tokens": 4096, "fallback_provider_key": "", "fallback_model_id": ""},
]


def build_provider_from_profile(profile: dict[str, Any]) -> dict[str, Any]:
    """Convert a profile dict to a provider dict suitable for LLMService."""
    return {
        "key": str(profile.get("provider_key") or "").strip(),
        "label": str(profile.get("label") or "").strip(),
        "base_url": str(profile.get("base_url") or "").strip(),
        "api_key": str(profile.get("api_key") or "").strip(),
        "model_id": str(profile.get("model_id") or "").strip(),
        "enabled": bool(profile.get("enabled")) and bool(str(profile.get("api_key") or "").strip()),
        "last_tested_at": profile.get("last_tested_at"),
        "last_test_result": profile.get("last_test_result"),
    }


def build_tasks_from_profile(profile: dict[str, Any]) -> list[dict[str, Any]]:
    """Build task configs from a profile's provider/model settings."""
    provider_key = str(profile.get("provider_key") or "").strip()
    model_id = str(profile.get("model_id") or "").strip()
    return [
        {
            **task,
            "provider_key": provider_key if bool(profile.get("enabled")) and model_id else "",
            "model_id": model_id if bool(profile.get("enabled")) else "",
        }
        for task in deepcopy(DEFAULT_LLM_TASK_TEMPLATE)
    ]


def default_llm_state() -> dict[str, Any]:
    """Create the default LLM state for a fresh installation."""
    profiles = deepcopy(DEFAULT_LLM_PROFILES)
    current_profile_id = profiles[0]["id"] if profiles else ""
    active_profile = next((item for item in profiles if item["id"] == current_profile_id), {})
    return {
        "current_profile_id": current_profile_id,
        "profiles": profiles,
        "providers": [build_provider_from_profile(active_profile)] if active_profile else [],
        "tasks": build_tasks_from_profile(active_profile) if active_profile else [],
        "usage_today": {},
    }


def merge_llm_profiles(
    incoming_profiles: list[dict[str, Any]],
    existing_profiles: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Merge incoming profiles with existing ones, preserving API keys."""
    existing_by_id = {
        str(item.get("id")): deepcopy(item)
        for item in (existing_profiles or [])
        if isinstance(item, dict) and item.get("id")
    }
    merged_by_id: dict[str, dict[str, Any]] = {
        item["id"]: {**item, **existing_by_id.get(item["id"], {})}
        for item in deepcopy(DEFAULT_LLM_PROFILES)
    }
    for item in incoming_profiles:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        profile_id = str(item["id"])
        profile = {**merged_by_id.get(profile_id, {}), **deepcopy(item)}
        existing = existing_by_id.get(profile_id, {})
        api_key = str(profile.get("api_key") or "").strip()
        if "****" in api_key and existing:
            profile["api_key"] = str(existing.get("api_key") or "")
        merged_by_id[profile_id] = profile

    provider_keys: dict[str, str] = {}
    for profile in list(merged_by_id.values()) + list(existing_by_id.values()):
        provider_key = str(profile.get("provider_key") or "").strip()
        api_key = str(profile.get("api_key") or "").strip()
        if provider_key and api_key and "****" not in api_key:
            provider_keys[provider_key] = api_key

    for profile in merged_by_id.values():
        provider_key = str(profile.get("provider_key") or "").strip()
        if provider_key and not str(profile.get("api_key") or "").strip():
            profile["api_key"] = provider_keys.get(provider_key, "")
        profile["enabled"] = bool(profile.get("enabled")) and bool(str(profile.get("api_key") or "").strip())

    return list(merged_by_id.values())
