from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..features.settings.read import (
    get_automation_modes_page as get_automation_modes_page_view,
)
from ..features.settings.read import (
    get_automation_profiles_page as get_automation_profiles_page_view,
)
from ..features.settings.read import (
    get_runtime_plan as get_runtime_plan_view,
)
from ..features.settings.read import (
    get_runtime_status as get_runtime_status_view,
)
from ..features.settings.write import (
    run_runtime_intent as run_runtime_intent_action,
)
from ..features.settings.write import (
    set_current_automation_mode_page as set_current_automation_mode_page_action,
)
from ..features.settings.write import (
    start_runtime as start_runtime_action,
)
from ..features.settings.write import (
    stop_runtime as stop_runtime_action,
)
from ..features.settings.write import (
    update_automation_profile_page as update_automation_profile_page_action,
)
from ..features.settings.write import (
    update_runtime_plan as update_runtime_plan_action,
)
from ..models import (
    AutomationModeProfile,
    AutomationModeSelectionPayload,
    AutomationModesResponse,
    AutomationProfilesResponse,
    RuntimeIntentPayload,
    RuntimePlanPayload,
    RuntimePlanResponse,
    SchedulerStatusResponse,
)


def build_runtime_router() -> APIRouter:
    router = APIRouter()

    @router.get("/api/admin/automation/modes", response_model=AutomationModesResponse)
    def list_automation_modes():
        payload = get_automation_modes_page_view()
        return AutomationModesResponse(
            current=payload["current"],
            items=payload["items"],
        )

    @router.get("/api/admin/automation/current", response_model=AutomationModesResponse)
    def get_current_automation_mode():
        payload = get_automation_modes_page_view()
        return AutomationModesResponse(current=payload["current"], items=payload["items"])

    @router.put("/api/admin/automation/current", response_model=AutomationModesResponse)
    def set_current_automation_mode(payload: AutomationModeSelectionPayload):
        try:
            result = set_current_automation_mode_page_action(payload.mode)
            return AutomationModesResponse(current=result["current"], items=result["items"])
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/api/admin/automation/profiles", response_model=AutomationProfilesResponse)
    def list_automation_profiles():
        payload = get_automation_profiles_page_view()
        return AutomationProfilesResponse(
            current=payload["current"],
            items=payload["items"],
        )

    @router.put("/api/admin/automation/profiles/{mode}", response_model=AutomationProfilesResponse)
    def update_automation_profile(mode: str, payload: AutomationModeProfile):
        try:
            result = update_automation_profile_page_action(mode, payload)
            return AutomationProfilesResponse(
                current=result["current"],
                items=result["items"],
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/api/admin/runtime/status", response_model=SchedulerStatusResponse)
    def get_runtime_status():
        return SchedulerStatusResponse(item=get_runtime_status_view())

    @router.get("/api/admin/runtime/plan", response_model=RuntimePlanResponse)
    def get_runtime_plan():
        return RuntimePlanResponse(item=get_runtime_plan_view())

    @router.put("/api/admin/runtime/plan", response_model=RuntimePlanResponse)
    def update_runtime_plan(payload: RuntimePlanPayload):
        return RuntimePlanResponse(item=update_runtime_plan_action(payload))

    @router.post("/api/admin/runtime/start", response_model=SchedulerStatusResponse)
    def start_runtime():
        return SchedulerStatusResponse(item=start_runtime_action())

    @router.post("/api/admin/runtime/stop", response_model=SchedulerStatusResponse)
    def stop_runtime():
        return SchedulerStatusResponse(item=stop_runtime_action())

    @router.post("/api/admin/runtime/run-intent", response_model=SchedulerStatusResponse)
    def run_runtime_intent(payload: RuntimeIntentPayload):
        try:
            return SchedulerStatusResponse(item=run_runtime_intent_action(payload.intent))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return router
