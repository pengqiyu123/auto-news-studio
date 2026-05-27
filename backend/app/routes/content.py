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
from ..api.admin.agent_analytics import router as analytics_router
from ..features.briefs.read import (
    copy_brief_package_page as copy_brief_package_page_view,
    get_agent_workflow_page as get_agent_workflow_page_view,
    get_brief_page as get_brief_page_view,
    get_deep_dive_page as get_deep_dive_page_view,
    list_agent_workflows_page as list_agent_workflows_page_view,
    list_briefs_page as list_briefs_page_view,
    list_deep_dives_page as list_deep_dives_page_view,
)
from ..features.briefs.write import (
    abandon_agent_workflow_page as abandon_agent_workflow_page_action,
    create_agent_article_page as create_agent_article_page_action,
    create_brief_from_event_page as create_brief_from_event_page_action,
    create_daily_digest_brief_page as create_daily_digest_brief_page_action,
    create_event_deep_dive_page as create_event_deep_dive_page_action,
    delete_brief_page as delete_brief_page_action,
    sync_brief_wechat_draft_page as sync_brief_wechat_draft_page_action,
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
                **create_event_deep_dive_page_action(
                    event_id,
                    force=bool(payload.force) if payload else False,
                    triggered_by=triggered_by,
                )
            )
        except ValueError as exc:
            raise http_from_value_error(exc) from exc

    @router.get("/api/admin/intel/deep-dives", response_model=EventDeepDivesResponse)
    def list_event_deep_dives():
        return EventDeepDivesResponse(**list_deep_dives_page_view())

    @router.get("/api/admin/intel/deep-dives/{event_id}", response_model=EventDeepDiveResponse)
    def get_event_deep_dive(event_id: str):
        try:
            return EventDeepDiveResponse(**get_deep_dive_page_view(event_id))
        except ValueError as exc:
            raise http_from_value_error(exc) from exc

    @router.post("/api/admin/intel/events/{event_id}/brief", response_model=BriefResponse)
    def create_brief_from_event(event_id: str, triggered_by: str = "dashboard"):
        try:
            return BriefResponse(**create_brief_from_event_page_action(event_id, triggered_by=triggered_by))
        except ValueError as exc:
            raise http_from_value_error(exc) from exc

    @router.post("/api/admin/agent/articles", response_model=BriefResponse)
    async def create_agent_article(request: Request):
        payload = await parse_request_model(request, AgentArticlePayload)
        try:
            return BriefResponse(**create_agent_article_page_action(payload))
        except ValueError as exc:
            raise http_from_value_error(exc) from exc

    @router.get("/api/admin/briefs", response_model=BriefsResponse)
    def list_briefs(page: int = 1, page_size: int = 50, stage: str = "all", q: str = "", workflow_mode: str = "all"):
        payload = list_briefs_page_view(
            page=page,
            page_size=page_size,
            stage=stage,
            q=q,
            workflow_mode=workflow_mode,
        )
        return BriefsResponse(
            items=payload["items"],
            total=payload["total"],
            page=payload["page"],
            page_size=payload["page_size"],
            has_more=payload["has_more"],
            stage_counts=payload["stage_counts"],
            record_counts=payload["record_counts"],
        )

    @router.get("/api/admin/agent/workflows", response_model=AgentWorkflowsResponse)
    def list_agent_workflows():
        return AgentWorkflowsResponse(**list_agent_workflows_page_view())

    @router.post("/api/admin/briefs/daily-digest", response_model=BriefResponse)
    def create_daily_digest_brief(triggered_by: str = "dashboard"):
        try:
            return BriefResponse(**create_daily_digest_brief_page_action(triggered_by=triggered_by))
        except ValueError as exc:
            raise http_from_value_error(exc) from exc

    @router.get("/api/admin/agent/workflows/{workflow_session_id}", response_model=AgentWorkflowResponse)
    def get_agent_workflow(workflow_session_id: str):
        try:
            return AgentWorkflowResponse(**get_agent_workflow_page_view(workflow_session_id))
        except ValueError as exc:
            raise http_from_value_error(exc) from exc

    @router.post("/api/admin/agent/workflows/{workflow_session_id}/abandon", response_model=AgentWorkflowResponse)
    def abandon_agent_workflow(workflow_session_id: str, triggered_by: str = "dashboard"):
        try:
            return AgentWorkflowResponse(**abandon_agent_workflow_page_action(workflow_session_id, triggered_by=triggered_by))
        except ValueError as exc:
            raise http_from_value_error(exc) from exc

    @router.get("/api/admin/briefs/{brief_id}", response_model=BriefResponse)
    def get_brief(brief_id: str):
        try:
            return BriefResponse(**get_brief_page_view(brief_id))
        except ValueError as exc:
            raise http_from_value_error(exc) from exc

    @router.post("/api/admin/briefs/{brief_id}/wechat-draft", response_model=BriefResponse)
    def sync_brief_wechat_draft(brief_id: str, triggered_by: str = "dashboard"):
        try:
            return BriefResponse(**sync_brief_wechat_draft_page_action(brief_id, triggered_by=triggered_by))
        except ValueError as exc:
            raise http_from_value_error(exc) from exc

    @router.post("/api/admin/briefs/{brief_id}/copy-package", response_model=BriefCopyPackageResponse)
    def copy_brief_package(brief_id: str):
        try:
            return BriefCopyPackageResponse(**copy_brief_package_page_view(brief_id))
        except ValueError as exc:
            raise http_from_value_error(exc) from exc

    @router.delete("/api/admin/briefs/{brief_id}", response_model=DictOkResponse)
    def delete_brief(brief_id: str, remote: str = "auto"):
        try:
            return delete_brief_page_action(brief_id, remote=remote)
        except ValueError as exc:
            raise http_from_value_error(exc) from exc

    # Analytics route group
    router.include_router(analytics_router)

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
