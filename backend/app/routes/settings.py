from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ..features.logs.read import list_logs_page
from ..features.settings.read import (
    export_system_backup as export_system_backup_view,
    export_system_config as export_system_config_view,
    get_llm_config as get_llm_config_view,
    get_llm_usage as get_llm_usage_view,
    get_settings as get_settings_view,
    list_cc_switch_providers as list_cc_switch_providers_view,
    get_system_doctor as get_system_doctor_view,
    get_system_update as get_system_update_view,
    list_reference_projects as list_reference_projects_view,
)
from ..features.settings.write import (
    dismiss_system_update as dismiss_system_update_action,
    import_cc_switch_profiles as import_cc_switch_profiles_action,
    import_cc_switch_provider_ids as import_cc_switch_provider_ids_action,
    open_cc_switch as open_cc_switch_action,
    test_llm_provider as test_llm_provider_action,
    update_llm_config as update_llm_config_action,
    update_settings as update_settings_action,
)
from ..models import (
    AppUpdateDismissPayload,
    AppUpdateResponse,
    LLMConfig,
    LLMConfigResponse,
    LLMTestResult,
    LLMUsageResponse,
    LogsResponse,
    ReferenceProjectsResponse,
    SettingsUpdatePayload,
    SystemDoctorResponse,
)


def build_settings_router() -> APIRouter:
    router = APIRouter()

    @router.get("/api/admin/system/update", response_model=AppUpdateResponse)
    def get_system_update(force: bool = False):
        return AppUpdateResponse(item=get_system_update_view(force=force))

    @router.post("/api/admin/system/update/dismiss", response_model=AppUpdateResponse)
    def dismiss_system_update(payload: AppUpdateDismissPayload):
        try:
            return AppUpdateResponse(item=dismiss_system_update_action(payload))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/api/admin/settings")
    def get_settings():
        return {"item": get_settings_view()}

    @router.put("/api/admin/settings")
    def update_settings(payload: SettingsUpdatePayload):
        try:
            return {"item": update_settings_action(payload.model_dump(exclude_none=True))}
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/api/admin/system/doctor", response_model=SystemDoctorResponse)
    def get_system_doctor():
        return SystemDoctorResponse(item=get_system_doctor_view())

    @router.post("/api/admin/system/export-config")
    def export_system_config():
        path = export_system_config_view()
        return FileResponse(path, filename=path.name, media_type="application/json")

    @router.post("/api/admin/system/export-backup")
    def export_system_backup():
        path = export_system_backup_view()
        return FileResponse(path, filename=path.name, media_type="application/zip")

    @router.get("/api/admin/reference-projects", response_model=ReferenceProjectsResponse)
    def list_reference_projects():
        return ReferenceProjectsResponse(items=list_reference_projects_view())

    @router.get("/api/admin/logs", response_model=LogsResponse)
    def list_logs(page: int = 1, page_size: int = 50, level: str = "all", q: str = ""):
        payload = list_logs_page(
            page=page,
            page_size=page_size,
            level=level,
            q=q,
        )
        return LogsResponse(
            items=payload["items"],
            total=payload["total"],
            page=payload["page"],
            page_size=payload["page_size"],
            has_more=payload["has_more"],
        )

    @router.get("/api/admin/llm/config", response_model=LLMConfigResponse)
    def get_llm_config():
        return LLMConfigResponse(item=get_llm_config_view())

    @router.put("/api/admin/llm/config", response_model=LLMConfigResponse)
    def update_llm_config(payload: LLMConfig):
        return LLMConfigResponse(item=update_llm_config_action(payload.model_dump()))

    @router.post("/api/admin/llm/test/{provider_key}", response_model=LLMTestResult)
    def test_llm_provider(provider_key: str):
        try:
            return LLMTestResult(**test_llm_provider_action(provider_key))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/api/admin/llm/usage", response_model=LLMUsageResponse)
    def get_llm_usage():
        return LLMUsageResponse(item=get_llm_usage_view())

    @router.post("/api/admin/llm/cc-switch/open")
    def open_cc_switch():
        try:
            return open_cc_switch_action()
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get("/api/admin/llm/cc-switch/providers")
    def list_cc_switch_providers():
        return list_cc_switch_providers_view()

    @router.post("/api/admin/llm/cc-switch/import")
    def import_cc_switch_providers(payload: dict):
        try:
            return LLMConfigResponse(item=import_cc_switch_provider_ids_action(payload.get("provider_ids", [])))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return router
