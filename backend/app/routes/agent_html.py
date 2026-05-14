from __future__ import annotations

from fastapi import APIRouter

from ..models import (
    AgentHtmlDiscoveryResponse,
    AgentHtmlDocumentResponse,
    AgentHtmlDocumentsResponse,
    AgentHtmlEventResponse,
    AgentHtmlEventsResponse,
    AgentHtmlMainlineBatchPayload,
    AgentHtmlRunBatchPayload,
    AgentHtmlRunResponse,
    AgentHtmlRunsResponse,
    AgentHtmlTargetCreatePayload,
    AgentHtmlTargetResponse,
    AgentHtmlTargetsResponse,
    AgentHtmlTargetUpdatePayload,
    SourceSyncResponse,
)
from .common import get_store, http_from_value_error


def build_agent_html_router() -> APIRouter:
    router = APIRouter()

    @router.post("/api/admin/agent-html/targets", response_model=AgentHtmlTargetResponse)
    def create_agent_html_target(payload: AgentHtmlTargetCreatePayload):
        try:
            return AgentHtmlTargetResponse(item=get_store().create_agent_html_target(payload))
        except ValueError as exc:
            raise http_from_value_error(exc) from exc

    @router.get("/api/admin/agent-html/targets", response_model=AgentHtmlTargetsResponse)
    def list_agent_html_targets():
        return AgentHtmlTargetsResponse(items=get_store().list_agent_html_targets())

    @router.patch("/api/admin/agent-html/targets/{target_id}", response_model=AgentHtmlTargetResponse)
    def update_agent_html_target(target_id: str, payload: AgentHtmlTargetUpdatePayload):
        try:
            return AgentHtmlTargetResponse(item=get_store().update_agent_html_target(target_id, payload))
        except ValueError as exc:
            raise http_from_value_error(exc) from exc

    @router.post("/api/admin/agent-html/targets/{target_id}/run", response_model=AgentHtmlRunResponse)
    def run_agent_html_target(target_id: str, triggered_by: str = "dashboard"):
        try:
            return AgentHtmlRunResponse(item=get_store().run_agent_html_target(target_id, triggered_by=triggered_by))
        except ValueError as exc:
            raise http_from_value_error(exc) from exc

    @router.post("/api/admin/agent-html/runs/batch", response_model=AgentHtmlRunsResponse)
    def run_agent_html_targets_batch(payload: AgentHtmlRunBatchPayload):
        try:
            return AgentHtmlRunsResponse(items=get_store().run_agent_html_targets_batch(payload.target_ids, triggered_by=payload.triggered_by))
        except ValueError as exc:
            raise http_from_value_error(exc) from exc

    @router.post("/api/admin/agent-html/mainline-sync", response_model=SourceSyncResponse)
    def sync_agent_html_into_mainline(payload: AgentHtmlMainlineBatchPayload):
        try:
            return get_store().sync_agent_html_into_mainline(payload.target_ids, triggered_by=payload.triggered_by)
        except ValueError as exc:
            raise http_from_value_error(exc) from exc

    @router.get("/api/admin/agent-html/runs", response_model=AgentHtmlRunsResponse)
    def list_agent_html_runs():
        return AgentHtmlRunsResponse(items=get_store().list_agent_html_runs())

    @router.get("/api/admin/agent-html/discovery", response_model=AgentHtmlDiscoveryResponse)
    def list_agent_html_discovery(page: int = 1, page_size: int = 50):
        items, total = get_store().list_agent_html_discovery(page=page, page_size=page_size)
        safe_page = max(1, page)
        safe_page_size = max(1, min(page_size, 200))
        return AgentHtmlDiscoveryResponse(
            items=items,
            total=total,
            page=safe_page,
            page_size=safe_page_size,
            has_more=(safe_page * safe_page_size) < total,
        )

    @router.get("/api/admin/agent-html/events", response_model=AgentHtmlEventsResponse)
    def list_agent_html_events(page: int = 1, page_size: int = 50):
        store = get_store()
        items, total = store.list_agent_html_events(page=page, page_size=page_size)
        safe_page = max(1, page)
        safe_page_size = max(1, min(page_size, 200))
        return AgentHtmlEventsResponse(
            items=items,
            history_items=store.list_agent_html_event_history(),
            total=total,
            page=safe_page,
            page_size=safe_page_size,
            has_more=(safe_page * safe_page_size) < total,
        )

    @router.get("/api/admin/agent-html/events/{event_id}", response_model=AgentHtmlEventResponse)
    def get_agent_html_event(event_id: str):
        try:
            return AgentHtmlEventResponse(item=get_store().get_agent_html_event(event_id))
        except ValueError as exc:
            raise http_from_value_error(exc) from exc

    @router.get("/api/admin/agent-html/documents", response_model=AgentHtmlDocumentsResponse)
    def list_agent_html_documents(page: int = 1, page_size: int = 50):
        items, total = get_store().list_agent_html_documents(page=page, page_size=page_size)
        safe_page = max(1, page)
        safe_page_size = max(1, min(page_size, 200))
        return AgentHtmlDocumentsResponse(
            items=items,
            total=total,
            page=safe_page,
            page_size=safe_page_size,
            has_more=(safe_page * safe_page_size) < total,
        )

    @router.get("/api/admin/agent-html/documents/{document_id}", response_model=AgentHtmlDocumentResponse)
    def get_agent_html_document(document_id: str):
        try:
            return AgentHtmlDocumentResponse(item=get_store().get_agent_html_document(document_id))
        except ValueError as exc:
            raise http_from_value_error(exc) from exc

    @router.post("/api/admin/agent-html/documents/{document_id}/reextract", response_model=AgentHtmlDocumentResponse)
    def reextract_agent_html_document(document_id: str, triggered_by: str = "dashboard"):
        try:
            return AgentHtmlDocumentResponse(item=get_store().reextract_agent_html_document(document_id, triggered_by=triggered_by))
        except ValueError as exc:
            raise http_from_value_error(exc) from exc

    return router
