from __future__ import annotations

from contextlib import suppress
from uuid import uuid4
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .models import (
    AutomationModeProfile,
    AutomationModesResponse,
    AutomationProfilesResponse,
    AutomationModeSelectionPayload,
    BatchDraftResponse,
    BrowserSessionPayload,
    BrowserSessionResponse,
    CandidateDraftPayload,
    CandidatesResponse,
    ChannelConfigPayload,
    CreateSourcePayload,
    DiscoveryItemsResponse,
    DictEnvelope,
    DraftApprovalPayload,
    DraftContentPayload,
    DraftsResponse,
    IntelAlertsResponse,
    IntelEventResponse,
    IntelEventsResponse,
    IntelSnapshotResponse,
    IntelSummaryResponse,
    JobRunPayload,
    JobsResponse,
    LLMConfigResponse,
    LLMProviderPayload,
    LLMTaskPayload,
    LLMTestResult,
    LLMUsageResponse,
    LogsResponse,
    ModeSelectionPayload,
    PublishTasksResponse,
    PublishBackendStatusResponse,
    ReferenceProjectsResponse,
    RuntimePlanPayload,
    RuntimePlanResponse,
    SchedulerStatusResponse,
    SourceConnectorPayload,
    SourceSyncResponse,
    SourcesResponse,
    WeChatChannelResponse,
)
from .store import StudioStore


store = StudioStore()
FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")

app = FastAPI(
    title="Auto News Studio API",
    version="0.2.0",
    description="自动化新闻助手运营后台 API，覆盖信息采集、候选选题、公众号草稿和浏览器会话。",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="frontend-assets")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/")
def frontend_index():
    if FRONTEND_DIST.exists():
        return FileResponse(FRONTEND_DIST / "index.html")
    return {"status": "frontend-not-built"}


@app.get("/api/admin/dashboard")
def get_dashboard():
    return store.get_dashboard()


@app.get("/api/admin/intel", response_model=IntelSnapshotResponse)
def get_intel_snapshot():
    return IntelSnapshotResponse(item=store.get_intel_snapshot())


@app.get("/api/admin/intel/summary", response_model=IntelSummaryResponse)
def get_intel_summary():
    return IntelSummaryResponse(item=store.get_intel_summary())


@app.get("/api/admin/intel/stream", response_model=DiscoveryItemsResponse)
def get_intel_stream():
    return DiscoveryItemsResponse(items=store.list_discovery_items())


@app.get("/api/admin/intel/events", response_model=IntelEventsResponse)
def get_intel_events():
    return IntelEventsResponse(items=store.list_intel_events())


@app.get("/api/admin/intel/events/{event_id}", response_model=IntelEventResponse)
def get_intel_event(event_id: str):
    try:
        return IntelEventResponse(item=store.get_intel_event(event_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/admin/intel/alerts", response_model=IntelAlertsResponse)
def get_intel_alerts():
    return IntelAlertsResponse(items=store.list_intel_alerts())


@app.get("/api/admin/intel/sources", response_model=SourcesResponse)
def get_intel_sources():
    return SourcesResponse(items=store.list_intel_sources())


@app.post("/api/admin/intel/watchlist/{event_id}", response_model=IntelEventResponse)
def add_watchlist_event(event_id: str):
    try:
        return IntelEventResponse(item=store.watchlist_event(event_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/admin/intel/ignore/{event_id}", response_model=IntelEventResponse)
def ignore_event(event_id: str):
    try:
        return IntelEventResponse(item=store.ignore_event(event_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.on_event("startup")
async def startup_scheduler() -> None:
    if scheduler.running:
        return
    scheduler.add_job(
        store.run_automation_cycle,
        "interval",
        seconds=60,
        id="automation-cycle",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
    )
    scheduler.start()
    store.reset_runtime_on_boot(message="服务启动后自动运行保持关闭，需要在驾驶舱手动启动。")


@app.on_event("shutdown")
async def shutdown_scheduler() -> None:
    if scheduler.running:
        with suppress(Exception):
            scheduler.shutdown(wait=False)
    store.reset_runtime_on_boot(message="服务关闭时已清空自动运行状态。")


@app.get("/api/admin/modes")
def list_modes():
    return {
        "current": store.get_current_mode(),
        "items": store.list_modes(),
    }


@app.put("/api/admin/modes/current")
def set_current_mode(payload: ModeSelectionPayload):
    try:
        mode = store.set_current_mode(payload.mode)
        return {"current": mode}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/admin/automation/modes", response_model=AutomationModesResponse)
def list_automation_modes():
    return AutomationModesResponse(
        current=store.get_current_automation_mode(),
        items=store.list_automation_modes(),
    )


@app.get("/api/admin/automation/current", response_model=AutomationModesResponse)
def get_current_automation_mode():
    current = store.get_current_automation_mode()
    return AutomationModesResponse(current=current, items=store.list_automation_modes())


@app.put("/api/admin/automation/current", response_model=AutomationModesResponse)
def set_current_automation_mode(payload: AutomationModeSelectionPayload):
    try:
        current = store.set_current_automation_mode(payload.mode)
        return AutomationModesResponse(current=current, items=store.list_automation_modes())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/admin/automation/profiles", response_model=AutomationProfilesResponse)
def list_automation_profiles():
    return AutomationProfilesResponse(
        current=store.get_current_automation_profile(),
        items=store.list_automation_profiles(),
    )


@app.put("/api/admin/automation/profiles/{mode}", response_model=AutomationProfilesResponse)
def update_automation_profile(mode: str, payload: AutomationModeProfile):
    try:
        store.update_automation_profile(mode, payload)
        return AutomationProfilesResponse(
            current=store.get_current_automation_profile(),
            items=store.list_automation_profiles(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/admin/runtime/status", response_model=SchedulerStatusResponse)
def get_runtime_status():
    return SchedulerStatusResponse(item=store.get_runtime_status())


@app.get("/api/admin/runtime/plan", response_model=RuntimePlanResponse)
def get_runtime_plan():
    return RuntimePlanResponse(item=store.get_runtime_plan())


@app.put("/api/admin/runtime/plan", response_model=RuntimePlanResponse)
def update_runtime_plan(payload: RuntimePlanPayload):
    return RuntimePlanResponse(item=store.update_runtime_plan(payload))


@app.post("/api/admin/runtime/start", response_model=SchedulerStatusResponse)
def start_runtime():
    return SchedulerStatusResponse(item=store.start_runtime())


@app.post("/api/admin/runtime/stop", response_model=SchedulerStatusResponse)
def stop_runtime():
    return SchedulerStatusResponse(item=store.stop_runtime())


@app.get("/api/admin/sources", response_model=SourcesResponse)
def list_sources():
    return SourcesResponse(items=store.list_sources())


@app.put("/api/admin/sources/{source_key}")
def update_source(source_key: str, payload: SourceConnectorPayload):
    try:
        return {"item": store.update_source(source_key, payload)}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/admin/sources")
def create_source(payload: CreateSourcePayload):
    try:
        return {"item": store.create_source(payload)}
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.delete("/api/admin/sources/{source_key}")
def delete_source(source_key: str):
    try:
        store.delete_source(source_key)
        return {"ok": True}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/admin/settings")
def get_settings():
    return {"item": store.get_settings()}


@app.put("/api/admin/settings")
def update_settings(payload: dict[str, Any]):
    try:
        return {"item": store.update_settings(payload)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/admin/sources/sync", response_model=SourceSyncResponse)
def sync_sources():
    return store.sync_sources()


@app.post("/api/admin/sources/{source_key}/sync", response_model=SourceSyncResponse)
def sync_source(source_key: str):
    try:
        return store.sync_source(source_key)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/admin/candidates", response_model=CandidatesResponse)
def list_candidates():
    return CandidatesResponse(items=store.list_candidates())


@app.post("/api/admin/candidates/{candidate_id}/draft")
def create_draft_from_candidate(candidate_id: str, payload: CandidateDraftPayload | None = None):
    try:
        mode = payload.publish_mode if payload else None
        return {"item": store.create_draft_from_candidate(candidate_id, publish_mode=mode)}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/admin/candidates/drafts/batch", response_model=BatchDraftResponse)
def batch_create_drafts():
    return store.batch_create_drafts()


@app.get("/api/admin/drafts", response_model=DraftsResponse)
def list_drafts():
    return DraftsResponse(items=store.list_drafts())


@app.post("/api/admin/drafts/{draft_id}/regenerate")
def regenerate_draft(draft_id: str):
    try:
        return {"item": store.regenerate_draft(draft_id)}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/admin/drafts/{draft_id}/approve")
def approve_draft(draft_id: str, payload: DraftApprovalPayload):
    try:
        return {"item": store.approve_draft(draft_id, payload.approved)}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/admin/drafts/{draft_id}/wechat-draft")
def sync_wechat_draft(draft_id: str):
    try:
        return {"item": store.sync_wechat_draft(draft_id)}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/admin/drafts/{draft_id}/open-preview")
def open_preview(draft_id: str):
    try:
        return {"item": store.open_preview(draft_id)}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/admin/drafts/{draft_id}/publish")
def publish_draft(draft_id: str):
    try:
        return {"item": store.publish_draft(draft_id)}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.put("/api/admin/drafts/{draft_id}/content")
def update_draft_content(draft_id: str, payload: DraftContentPayload):
    try:
        return {"item": store.update_draft_content(draft_id, payload.markdown, payload.title)}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


IMAGES_DIR = Path(__file__).resolve().parents[1] / "data" / "images"
MAX_UPLOAD_SIZE = 5 * 1024 * 1024
ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}


@app.post("/api/admin/images/upload")
async def upload_image(file: UploadFile = File(...)):
    content = await file.read()
    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=413, detail="Image too large (max 5MB)")
    suffix = Path(file.filename or "image.png").suffix.lower() or ".png"
    if suffix not in ALLOWED_IMAGE_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {suffix}")
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid4().hex[:12]}{suffix}"
    (IMAGES_DIR / filename).write_bytes(content)
    return {"url": f"/api/admin/images/{filename}"}


@app.get("/api/admin/images/{filename}")
def serve_image(filename: str):
    target = IMAGES_DIR / filename
    if not target.exists():
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(target)


@app.get("/api/admin/publish-tasks", response_model=PublishTasksResponse)
def list_publish_tasks():
    return PublishTasksResponse(items=store.list_publish_tasks())


@app.get("/api/admin/jobs", response_model=JobsResponse)
def list_jobs():
    return JobsResponse(items=store.list_jobs())


@app.post("/api/admin/jobs/run")
def run_job(payload: JobRunPayload):
    try:
        return {"item": store.run_job(payload.action)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/admin/channels/wechat", response_model=WeChatChannelResponse)
def get_wechat_channel():
    return WeChatChannelResponse(item=store.get_wechat_config())


@app.put("/api/admin/channels/wechat")
def update_wechat_channel(payload: ChannelConfigPayload):
    return {"item": store.update_wechat_config(payload)}


@app.get("/api/admin/browser/wechat/session", response_model=BrowserSessionResponse)
def get_browser_session():
    return BrowserSessionResponse(item=store.get_browser_session())


@app.put("/api/admin/browser/wechat/session")
def update_browser_session(payload: BrowserSessionPayload):
    return {"item": store.update_browser_session(payload)}


@app.post("/api/admin/browser/wechat/open-dashboard", response_model=BrowserSessionResponse)
def open_browser_dashboard():
    return BrowserSessionResponse(item=store.open_browser_dashboard())


@app.post("/api/admin/browser/wechat/check", response_model=BrowserSessionResponse)
def check_browser_session():
    return BrowserSessionResponse(item=store.check_browser_session())


@app.get("/api/admin/publish/backends", response_model=PublishBackendStatusResponse)
def get_publish_backends():
    return PublishBackendStatusResponse(items=store.get_publish_backends())


@app.get("/api/admin/reference-projects", response_model=ReferenceProjectsResponse)
def list_reference_projects():
    return ReferenceProjectsResponse(items=store.list_reference_projects())


@app.get("/api/admin/logs", response_model=LogsResponse)
def list_logs():
    return LogsResponse(items=store.list_logs())


# ── LLM config ──────────────────────────────────────────────────

@app.get("/api/admin/llm/config", response_model=LLMConfigResponse)
def get_llm_config():
    return LLMConfigResponse(item=store.get_llm_config())


@app.put("/api/admin/llm/config")
def update_llm_config(payload: dict):
    return LLMConfigResponse(item=store.update_llm_config(payload))


@app.post("/api/admin/llm/test/{provider_key}", response_model=LLMTestResult)
def test_llm_provider(provider_key: str):
    try:
        return LLMTestResult(**store.test_llm_provider(provider_key))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/admin/llm/usage", response_model=LLMUsageResponse)
def get_llm_usage():
    return LLMUsageResponse(item=store.get_llm_usage())
