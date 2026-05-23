from ...routes.common import get_store


def list_stream(page: int, page_size: int):
    return get_store().list_discovery_items(page=page, page_size=page_size)


def list_stream_page(page: int, page_size: int):
    items, total = list_stream(page=page, page_size=page_size)
    safe_page = max(1, page)
    safe_page_size = max(1, min(page_size, 200))
    return {
        "items": items,
        "total": total,
        "page": safe_page,
        "page_size": safe_page_size,
        "has_more": (safe_page * safe_page_size) < total,
    }
