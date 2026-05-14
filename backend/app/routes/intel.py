from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..models import (
    CreateSourcePayload,
    DiscoveryItemsResponse,
    EntityWatchlistPayload,
    EntityWatchlistResponse,
    IntelAlertsResponse,
    IntelEventResponse,
    IntelEventsResponse,
    IntelSnapshotResponse,
    IntelSummaryResponse,
    SourceConnectorPayload,
    SourceSyncResponse,
    SourcesResponse,
)
from .common import get_store


def build_intel_router() -> APIRouter:
    router = APIRouter()

    @router.get("/api/admin/dashboard")
    def get_dashboard():
        return get_store().get_dashboard()

    @router.get("/api/admin/intel", response_model=IntelSnapshotResponse)
    def get_intel_snapshot():
        return IntelSnapshotResponse(item=get_store().get_intel_snapshot())

    @router.get("/api/admin/intel/summary", response_model=IntelSummaryResponse)
    def get_intel_summary():
        return IntelSummaryResponse(item=get_store().get_intel_summary())

    @router.get("/api/admin/intel/stream", response_model=DiscoveryItemsResponse)
    def get_intel_stream(page: int = 1, page_size: int = 50):
        items, total = get_store().list_discovery_items(page=page, page_size=page_size)
        safe_page = max(1, page)
        safe_page_size = max(1, min(page_size, 200))
        return DiscoveryItemsResponse(
            items=items,
            total=total,
            page=safe_page,
            page_size=safe_page_size,
            has_more=(safe_page * safe_page_size) < total,
        )

    @router.get("/api/admin/intel/events", response_model=IntelEventsResponse)
    def get_intel_events(page: int = 1, page_size: int = 50):
        store = get_store()
        items, total = store.list_intel_events(page=page, page_size=page_size)
        safe_page = max(1, page)
        safe_page_size = max(1, min(page_size, 200))
        return IntelEventsResponse(
            items=items,
            history_items=store.list_intel_event_history(),
            total=total,
            page=safe_page,
            page_size=safe_page_size,
            has_more=(safe_page * safe_page_size) < total,
        )

    @router.get("/api/admin/intel/events/{event_id}", response_model=IntelEventResponse)
    def get_intel_event(event_id: str):
        try:
            return IntelEventResponse(item=get_store().get_intel_event(event_id))
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get("/api/admin/intel/alerts", response_model=IntelAlertsResponse)
    def get_intel_alerts():
        store = get_store()
        return IntelAlertsResponse(
            items=store.list_intel_alerts(),
            history_items=store.list_intel_alert_history(),
        )

    @router.get("/api/admin/entities/watchlist", response_model=EntityWatchlistResponse)
    def get_entity_watchlist():
        return EntityWatchlistResponse(items=get_store().list_entity_watchlist())

    @router.put("/api/admin/entities/watchlist", response_model=EntityWatchlistResponse)
    def put_entity_watchlist(payload: EntityWatchlistPayload):
        return EntityWatchlistResponse(items=get_store().update_entity_watchlist([item.model_dump() for item in payload.items]))

    @router.get("/api/admin/intel/sources", response_model=SourcesResponse)
    def get_intel_sources():
        return SourcesResponse(items=get_store().list_intel_sources())

    @router.post("/api/admin/intel/watchlist/{event_id}", response_model=IntelEventResponse)
    def add_watchlist_event(event_id: str):
        try:
            return IntelEventResponse(item=get_store().watchlist_event(event_id))
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post("/api/admin/intel/ignore/{event_id}", response_model=IntelEventResponse)
    def ignore_event(event_id: str):
        try:
            return IntelEventResponse(item=get_store().ignore_event(event_id))
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get("/api/admin/sources", response_model=SourcesResponse)
    def list_sources():
        return SourcesResponse(items=get_store().list_sources())

    @router.put("/api/admin/sources/{source_key}")
    def update_source(source_key: str, payload: SourceConnectorPayload):
        try:
            return {"item": get_store().update_source(source_key, payload)}
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post("/api/admin/sources")
    def create_source(payload: CreateSourcePayload):
        try:
            return {"item": get_store().create_source(payload)}
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.delete("/api/admin/sources/{source_key}")
    def delete_source(source_key: str):
        try:
            get_store().delete_source(source_key)
            return {"ok": True}
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post("/api/admin/sources/sync", response_model=SourceSyncResponse)
    def sync_sources(triggered_by: str = "dashboard"):
        return get_store().sync_sources(triggered_by=triggered_by)

    @router.post("/api/admin/sources/{source_key}/sync", response_model=SourceSyncResponse)
    def sync_source(source_key: str, triggered_by: str = "dashboard"):
        try:
            return get_store().sync_source(source_key, triggered_by=triggered_by)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    return router
