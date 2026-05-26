from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import importlib
import json
from pathlib import Path
from typing import Any
import zipfile

from ..intel.legacy_sources import build_legacy_rss_sources
from ..llm import LLMService
from ..models import (
    AppUpdateInfo,
    AppVersionInfo,
    ImportBackupResponse,
    LogItem,
    ReferenceProject,
    SystemCheckItem,
    SystemDoctorResult,
)
from ..store.reference_projects import write_reference_baseline
from ..sources import discover_sources
from ..store.base import (
    BACKUP_DIR,
    DEFAULT_RELEASE_NOTES_URL,
    DEFAULT_RELEASE_REPO,
    UNSUPPORTED_SOURCE_DRIVERS,
    UTC,
    atomic_write_json,
    backup_file,
    deepcopy_json,
    now_iso,
    parse_time,
    schedule_to_minutes,
)
from ..llm.store_llm import build_provider_from_profile, build_runtime_tasks, default_llm_state, merge_llm_profiles


def _get_database_settings():
    module = importlib.import_module("backend.app.db.config")
    return module.get_database_settings()


def _check_database_health() -> tuple[bool, str]:
    try:
        module = importlib.import_module("backend.app.db.health")
    except ModuleNotFoundError as exc:
        if exc.name and exc.name.startswith("sqlalchemy"):
            return False, "数据库依赖未安装：缺少 sqlalchemy/psycopg/alembic"
        raise
    return module.check_database_health()


class SettingsMixin:
    def get_llm_usage(self) -> dict[str, dict[str, int]]:
        state = self._read_live()
        return state.get("llm", {}).get("usage_today", {})

    def import_cc_switch_profiles(self, cc_profiles: list[dict[str, Any]]) -> dict[str, Any]:
        state = self._upgrade_state(self._read())
        llm = state.setdefault("llm", default_llm_state())
        existing_profiles = llm.get("profiles", [])
        existing_by_id = {str(p.get("id", "")): deepcopy(p) for p in existing_profiles if isinstance(p, dict) and p.get("id")}

        for cc in cc_profiles:
            pid = str(cc.get("id", ""))
            if not pid:
                continue
            incoming_key = str(cc.get("api_key", ""))
            if pid in existing_by_id:
                existing_key = str(existing_by_id[pid].get("api_key", ""))
                if "****" in incoming_key and existing_key and "****" not in existing_key:
                    cc["api_key"] = existing_key
                existing_by_id[pid] = {**existing_by_id[pid], **cc}
            else:
                existing_by_id[pid] = deepcopy(cc)

        profiles = merge_llm_profiles(list(existing_by_id.values()), existing_profiles)
        for profile in profiles:
            profile["enabled"] = bool(str(profile.get("api_key") or "").strip()) and "****" not in str(profile.get("api_key", ""))

        current_profile_id = str(llm.get("current_profile_id") or "").strip()
        if not any(str(profile.get("id") or "") == current_profile_id for profile in profiles):
            current_profile_id = str(profiles[0].get("id") or "") if profiles else ""

        fallback_profile_id = str(llm.get("fallback_profile_id") or "").strip()
        if fallback_profile_id == current_profile_id:
            fallback_profile_id = ""
        fallback_profile = next((profile for profile in profiles if str(profile.get("id") or "") == fallback_profile_id), None)
        if not fallback_profile or not bool(str(fallback_profile.get("api_key") or "").strip()):
            fallback_profile_id = ""

        llm["current_profile_id"] = current_profile_id
        llm["fallback_profile_id"] = fallback_profile_id or None
        llm["profiles"] = profiles
        llm["providers"] = [
            build_provider_from_profile(profile)
            for profile in profiles
            if bool(str(profile.get("api_key") or "").strip()) and "****" not in str(profile.get("api_key", ""))
        ]
        self._write(state)
        self._append_log(state, "info", "config", f"已从 CC-Switch 导入 {len(cc_profiles)} 个服务商配置")
        return llm

    def get_app_version_info(self) -> AppVersionInfo:
        manifest = self.version_manifest
        return AppVersionInfo(
            version=str(manifest.get("version") or "0.2.11"),
            release_channel=str(manifest.get("release_channel") or "stable"),
            release_repo=str(manifest.get("release_repo") or DEFAULT_RELEASE_REPO),
            release_notes_url=str(manifest.get("release_notes_url") or DEFAULT_RELEASE_NOTES_URL),
        )

    def get_app_update_info(self, force: bool = False) -> AppUpdateInfo:
        current = self.get_app_version_info()
        checked_at = now_iso()
        with self._lock:
            state = self._upgrade_state(self._read())
            app_meta = self._app_meta(state)
            cached = app_meta.get("last_update_check")
            if isinstance(cached, dict) and not force:
                checked_dt = parse_time(str(cached.get("checked_at") or ""))
                if checked_dt and (datetime.now(UTC) - checked_dt).total_seconds() < 1800:
                    payload = deepcopy_json(cached)
                    payload["dismissed_version"] = app_meta.get("dismissed_update_version")
                    payload["dismissed"] = bool(
                        payload.get("latest_version")
                        and app_meta.get("dismissed_update_version")
                        and self._normalize_version_text(str(payload.get("latest_version") or ""))
                        == self._normalize_version_text(str(app_meta.get("dismissed_update_version") or ""))
                    )
                    return AppUpdateInfo(**payload)

        latest_payload, error = self._fetch_latest_release(current.release_repo)
        update_payload = {
            "current_version": current.version,
            "latest_version": latest_payload.get("latest_version") if latest_payload else None,
            "update_available": bool(latest_payload and self._is_version_newer(latest_payload.get("latest_version"), current.version)),
            "checked_at": checked_at,
            "source": latest_payload.get("source") if latest_payload else "unavailable",
            "release_url": latest_payload.get("release_url") if latest_payload else None,
            "release_notes_url": latest_payload.get("release_notes_url") if latest_payload else current.release_notes_url,
            "published_at": latest_payload.get("published_at") if latest_payload else None,
            "error": error,
        }
        with self._lock:
            state = self._upgrade_state(self._read())
            app_meta = self._app_meta(state)
            app_meta["last_update_check"] = deepcopy_json(update_payload)
            self._write(state)
            update_payload["dismissed_version"] = app_meta.get("dismissed_update_version")
            update_payload["dismissed"] = bool(
                update_payload.get("latest_version")
                and app_meta.get("dismissed_update_version")
                and self._normalize_version_text(str(update_payload.get("latest_version") or ""))
                == self._normalize_version_text(str(app_meta.get("dismissed_update_version") or ""))
            )
        return AppUpdateInfo(**update_payload)

    def dismiss_app_update(self, version: str) -> AppUpdateInfo:
        target_version = self._normalize_version_text(version)
        if not target_version:
            raise ValueError("缺少要关闭提示的版本号")
        with self._lock:
            state = self._upgrade_state(self._read())
            app_meta = self._app_meta(state)
            app_meta["dismissed_update_version"] = target_version
            self._write(state)
        return self.get_app_update_info(force=False)

    def system_doctor(self) -> SystemDoctorResult:
        state = self._upgrade_state(self._read())
        browser = self._refresh_browser_session(state)
        llm_cfg = state.get("llm", {})
        profiles = llm_cfg.get("profiles", []) if isinstance(llm_cfg, dict) else []
        enabled_profiles = [
            profile
            for profile in profiles
            if isinstance(profile, dict)
            and bool(str(profile.get("api_key") or "").strip())
            and "****" not in str(profile.get("api_key") or "")
        ]
        dist_index = Path(__file__).resolve().parents[3] / "frontend" / "dist" / "index.html"
        items = [
            SystemCheckItem(
                key="backend",
                label="后端服务",
                ok=True,
                detail="后端接口可访问。",
                next_action=None,
            ),
            SystemCheckItem(
                key="frontend_dist",
                label="前端资源",
                ok=dist_index.exists(),
                detail="已检测到前端构建产物。" if dist_index.exists() else "缺少 frontend/dist，请先运行发布构建或开发构建。",
                next_action=None if dist_index.exists() else "运行 npm run build 生成前端资源。",
            ),
            SystemCheckItem(
                key="llm",
                label="AI 模型",
                ok=bool(enabled_profiles),
                detail=f"已配置 {len(enabled_profiles)} 个可用 profile。" if enabled_profiles else "尚未配置可用的 AI profile。",
                next_action=None if enabled_profiles else "前往设置 > AI 模型，填入至少一个 API Key 并测试连接。",
            ),
            SystemCheckItem(
                key="wechat_profile",
                label="微信浏览器配置",
                ok=bool(str(browser.get("user_data_dir") or "").strip()),
                detail=f"当前 profile：{browser.get('user_data_dir')}" if str(browser.get("user_data_dir") or "").strip() else "尚未配置微信浏览器 profile。",
                next_action=None if str(browser.get("user_data_dir") or "").strip() else "前往设置 > 微信浏览器，先保存浏览器与 profile 路径。",
            ),
            SystemCheckItem(
                key="wechat_login",
                label="公众号登录态",
                ok=bool(browser.get("logged_in")),
                detail="已检测到可复用的公众号登录态。" if browser.get("logged_in") else str(browser.get("last_error") or "尚未完成公众号后台登录检查。"),
                next_action=None if browser.get("logged_in") else "前往设置 > 微信浏览器，打开公众号后台并完成登录检查。",
            ),
        ]
        db_settings = _get_database_settings()
        db_ok, db_detail = _check_database_health()
        db_enabled = db_settings.state_backend in {"dual_write", "postgres"}
        items.append(
            SystemCheckItem(
                key="postgres",
                label="PostgreSQL 主账本",
                ok=db_ok if db_enabled else True,
                detail=db_detail if db_settings.database_url else f"当前未配置数据库，STATE_BACKEND={db_settings.state_backend}",
                next_action=None if (db_ok or not db_enabled) else "检查 DATABASE_URL、PostgreSQL 服务和 Alembic 迁移状态。",
            )
        )
        ok = all(item.ok for item in items)
        summary = "系统已满足分发版基本使用条件。" if ok else "系统仍有未完成项，请按建议补齐后再投入使用。"
        return SystemDoctorResult(checked_at=now_iso(), ok=ok, items=items, summary=summary)

    def export_config_bundle(self) -> Path:
        config = self._upgrade_user_settings(self._read_config())
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        export_path = BACKUP_DIR / f"config-export-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}.json"
        atomic_write_json(export_path, config)
        return export_path

    def export_backup_bundle(self) -> Path:
        state = self._upgrade_state(self._read())
        config = self._upgrade_user_settings(self._read_config())
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        export_path = BACKUP_DIR / f"studio-backup-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}.zip"
        with zipfile.ZipFile(export_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("config/user-settings.json", json.dumps(config, ensure_ascii=False, indent=2))
            zf.writestr("data/state.json", json.dumps(state, ensure_ascii=False, indent=2))
            recent_logs = {"logs": state.get("logs", [])[:200]}
            zf.writestr("logs/recent-logs.json", json.dumps(recent_logs, ensure_ascii=False, indent=2))
        return export_path

    def import_backup_bundle(self, file_path: Path) -> ImportBackupResponse:
        if not file_path.exists():
            raise ValueError("备份文件不存在。")
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        rollback = BACKUP_DIR / f"rollback-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}"
        rollback.mkdir(parents=True, exist_ok=True)
        backup_file(self.data_file, rollback, "state")
        backup_file(self.config_file, rollback, "config")
        with zipfile.ZipFile(file_path, "r") as zf:
            if "config/user-settings.json" in zf.namelist():
                config = json.loads(zf.read("config/user-settings.json").decode("utf-8"))
                self._write_config(self._upgrade_user_settings(config))
            if "data/state.json" in zf.namelist():
                state = json.loads(zf.read("data/state.json").decode("utf-8"))
                self._write(self._upgrade_state(state))
        return ImportBackupResponse(ok=True, message="已导入备份。若为新机器，请重新登录公众号后台。", backup_path=str(rollback))

    def get_settings(self) -> dict[str, Any]:
        config = self._upgrade_user_settings(self._read_config())
        return deepcopy_json(config.get("settings", {}))

    def update_settings(self, updates: dict[str, Any]) -> dict[str, Any]:
        state = self._upgrade_state(self._read())
        settings = state.setdefault("settings", {})
        config = self._read_config()
        config_settings = config.setdefault("settings", {})
        if "max_workers" in updates:
            value = int(updates["max_workers"])
            if not 1 <= value <= 20:
                raise ValueError("max_workers 必须在 1-20 之间")
            settings["max_workers"] = value
            config_settings["max_workers"] = value
        if "tavily_api_key" in updates:
            compact = str(updates.get("tavily_api_key") or "").strip()
            settings["tavily_api_key"] = compact
            config_settings["tavily_api_key"] = compact
        self._append_log(state, "success", "settings", f"已更新设置: {list(updates.keys())}")
        self._write_config(self._upgrade_user_settings(config))
        self._write(state)
        return settings

    def list_reference_projects(self) -> list[ReferenceProject]:
        state = self._upgrade_state(self._read())
        state["reference_projects"] = write_reference_baseline()
        self._write(state)
        return [ReferenceProject(**item) for item in state["reference_projects"]]

    def list_logs(
        self,
        *,
        page: int = 1,
        page_size: int = 50,
        level: str = "all",
        q: str = "",
    ) -> tuple[list[LogItem], int, int, int, bool]:
        state = self._read_live()
        items = [item for item in state["logs"] if isinstance(item, dict)]
        items.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
        level_filter = str(level or "all").strip().lower()
        keyword = str(q or "").strip().lower()

        def matches_level(item: dict[str, Any]) -> bool:
            if level_filter == "all":
                return True
            return str(item.get("level") or "").lower() == level_filter

        def matches_query(item: dict[str, Any]) -> bool:
            if not keyword:
                return True
            haystack = "\n".join(
                [
                    str(item.get("message") or ""),
                    str(item.get("detail") or ""),
                    str(item.get("category") or ""),
                    str(item.get("actor") or ""),
                ]
            ).lower()
            return keyword in haystack

        filtered = [item for item in items if matches_level(item) and matches_query(item)]
        page_items, total, safe_page, safe_page_size, has_more = self._paginate_items(
            filtered,
            page=page,
            page_size=page_size,
        )
        return [LogItem(**item) for item in page_items], total, safe_page, safe_page_size, has_more

    def get_llm_config(self) -> dict[str, Any]:
        config = self._upgrade_user_settings(self._read_config())
        cfg = deepcopy(config.get("llm", {}))
        cfg.pop("tasks", None)
        for profile in cfg.get("profiles", []):
            key = str(profile.get("api_key", ""))
            if key and profile.get("id", "").startswith("cc-"):
                profile["api_key"] = key[:4] + "****" + key[-4:] if len(key) > 8 else "****"
        for provider in cfg.get("providers", []):
            key = str(provider.get("api_key", ""))
            if key:
                provider["api_key"] = key[:4] + "****" + key[-4:] if len(key) > 8 else "****"
        return cfg

    def update_llm_config(self, config: dict[str, Any]) -> dict[str, Any]:
        state = self._upgrade_state(self._read())
        existing = state.get("llm", {})
        profiles = merge_llm_profiles(
            [item for item in config.get("profiles", []) if isinstance(item, dict)],
            [item for item in existing.get("profiles", []) if isinstance(item, dict)],
        )
        current_profile_id = str(config.get("current_profile_id") or existing.get("current_profile_id") or "").strip()
        active_profile = next((item for item in profiles if item.get("id") == current_profile_id), None)
        if not active_profile and profiles:
            active_profile = profiles[0]
            current_profile_id = str(active_profile.get("id") or "")
        for profile in profiles:
            profile["enabled"] = bool(str(profile.get("api_key") or "").strip()) and "****" not in str(profile.get("api_key", ""))

        fallback_profile_id = str(config.get("fallback_profile_id") or existing.get("fallback_profile_id") or "").strip()
        if fallback_profile_id == current_profile_id:
            fallback_profile_id = ""
        fallback_profile = next((item for item in profiles if item.get("id") == fallback_profile_id), None)
        if not fallback_profile:
            fallback_profile_id = ""
        elif not bool(str(fallback_profile.get("api_key") or "").strip()):
            fallback_profile_id = ""

        providers_map: dict[str, dict[str, Any]] = {}
        if active_profile:
            active_provider = build_provider_from_profile(active_profile)
            if active_provider.get("key"):
                providers_map[active_provider["key"]] = active_provider
        if fallback_profile and fallback_profile_id:
            fallback_provider = build_provider_from_profile(fallback_profile)
            if fallback_provider.get("key"):
                providers_map.setdefault(fallback_provider["key"], fallback_provider)
        for profile in profiles:
            provider_key = str(profile.get("provider_key") or "")
            api_key = str(profile.get("api_key") or "").strip()
            if provider_key and api_key and "****" not in api_key and provider_key not in providers_map:
                providers_map[provider_key] = build_provider_from_profile(profile)

        next_llm = {
            "current_profile_id": current_profile_id,
            "fallback_profile_id": fallback_profile_id or None,
            "profiles": profiles,
            "providers": list(providers_map.values()),
            "usage_today": existing.get("usage_today", {}),
        }
        state["llm"] = next_llm
        settings_config = self._read_config()
        settings_config["llm"] = deepcopy_json(next_llm)
        self._write_config(self._upgrade_user_settings(settings_config))
        self._write(state)
        self._append_log(state, "info", "config", "已更新 AI 模型配置")
        return state["llm"]

    def test_llm_provider(self, provider_key: str) -> dict[str, Any]:
        state = self._upgrade_state(self._read())
        profiles = state.get("llm", {}).get("profiles", [])
        providers = state.get("llm", {}).get("providers", [])

        profile = next((item for item in profiles if item.get("provider_key") == provider_key or item.get("id") == provider_key), None)
        provider: dict[str, Any] | None = None
        tested_profile_id = ""
        if profile:
            tested_profile_id = str(profile.get("id") or "")
            provider = build_provider_from_profile(profile)
            provider["enabled"] = True
        if not provider:
            provider = next((item for item in providers if item.get("key") == provider_key), None)
            if provider:
                provider = deepcopy(provider)
        if not provider:
            raise ValueError(f"未找到服务商配置：{provider_key}")

        api_key = str(provider.get("api_key", "")).strip()
        if not api_key or "****" in api_key:
            raise ValueError(f"Provider {provider_key} has no API key configured")

        provider["enabled"] = True
        llm_config = deepcopy(state.get("llm", {}))
        llm_config["providers"] = [provider]
        llm_service = LLMService(llm_config)
        result = llm_service.test_connection(str(provider.get("key") or provider_key))
        tested_at = now_iso()
        for profile in profiles:
            if str(profile.get("id") or "") == tested_profile_id:
                profile["last_tested_at"] = tested_at
                profile["last_test_result"] = "ok" if result.get("ok") else result.get("error", "failed")
                profile["cc_probe_status"] = result.get("probe_status") or ("verified" if result.get("ok") else "request_failed")
                profile["cc_probe_message"] = result.get("probe_message") or result.get("error") or ""
                if result.get("ok"):
                    profile["cc_last_verified_endpoint"] = result.get("resolved_endpoint") or profile.get("cc_last_verified_endpoint")
                    profile["cc_last_verified_format"] = result.get("resolved_format") or profile.get("cc_last_verified_format")
                    profile["cc_last_verified_model"] = result.get("resolved_model") or result.get("model") or profile.get("cc_last_verified_model")
        state["llm"]["profiles"] = profiles
        config = self._read_config()
        config["llm"] = deepcopy_json(state["llm"])
        self._write_config(self._upgrade_user_settings(config))
        self._write(state)
        return result

    def _build_source_registry(self) -> list[dict[str, Any]]:
        merged: list[dict[str, Any]] = deepcopy(discover_sources())
        seen_keys = {item["key"] for item in merged}
        seen_urls = {item["url"] for item in merged if item.get("url")}
        for source in build_legacy_rss_sources():
            if source["key"] in seen_keys or source.get("url") in seen_urls:
                continue
            source.setdefault("platform", source.get("kind", "rss"))
            source.setdefault("interval_minutes", schedule_to_minutes(source.get("schedule")) or 30)
            source.setdefault("weight", 0.7)
            merged.append(source)
            seen_keys.add(source["key"])
            if source.get("url"):
                seen_urls.add(source["url"])
        return merged

    def _prune_unsupported_sources(self, state: dict[str, Any]) -> None:
        state.setdefault("logs", [])
        state.setdefault("sources", [])
        sources_before = list(state.get("sources", []))
        supported_sources = [
            source
            for source in sources_before
            if str(source.get("driver") or "") not in UNSUPPORTED_SOURCE_DRIVERS
        ]
        if len(supported_sources) == len(sources_before):
            return
        removed_names = [
            str(source.get("name") or source.get("key") or "unknown")
            for source in sources_before
            if str(source.get("driver") or "") in UNSUPPORTED_SOURCE_DRIVERS
        ]
        state["sources"] = supported_sources
        if removed_names:
            self._append_log(
                state,
                "warning",
                "source",
                f"已移除不再支持的来源驱动：{', '.join(removed_names[:8])}",
                detail="unsupported drivers pruned during migration",
            )

    def _make_llm_service(self, state: dict[str, Any]) -> LLMService | None:
        llm_config = state.get("llm", {})
        if not llm_config or not llm_config.get("profiles"):
            return None
        profiles = [item for item in llm_config.get("profiles", []) if isinstance(item, dict)]
        current_profile_id = str(llm_config.get("current_profile_id") or "").strip()
        fallback_profile_id = str(llm_config.get("fallback_profile_id") or "").strip()
        active_profile = next((item for item in profiles if str(item.get("id") or "") == current_profile_id), None)
        fallback_profile = next((item for item in profiles if str(item.get("id") or "") == fallback_profile_id), None)
        runtime_tasks = build_runtime_tasks(active_profile, fallback_profile)
        if not runtime_tasks or not runtime_tasks[0].get("provider_key"):
            return None
        providers = [
            build_provider_from_profile(profile)
            for profile in profiles
            if bool(str(profile.get("api_key") or "").strip()) and "****" not in str(profile.get("api_key", ""))
        ]
        if not providers:
            return None
        config = deepcopy(llm_config)
        config["providers"] = providers
        config["tasks"] = runtime_tasks
        return LLMService(config)
