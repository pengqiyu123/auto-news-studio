from ...routes.common import get_store


def check_wechat_draft_box(triggered_by: str):
    return get_store().check_wechat_draft_box(triggered_by=triggered_by)


def get_wechat_mapping():
    return get_store().get_wechat_mapping()


def refresh_wechat_mapping(triggered_by: str):
    return get_store().refresh_wechat_mapping(triggered_by=triggered_by)


def check_wechat_draft_box_page(triggered_by: str):
    return {"item": check_wechat_draft_box(triggered_by=triggered_by)}


def get_wechat_mapping_page():
    return {"item": get_wechat_mapping()}


def refresh_wechat_mapping_page(triggered_by: str):
    return {"item": refresh_wechat_mapping(triggered_by=triggered_by)}


def list_publish_tasks_page(page: int, page_size: int):
    items, total, safe_page, safe_page_size, has_more = get_store().list_publish_tasks(
        page=page,
        page_size=page_size,
    )
    return {
        "items": items,
        "total": total,
        "page": safe_page,
        "page_size": safe_page_size,
        "has_more": has_more,
    }
