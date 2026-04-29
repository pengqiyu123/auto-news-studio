"""Bridge module to read provider configurations from CC-Switch's SQLite database."""

from __future__ import annotations

import json
import sqlite3
import tomllib
from pathlib import Path
from typing import Any


def get_cc_switch_db_path() -> Path | None:
    db = Path.home() / ".cc-switch" / "cc-switch.db"
    return db if db.is_file() else None


def _extract_from_claude_config(settings: dict[str, Any]) -> tuple[str, str, str]:
    env = settings.get("env", {})
    base_url = str(env.get("ANTHROPIC_BASE_URL", "")).strip()
    api_key = str(env.get("ANTHROPIC_AUTH_TOKEN", "") or env.get("ANTHROPIC_API_KEY", "")).strip()
    model = str(env.get("ANTHROPIC_MODEL", "")).strip()
    return base_url, api_key, model


def _extract_from_codex_config(settings: dict[str, Any]) -> tuple[str, str, str]:
    api_key = ""
    auth = settings.get("auth", {})
    if isinstance(auth, dict):
        api_key = str(auth.get("OPENAI_API_KEY", "")).strip()

    base_url = ""
    model = ""
    config_text = str(settings.get("config", "")).strip()
    if config_text:
        try:
            config = tomllib.loads(config_text)
            base_url = str(config.get("base_url", "")).strip()
            model = str(config.get("model", "")).strip()
            # Also check model_providers section
            for section_name, section in config.items():
                if isinstance(section, dict) and section.get("base_url"):
                    if not base_url:
                        base_url = str(section["base_url"]).strip()
                    break
        except Exception:
            pass
    return base_url, api_key, model


def _extract_from_gemini_config(settings: dict[str, Any]) -> tuple[str, str, str]:
    env = settings.get("env", {})
    base_url = str(env.get("GOOGLE_GEMINI_BASE_URL", "")).strip()
    api_key = str(env.get("GEMINI_API_KEY", "")).strip()
    model = str(env.get("GEMINI_MODEL", "")).strip()
    return base_url, api_key, model


def _normalize_cc_api_format(raw: Any, app_type: str, settings: dict[str, Any]) -> str | None:
    value = str(raw or "").strip().lower()
    if value in {"openai_chat", "openai_responses", "anthropic", "gemini_native"}:
        return value

    if app_type == "codex":
        config_text = str(settings.get("config", "")).strip()
        if config_text:
            try:
                config = tomllib.loads(config_text)
            except Exception:
                config = {}
            provider_sections = config.get("model_providers", {})
            if isinstance(provider_sections, dict):
                for section in provider_sections.values():
                    if isinstance(section, dict):
                        wire_api = str(section.get("wire_api") or "").strip().lower()
                        if wire_api == "responses":
                            return "openai_responses"
                        if wire_api == "chat":
                            return "openai_chat"
        return "openai_responses"

    if app_type == "gemini":
        return "gemini_native"

    if app_type == "claude":
        return "anthropic"

    return None


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for raw in values:
        value = str(raw or "").strip()
        if not value:
            continue
        if value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return unique


_EXTRACTORS: dict[str, Any] = {
    "claude": _extract_from_claude_config,
    "codex": _extract_from_codex_config,
    "gemini": _extract_from_gemini_config,
}


def read_cc_switch_providers(db_path: Path | None = None) -> list[dict[str, Any]]:
    db_path = db_path or get_cc_switch_db_path()
    if not db_path:
        return []

    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro&nolock=1", uri=True)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT p.id, p.app_type, p.name, p.settings_config, p.category, p.meta,
                   p.is_current,
                   ph.is_healthy, ph.consecutive_failures, ph.last_error
            FROM providers p
            LEFT JOIN provider_health ph ON p.id = ph.provider_id AND p.app_type = ph.app_type
            ORDER BY COALESCE(p.sort_index, 999999), p.created_at ASC
        """)
        rows = cursor.fetchall()

        endpoint_rows = cursor.execute("""
            SELECT provider_id, app_type, url
            FROM provider_endpoints
            ORDER BY added_at ASC, id ASC
        """).fetchall()
        conn.close()
    except Exception:
        return []

    endpoint_map: dict[tuple[str, str], list[str]] = {}
    for row in endpoint_rows:
        provider_id = str(row["provider_id"] or "").strip()
        app_type = str(row["app_type"] or "").strip()
        url = str(row["url"] or "").strip()
        if not provider_id or not app_type or not url:
            continue
        endpoint_map.setdefault((provider_id, app_type), []).append(url)

    providers: list[dict[str, Any]] = []
    for row in rows:
        app_type = str(row["app_type"]).strip()
        settings_raw = str(row["settings_config"] or "{}").strip()
        try:
            settings = json.loads(settings_raw)
        except json.JSONDecodeError:
            settings = {}
        meta_raw = str(row["meta"] or "{}").strip()
        try:
            meta = json.loads(meta_raw)
        except json.JSONDecodeError:
            meta = {}

        extractor = _EXTRACTORS.get(app_type)
        if not extractor:
            continue

        base_url, api_key, model_id = extractor(settings)
        if not api_key:
            continue

        meta_usage_script = meta.get("usage_script") if isinstance(meta, dict) else None
        usage_base_url = ""
        if isinstance(meta_usage_script, dict):
            usage_base_url = str(meta_usage_script.get("baseUrl") or "").strip()

        provider_id = str(row["id"]).strip()
        endpoint_candidates = _dedupe_preserve_order(
            list(endpoint_map.get((provider_id, app_type), [])) + ([base_url] if base_url else []) + ([usage_base_url] if usage_base_url else [])
        )
        cc_api_format = _normalize_cc_api_format(meta.get("apiFormat"), app_type, settings) if isinstance(meta, dict) else None

        health = None
        if row["is_healthy"] is not None:
            health = {
                "is_healthy": bool(row["is_healthy"]),
                "consecutive_failures": row["consecutive_failures"] or 0,
                "last_error": row["last_error"],
            }

        providers.append({
            "id": f"cc-{row['id']}",
            "label": str(row["name"]).strip(),
            "description": f"从 CC-Switch 导入 ({app_type})",
            "provider_key": f"cc-{row['id']}",
            "base_url": base_url,
            "api_key": api_key,
            "model_id": model_id,
            "enabled": False,
            "source": "cc-switch",
            "cc_app_type": app_type,
            "cc_api_format": cc_api_format,
            "cc_is_full_url": bool(meta.get("isFullUrl")) if isinstance(meta, dict) and meta.get("isFullUrl") is not None else None,
            "cc_endpoint_auto_select": bool(meta.get("endpointAutoSelect")) if isinstance(meta, dict) and meta.get("endpointAutoSelect") is not None else None,
            "cc_endpoint_candidates": endpoint_candidates,
            "cc_base_url_raw": base_url,
            "cc_usage_base_url": usage_base_url or None,
            "cc_last_verified_endpoint": None,
            "cc_last_verified_format": None,
            "cc_last_verified_model": None,
            "cc_probe_status": None,
            "cc_probe_message": None,
            "cc_category": row["category"],
            "cc_is_current": bool(row["is_current"]),
            "cc_health": health,
        })

    return providers
