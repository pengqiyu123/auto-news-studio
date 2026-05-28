from ...routes.common import get_store


def list_events(
    page: int,
    page_size: int,
    *,
    entity_id: str | None = None,
    event_id: str | None = None,
    sort_by: str | None = None,
    ignore_mode: str | None = None,
):
    store = get_store()
    return (
        store.list_intel_events(
            page=page,
            page_size=page_size,
            entity_id=entity_id,
            event_id=event_id,
            sort_by=sort_by,
            ignore_mode=ignore_mode,
        ),
        store.list_intel_event_history(),
    )


def get_event(event_id: str):
    return get_store().get_intel_event(event_id)


def list_events_page(
    page: int,
    page_size: int,
    *,
    entity_id: str | None = None,
    event_id: str | None = None,
    sort_by: str | None = None,
    ignore_mode: str | None = None,
):
    (items, total), history_items = list_events(
        page=page,
        page_size=page_size,
        entity_id=entity_id,
        event_id=event_id,
        sort_by=sort_by,
        ignore_mode=ignore_mode,
    )
    safe_page = max(1, page)
    safe_page_size = max(1, min(page_size, 200))
    return {
        "items": items,
        "history_items": history_items,
        "total": total,
        "page": safe_page,
        "page_size": safe_page_size,
        "has_more": (safe_page * safe_page_size) < total,
    }


def get_event_page(event_id: str):
    return {"item": get_event(event_id)}
