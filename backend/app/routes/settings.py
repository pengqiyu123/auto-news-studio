from __future__ import annotations

import ctypes
import subprocess
from pathlib import Path
import winreg

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ..cc_switch_bridge import get_cc_switch_db_path, read_cc_switch_providers
from ..models import (
    AppUpdateDismissPayload,
    AppUpdateResponse,
    ImportBackupResponse,
    LLMConfig,
    LLMConfigResponse,
    LLMTestResult,
    LLMUsageResponse,
    LogsResponse,
    ReferenceProjectsResponse,
    SettingsUpdatePayload,
    SystemDoctorResponse,
)
from .common import get_store


def build_settings_router() -> APIRouter:
    router = APIRouter()

    @router.get("/api/admin/system/update", response_model=AppUpdateResponse)
    def get_system_update(force: bool = False):
        return AppUpdateResponse(item=get_store().get_app_update_info(force=force))

    @router.post("/api/admin/system/update/dismiss", response_model=AppUpdateResponse)
    def dismiss_system_update(payload: AppUpdateDismissPayload):
        try:
            return AppUpdateResponse(item=get_store().dismiss_app_update(payload.version))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/api/admin/settings")
    def get_settings():
        return {"item": get_store().get_settings()}

    @router.put("/api/admin/settings")
    def update_settings(payload: SettingsUpdatePayload):
        try:
            return {"item": get_store().update_settings(payload.model_dump(exclude_none=True))}
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/api/admin/system/doctor", response_model=SystemDoctorResponse)
    def get_system_doctor():
        return SystemDoctorResponse(item=get_store().system_doctor())

    @router.post("/api/admin/system/export-config")
    def export_system_config():
        path = get_store().export_config_bundle()
        return FileResponse(path, filename=path.name, media_type="application/json")

    @router.post("/api/admin/system/export-backup")
    def export_system_backup():
        path = get_store().export_backup_bundle()
        return FileResponse(path, filename=path.name, media_type="application/zip")

    @router.get("/api/admin/reference-projects", response_model=ReferenceProjectsResponse)
    def list_reference_projects():
        return ReferenceProjectsResponse(items=get_store().list_reference_projects())

    @router.get("/api/admin/logs", response_model=LogsResponse)
    def list_logs(page: int = 1, page_size: int = 50, level: str = "all", q: str = ""):
        items, total, safe_page, safe_page_size, has_more = get_store().list_logs(
            page=page,
            page_size=page_size,
            level=level,
            q=q,
        )
        return LogsResponse(
            items=items,
            total=total,
            page=safe_page,
            page_size=safe_page_size,
            has_more=has_more,
        )

    @router.get("/api/admin/llm/config", response_model=LLMConfigResponse)
    def get_llm_config():
        return LLMConfigResponse(item=get_store().get_llm_config())

    @router.put("/api/admin/llm/config", response_model=LLMConfigResponse)
    def update_llm_config(payload: LLMConfig):
        return LLMConfigResponse(item=get_store().update_llm_config(payload.model_dump()))

    @router.post("/api/admin/llm/test/{provider_key}", response_model=LLMTestResult)
    def test_llm_provider(provider_key: str):
        try:
            return LLMTestResult(**get_store().test_llm_provider(provider_key))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/api/admin/llm/usage", response_model=LLMUsageResponse)
    def get_llm_usage():
        return LLMUsageResponse(item=get_store().get_llm_usage())

    @router.post("/api/admin/llm/cc-switch/open")
    def open_cc_switch():
        for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            try:
                key = winreg.OpenKey(hive, r"Software\Microsoft\Windows\CurrentVersion\Uninstall")
                for i in range(winreg.QueryInfoKey(key)[0]):
                    sub = winreg.EnumKey(key, i)
                    try:
                        with winreg.OpenKey(key, sub) as sk:
                            name = winreg.QueryValueEx(sk, "DisplayName")[0] or ""
                            if "cc switch" in name.lower():
                                loc = winreg.QueryValueEx(sk, "InstallLocation")[0]
                                if loc:
                                    exe = Path(loc) / "cc-switch.exe"
                                    if exe.exists():
                                        subprocess.Popen(
                                            [str(exe)],
                                            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
                                        )
                                        return {"ok": True}
                    except (OSError, FileNotFoundError):
                        pass
                winreg.CloseKey(key)
            except (OSError, FileNotFoundError):
                pass

        desktop = Path.home() / "Desktop"
        for lnk in desktop.glob("*CC*Switch*"):
            if lnk.suffix == ".lnk":
                ctypes.windll.shell32.ShellExecuteW(None, "open", str(lnk), None, None, 1)
                return {"ok": True}

        raise HTTPException(status_code=404, detail="未找到 CC-Switch，请确认已安装")

    @router.get("/api/admin/llm/cc-switch/providers")
    def list_cc_switch_providers():
        db_path = get_cc_switch_db_path()
        providers = read_cc_switch_providers(db_path) if db_path else []
        masked = []
        for p in providers:
            key = p.get("api_key", "")
            masked.append(
                {
                    **{k: v for k, v in p.items() if k != "api_key"},
                    "has_api_key": bool(key.strip()),
                    "api_key_preview": f"{key[:6]}...{key[-4:]}" if len(key) > 10 else "****" if key else "",
                }
            )
        return {"providers": masked, "db_available": db_path is not None}

    @router.post("/api/admin/llm/cc-switch/import")
    def import_cc_switch_providers(payload: dict):
        selected_ids = payload.get("provider_ids", [])
        db_path = get_cc_switch_db_path()
        if not db_path:
            raise HTTPException(status_code=400, detail="未找到 CC-Switch 数据库，请确认 CC-Switch 已安装")
        all_providers = read_cc_switch_providers(db_path)
        selected = [p for p in all_providers if p.get("id") in selected_ids]
        if not selected:
            raise HTTPException(status_code=400, detail="未找到选中的 provider")
        return LLMConfigResponse(item=get_store().import_cc_switch_profiles(selected))

    return router
