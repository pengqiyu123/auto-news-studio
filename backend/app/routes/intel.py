from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..content.text_quality import score_text_quality
from ..features.alerts.read import list_alerts_page as list_alerts_page_view
from ..features.events.read import get_event_page as get_event_page_view
from ..features.events.read import list_events_page as list_events_page_view
from ..features.events.write import ignore_event as ignore_event_action
from ..features.events.write import watch_event
from ..features.overview.read import (
    get_dashboard_lite_page as get_dashboard_lite_page_view,
)
from ..features.overview.read import (
    get_dashboard_page as get_dashboard_page_view,
)
from ..features.overview.read import (
    get_intel_snapshot_page as get_intel_snapshot_page_view,
)
from ..features.overview.read import (
    get_intel_summary_page as get_intel_summary_page_view,
)
from ..features.source_health.read import list_intel_sources_page as list_intel_sources_page_view
from ..features.source_health.read import list_sources_page as list_sources_page_view
from ..features.source_health.write import (
    create_source_page as create_source_page_action,
)
from ..features.source_health.write import (
    delete_source_page as delete_source_page_action,
)
from ..features.source_health.write import (
    sync_source as sync_source_action,
)
from ..features.source_health.write import (
    sync_sources as sync_sources_action,
)
from ..features.source_health.write import (
    update_source_page as update_source_page_action,
)
from ..features.stream.read import list_stream_page as list_stream_page_view
from ..features.watchlist.read import list_entity_watchlist_page as list_entity_watchlist_page_view
from ..features.watchlist.write import update_entity_watchlist as update_entity_watchlist_action
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
    SourcesResponse,
    SourceSyncResponse,
)


class TextQualityRequest(BaseModel):
    text: str
    max_banned: int = Field(default=3, ge=0)
    min_burstiness: float = Field(default=0.4, ge=0, le=2)


def build_intel_router() -> APIRouter:
    router = APIRouter()

    @router.get("/api/admin/dashboard")
    def get_dashboard():
        return get_dashboard_page_view()

    @router.get("/api/admin/dashboard/lite")
    def get_dashboard_lite():
        return get_dashboard_lite_page_view()

    @router.get("/api/admin/intel", response_model=IntelSnapshotResponse)
    def get_intel_snapshot():
        return IntelSnapshotResponse(**get_intel_snapshot_page_view())

    @router.get("/api/admin/intel/summary", response_model=IntelSummaryResponse)
    def get_intel_summary():
        return IntelSummaryResponse(**get_intel_summary_page_view())

    @router.get("/api/admin/intel/stream", response_model=DiscoveryItemsResponse)
    def get_intel_stream(
        page: int = 1,
        page_size: int = 50,
        q: str | None = None,
        time_range: str | None = None,
        platform: str | None = None,
        source: str | None = None,
        item_state: str | None = None,
        min_engagement: int | None = None,
        max_engagement: int | None = None,
    ):
        payload = list_stream_page_view(
            page=page,
            page_size=page_size,
            q=q,
            time_range=time_range,
            platform=platform,
            source=source,
            item_state=item_state,
            min_engagement=min_engagement,
            max_engagement=max_engagement,
        )
        return DiscoveryItemsResponse(
            items=payload["items"],
            total=payload["total"],
            page=payload["page"],
            page_size=payload["page_size"],
            has_more=payload["has_more"],
            available_platforms=payload["available_platforms"],
            available_sources=payload["available_sources"],
        )

    @router.get("/api/admin/intel/events", response_model=IntelEventsResponse)
    def get_intel_events(
        page: int = 1,
        page_size: int = 50,
        entity_id: str | None = None,
        event_id: str | None = None,
        sort_by: str | None = None,
        ignore_mode: str | None = None,
    ):
        payload = list_events_page_view(
            page=page,
            page_size=page_size,
            entity_id=entity_id,
            event_id=event_id,
            sort_by=sort_by,
            ignore_mode=ignore_mode,
        )
        return IntelEventsResponse(
            items=payload["items"],
            history_items=payload["history_items"],
            total=payload["total"],
            page=payload["page"],
            page_size=payload["page_size"],
            has_more=payload["has_more"],
        )

    @router.get("/api/admin/intel/events/{event_id}", response_model=IntelEventResponse)
    def get_intel_event(event_id: str):
        try:
            return IntelEventResponse(**get_event_page_view(event_id))
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get("/api/admin/intel/alerts", response_model=IntelAlertsResponse)
    def get_intel_alerts():
        payload = list_alerts_page_view()
        return IntelAlertsResponse(
            items=payload["items"],
            history_items=payload["history_items"],
        )

    @router.get("/api/admin/entities/watchlist", response_model=EntityWatchlistResponse)
    def get_entity_watchlist():
        return EntityWatchlistResponse(**list_entity_watchlist_page_view())

    @router.put("/api/admin/entities/watchlist", response_model=EntityWatchlistResponse)
    def put_entity_watchlist(payload: EntityWatchlistPayload):
        return EntityWatchlistResponse(items=update_entity_watchlist_action([item.model_dump() for item in payload.items]))

    @router.get("/api/admin/intel/sources", response_model=SourcesResponse)
    def get_intel_sources():
        return SourcesResponse(**list_intel_sources_page_view())

    @router.post("/api/admin/intel/watchlist/{event_id}", response_model=IntelEventResponse)
    def add_watchlist_event(event_id: str):
        try:
            return IntelEventResponse(item=watch_event(event_id))
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post("/api/admin/intel/ignore/{event_id}", response_model=IntelEventResponse)
    def ignore_event(event_id: str):
        try:
            return IntelEventResponse(item=ignore_event_action(event_id))
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get("/api/admin/sources", response_model=SourcesResponse)
    def list_sources():
        return SourcesResponse(**list_sources_page_view())

    @router.put("/api/admin/sources/{source_key}")
    def update_source(source_key: str, payload: SourceConnectorPayload):
        try:
            return update_source_page_action(source_key, payload)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post("/api/admin/sources")
    def create_source(payload: CreateSourcePayload):
        try:
            return create_source_page_action(payload)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.delete("/api/admin/sources/{source_key}")
    def delete_source(source_key: str):
        try:
            return delete_source_page_action(source_key)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post("/api/admin/sources/sync", response_model=SourceSyncResponse)
    def sync_sources(triggered_by: str = "dashboard"):
        return sync_sources_action(triggered_by=triggered_by)

    @router.post("/api/admin/sources/{source_key}/sync", response_model=SourceSyncResponse)
    def sync_source(source_key: str, triggered_by: str = "dashboard"):
        try:
            return sync_source_action(source_key, triggered_by=triggered_by)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post("/api/admin/agent/text-quality")
    def post_text_quality(payload: TextQualityRequest):
        report = score_text_quality(payload.text, max_banned=payload.max_banned, min_burstiness=payload.min_burstiness)
        return report

    return router
