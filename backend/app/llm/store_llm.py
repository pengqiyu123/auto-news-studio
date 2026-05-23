"""LLM configuration management for StudioStore."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

SILICONFLOW_DEFAULT_MODEL = "THUDM/GLM-4-9B-0414"
SILICONFLOW_MODEL_ALIASES_TO_MIGRATE = {"glm4", "glm-4"}


# Default LLM profiles — one card per free provider, model selectable via dropdown
DEFAULT_LLM_PROFILES: list[dict[str, Any]] = [
    {
        "id": "preset-nvidia",
        "label": "NVIDIA NIM",
        "description": "免费模型平台，支持多种开源大模型。",
        "provider_key": "nvidia",
        "base_url": "https://integrate.api.nvidia.com/v1",
        "api_key": "",
        "model_id": "qwen/qwen3.5-122b-a10b",
        "enabled": False,
    },
    {
        "id": "preset-siliconflow",
        "label": "SiliconFlow",
        "description": "免费模型平台，支持多种开源大模型。",
        "provider_key": "siliconflow",
        "base_url": "https://api.siliconflow.cn/v1",
        "api_key": "",
        "model_id": SILICONFLOW_DEFAULT_MODEL,
        "enabled": False,
    },
]

# Old profile IDs that were consolidated into the new provider-level profiles
_LEGACY_PROFILE_MIGRATION: dict[str, str] = {
    "nvidia-qwen35-122b": "preset-nvidia",
    "nvidia-glm47": "preset-nvidia",
    "nvidia-minimax-m27": "preset-nvidia",
    "siliconflow-glm4-9b": "preset-siliconflow",
    "siliconflow-glmz1-9b": "preset-siliconflow",
    "siliconflow-deepseek-r1-qwen3-8b": "preset-siliconflow",
    "siliconflow-qwen3-8b": "preset-siliconflow",
}

DEFAULT_LLM_TASK_TEMPLATE: list[dict[str, Any]] = [
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
        "source": profile.get("source"),
        "cc_app_type": profile.get("cc_app_type"),
        "cc_api_format": profile.get("cc_api_format"),
        "cc_is_full_url": profile.get("cc_is_full_url"),
        "cc_endpoint_auto_select": profile.get("cc_endpoint_auto_select"),
        "cc_endpoint_candidates": list(profile.get("cc_endpoint_candidates", []) or []),
        "cc_base_url_raw": profile.get("cc_base_url_raw"),
        "cc_usage_base_url": profile.get("cc_usage_base_url"),
        "cc_last_verified_endpoint": profile.get("cc_last_verified_endpoint"),
        "cc_last_verified_format": profile.get("cc_last_verified_format"),
        "cc_last_verified_model": profile.get("cc_last_verified_model"),
        "cc_probe_status": profile.get("cc_probe_status"),
        "cc_probe_message": profile.get("cc_probe_message"),
    }


def build_runtime_tasks(
    active_profile: dict[str, Any] | None,
    fallback_profile: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Build runtime-only article task config from default/fallback profiles."""
    active_provider_key = str((active_profile or {}).get("provider_key") or "").strip()
    active_model_id = str((active_profile or {}).get("model_id") or "").strip()
    active_enabled = bool((active_profile or {}).get("enabled")) and bool(str((active_profile or {}).get("api_key") or "").strip())
    fallback_provider_key = str((fallback_profile or {}).get("provider_key") or "").strip()
    fallback_model_id = str((fallback_profile or {}).get("model_id") or "").strip()
    fallback_enabled = bool((fallback_profile or {}).get("enabled")) and bool(str((fallback_profile or {}).get("api_key") or "").strip())
    return [
        {
            **task,
            "provider_key": active_provider_key if active_enabled else "",
            "model_id": active_model_id if active_enabled else "",
            "fallback_provider_key": fallback_provider_key if fallback_enabled else "",
            "fallback_model_id": fallback_model_id if fallback_enabled else "",
        }
        for task in deepcopy(DEFAULT_LLM_TASK_TEMPLATE)
    ]


def infer_fallback_profile_id_from_tasks(
    tasks: list[dict[str, Any]],
    profiles: list[dict[str, Any]],
) -> str | None:
    """Infer fallback profile from legacy task configs."""
    article_task = next(
        (
            task for task in tasks
            if str(task.get("task_key") or "").strip() in {"article", "outline", "title", "summary", "translation"}
        ),
        None,
    )
    if not article_task:
        return None
    fallback_provider_key = str(article_task.get("fallback_provider_key") or "").strip()
    fallback_model_id = str(article_task.get("fallback_model_id") or "").strip()
    if not fallback_provider_key:
        return None
    exact_match = next(
        (
            str(profile.get("id") or "")
            for profile in profiles
            if str(profile.get("provider_key") or "").strip() == fallback_provider_key
            and str(profile.get("model_id") or "").strip() == fallback_model_id
        ),
        "",
    )
    if exact_match:
        return exact_match
    provider_match = next(
        (
            str(profile.get("id") or "")
            for profile in profiles
            if str(profile.get("provider_key") or "").strip() == fallback_provider_key
        ),
        "",
    )
    return provider_match or None


def default_llm_state() -> dict[str, Any]:
    """Create the default LLM state for a fresh installation."""
    profiles = deepcopy(DEFAULT_LLM_PROFILES)
    current_profile_id = profiles[0]["id"] if profiles else ""
    return {
        "current_profile_id": current_profile_id,
        "fallback_profile_id": None,
        "profiles": profiles,
        "providers": [],
        "usage_today": {},
    }


def merge_llm_profiles(
    incoming_profiles: list[dict[str, Any]],
    existing_profiles: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Merge incoming profiles with existing ones, preserving API keys.

    Migrates legacy per-model profile IDs (e.g. nvidia-qwen35-122b) into the
    new per-provider profile IDs (e.g. preset-nvidia) so that one API key per
    provider is enough.
    """
    existing_by_id = {
        str(item.get("id")): deepcopy(item)
        for item in (existing_profiles or [])
        if isinstance(item, dict) and item.get("id")
    }

    # Collect real API keys from legacy profiles and map them to new IDs
    legacy_api_keys: dict[str, str] = {}  # new_id -> api_key
    for old_id, new_id in _LEGACY_PROFILE_MIGRATION.items():
        old = existing_by_id.get(old_id)
        if old:
            key = str(old.get("api_key") or "").strip()
            if key and "****" not in key:
                legacy_api_keys.setdefault(new_id, key)

    merged_by_id: dict[str, dict[str, Any]] = {
        item["id"]: {**item, **existing_by_id.get(item["id"], {})}
        for item in deepcopy(DEFAULT_LLM_PROFILES)
    }

    # Apply migrated legacy API keys to new provider profiles
    for new_id, key in legacy_api_keys.items():
        if new_id in merged_by_id and not merged_by_id[new_id].get("api_key"):
            merged_by_id[new_id]["api_key"] = key

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
        model_id = str(profile.get("model_id") or "").strip()
        if provider_key == "siliconflow" and model_id.lower() in SILICONFLOW_MODEL_ALIASES_TO_MIGRATE:
            profile["model_id"] = SILICONFLOW_DEFAULT_MODEL
        if provider_key and not str(profile.get("api_key") or "").strip():
            profile["api_key"] = provider_keys.get(provider_key, "")
        profile["enabled"] = bool(profile.get("enabled")) and bool(str(profile.get("api_key") or "").strip())

    # Filter out legacy profiles that were migrated into new provider profiles
    return [p for p in merged_by_id.values() if p["id"] not in _LEGACY_PROFILE_MIGRATION]
