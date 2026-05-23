from ...routes.common import get_store


def list_events(page: int, page_size: int):
    store = get_store()
    return store.list_intel_events(page=page, page_size=page_size), store.list_intel_event_history()


def get_event(event_id: str):
    return get_store().get_intel_event(event_id)


def list_events_page(page: int, page_size: int):
    (items, total), history_items = list_events(page=page, page_size=page_size)
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
