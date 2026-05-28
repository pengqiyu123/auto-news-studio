from ...routes.common import get_store


def list_stream(
    page: int,
    page_size: int,
    *,
    q: str | None = None,
    time_range: str | None = None,
    platform: str | None = None,
    source: str | None = None,
    item_state: str | None = None,
    min_engagement: int | None = None,
    max_engagement: int | None = None,
):
    return get_store().list_discovery_items(
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


def list_stream_page(
    page: int,
    page_size: int,
    *,
    q: str | None = None,
    time_range: str | None = None,
    platform: str | None = None,
    source: str | None = None,
    item_state: str | None = None,
    min_engagement: int | None = None,
    max_engagement: int | None = None,
):
    items, total, available_platforms, available_sources = list_stream(
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
    safe_page = max(1, page)
    safe_page_size = max(1, min(page_size, 200))
    return {
        "items": items,
        "total": total,
        "page": safe_page,
        "page_size": safe_page_size,
        "has_more": (safe_page * safe_page_size) < total,
        "available_platforms": available_platforms,
        "available_sources": available_sources,
    }
