from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

from ..models import (
    AgentArticlePayload,
    AgentWorkflowResponse,
    AgentWorkflowsResponse,
    BriefCopyPackageResponse,
    BriefResponse,
    BriefsResponse,
    DictOkResponse,
    EventDeepDivePayload,
    EventDeepDiveResponse,
    EventDeepDivesResponse,
    ImportBackupResponse,
)
from .common import RUNTIME_DIR, get_store, http_from_value_error, parse_request_model


IMAGES_DIR = Path(__file__).resolve().parents[2] / "data" / "images"
MAX_UPLOAD_SIZE = 5 * 1024 * 1024
ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}


def build_content_router() -> APIRouter:
    router = APIRouter()

    @router.post("/api/admin/intel/events/{event_id}/deep-dive", response_model=EventDeepDiveResponse)
    def create_event_deep_dive(event_id: str, payload: EventDeepDivePayload | None = None, triggered_by: str = "dashboard"):
        try:
            return EventDeepDiveResponse(
                item=get_store().create_event_deep_dive(
                    event_id,
                    force=bool(payload.force) if payload else False,
                    triggered_by=triggered_by,
                )
            )
        except ValueError as exc:
            raise http_from_value_error(exc) from exc

    @router.get("/api/admin/intel/deep-dives", response_model=EventDeepDivesResponse)
    def list_event_deep_dives():
        return EventDeepDivesResponse(items=get_store().list_event_deep_dives())

    @router.get("/api/admin/intel/deep-dives/{event_id}", response_model=EventDeepDiveResponse)
    def get_event_deep_dive(event_id: str):
        try:
            return EventDeepDiveResponse(item=get_store().get_event_deep_dive(event_id))
        except ValueError as exc:
            raise http_from_value_error(exc) from exc

    @router.post("/api/admin/intel/events/{event_id}/brief", response_model=BriefResponse)
    def create_brief_from_event(event_id: str, triggered_by: str = "dashboard"):
        try:
            return BriefResponse(item=get_store().create_brief_from_event(event_id, triggered_by=triggered_by))
        except ValueError as exc:
            raise http_from_value_error(exc) from exc

    @router.post("/api/admin/agent/articles", response_model=BriefResponse)
    async def create_agent_article(request: Request):
        payload = await parse_request_model(request, AgentArticlePayload)
        try:
            return BriefResponse(item=get_store().create_agent_article(payload))
        except ValueError as exc:
            raise http_from_value_error(exc) from exc

    @router.get("/api/admin/briefs", response_model=BriefsResponse)
    def list_briefs(page: int = 1, page_size: int = 50, stage: str = "all", q: str = "", workflow_mode: str = "all"):
        items, total, safe_page, safe_page_size, has_more, stage_counts, record_counts = get_store().list_briefs(
            page=page,
            page_size=page_size,
            stage=stage,
            q=q,
            workflow_mode=workflow_mode,
        )
        return BriefsResponse(
            items=items,
            total=total,
            page=safe_page,
            page_size=safe_page_size,
            has_more=has_more,
            stage_counts=stage_counts,
            record_counts=record_counts,
        )

    @router.get("/api/admin/agent/workflows", response_model=AgentWorkflowsResponse)
    def list_agent_workflows():
        return AgentWorkflowsResponse(items=get_store().list_agent_workflows())

    @router.get("/api/admin/agent/workflows/{workflow_session_id}", response_model=AgentWorkflowResponse)
    def get_agent_workflow(workflow_session_id: str):
        try:
            return AgentWorkflowResponse(item=get_store().get_agent_workflow(workflow_session_id))
        except ValueError as exc:
            raise http_from_value_error(exc) from exc

    @router.get("/api/admin/briefs/{brief_id}", response_model=BriefResponse)
    def get_brief(brief_id: str):
        try:
            return BriefResponse(item=get_store().get_brief(brief_id))
        except ValueError as exc:
            raise http_from_value_error(exc) from exc

    @router.post("/api/admin/briefs/{brief_id}/wechat-draft", response_model=BriefResponse)
    def sync_brief_wechat_draft(brief_id: str, triggered_by: str = "dashboard"):
        try:
            return BriefResponse(item=get_store().sync_brief_wechat_draft(brief_id, triggered_by=triggered_by))
        except ValueError as exc:
            raise http_from_value_error(exc) from exc

    @router.post("/api/admin/briefs/{brief_id}/copy-package", response_model=BriefCopyPackageResponse)
    def copy_brief_package(brief_id: str):
        try:
            return BriefCopyPackageResponse(markdown=get_store().build_brief_copy_package(brief_id))
        except ValueError as exc:
            raise http_from_value_error(exc) from exc

    @router.delete("/api/admin/briefs/{brief_id}", response_model=DictOkResponse)
    def delete_brief(brief_id: str, remote: str = "auto"):
        try:
            return get_store().delete_brief(brief_id, remote=remote)
        except ValueError as exc:
            raise http_from_value_error(exc) from exc

    @router.post("/api/admin/images/upload")
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

    @router.get("/api/admin/images/{filename}")
    def serve_image(filename: str):
        images_root = IMAGES_DIR.resolve()
        target = (IMAGES_DIR / filename).resolve()
        if images_root not in target.parents and target != images_root:
            raise HTTPException(status_code=400, detail="Invalid filename")
        if not target.exists():
            raise HTTPException(status_code=404, detail="Image not found")
        return FileResponse(target)

    @router.post("/api/admin/system/import-backup", response_model=ImportBackupResponse)
    async def import_system_backup(file: UploadFile = File(...)):
        suffix = Path(file.filename or "backup.zip").suffix or ".zip"
        temp_path = RUNTIME_DIR / f"import-backup-{uuid4().hex}{suffix}"
        temp_path.write_bytes(await file.read())
        try:
            return get_store().import_backup_bundle(temp_path)
        finally:
            temp_path.unlink(missing_ok=True)

    return router
