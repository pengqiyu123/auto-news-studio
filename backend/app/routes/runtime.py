from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..models import (
    AutomationModeProfile,
    AutomationModesResponse,
    AutomationProfilesResponse,
    AutomationModeSelectionPayload,
    RuntimeIntentPayload,
    RuntimePlanPayload,
    RuntimePlanResponse,
    SchedulerStatusResponse,
)
from .common import get_store


def build_runtime_router() -> APIRouter:
    router = APIRouter()

    @router.get("/api/admin/automation/modes", response_model=AutomationModesResponse)
    def list_automation_modes():
        store = get_store()
        return AutomationModesResponse(
            current=store.get_current_automation_mode(),
            items=store.list_automation_modes(),
        )

    @router.get("/api/admin/automation/current", response_model=AutomationModesResponse)
    def get_current_automation_mode():
        store = get_store()
        current = store.get_current_automation_mode()
        return AutomationModesResponse(current=current, items=store.list_automation_modes())

    @router.put("/api/admin/automation/current", response_model=AutomationModesResponse)
    def set_current_automation_mode(payload: AutomationModeSelectionPayload):
        store = get_store()
        try:
            current = store.set_current_automation_mode(payload.mode)
            return AutomationModesResponse(current=current, items=store.list_automation_modes())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/api/admin/automation/profiles", response_model=AutomationProfilesResponse)
    def list_automation_profiles():
        store = get_store()
        return AutomationProfilesResponse(
            current=store.get_current_automation_profile(),
            items=store.list_automation_profiles(),
        )

    @router.put("/api/admin/automation/profiles/{mode}", response_model=AutomationProfilesResponse)
    def update_automation_profile(mode: str, payload: AutomationModeProfile):
        store = get_store()
        try:
            store.update_automation_profile(mode, payload)
            return AutomationProfilesResponse(
                current=store.get_current_automation_profile(),
                items=store.list_automation_profiles(),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/api/admin/runtime/status", response_model=SchedulerStatusResponse)
    def get_runtime_status():
        return SchedulerStatusResponse(item=get_store().get_runtime_status())

    @router.get("/api/admin/runtime/plan", response_model=RuntimePlanResponse)
    def get_runtime_plan():
        return RuntimePlanResponse(item=get_store().get_runtime_plan())

    @router.put("/api/admin/runtime/plan", response_model=RuntimePlanResponse)
    def update_runtime_plan(payload: RuntimePlanPayload):
        return RuntimePlanResponse(item=get_store().update_runtime_plan(payload))

    @router.post("/api/admin/runtime/start", response_model=SchedulerStatusResponse)
    def start_runtime():
        return SchedulerStatusResponse(item=get_store().start_runtime())

    @router.post("/api/admin/runtime/stop", response_model=SchedulerStatusResponse)
    def stop_runtime():
        return SchedulerStatusResponse(item=get_store().stop_runtime())

    @router.post("/api/admin/runtime/run-intent", response_model=SchedulerStatusResponse)
    def run_runtime_intent(payload: RuntimeIntentPayload):
        try:
            return SchedulerStatusResponse(item=get_store().run_runtime_intent(payload.intent))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return router
