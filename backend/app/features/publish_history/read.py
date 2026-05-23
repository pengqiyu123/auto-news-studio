from ...routes.common import get_store


def check_wechat_publish_history(triggered_by: str):
    return get_store().check_wechat_publish_history(triggered_by=triggered_by)


def check_wechat_publish_history_page(triggered_by: str):
    return {"item": check_wechat_publish_history(triggered_by=triggered_by)}
