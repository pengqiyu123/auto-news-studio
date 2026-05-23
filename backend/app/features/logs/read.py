from ...routes.common import get_store


def list_logs(page: int, page_size: int, level: str, q: str):
    return get_store().list_logs(page=page, page_size=page_size, level=level, q=q)


def list_logs_page(page: int, page_size: int, level: str, q: str):
    items, total, safe_page, safe_page_size, has_more = list_logs(
        page=page,
        page_size=page_size,
        level=level,
        q=q,
    )
    return {
        "items": items,
        "total": total,
        "page": safe_page,
        "page_size": safe_page_size,
        "has_more": has_more,
    }
