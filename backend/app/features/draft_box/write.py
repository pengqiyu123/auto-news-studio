from ...routes.common import get_store


def delete_wechat_remote_draft(remote_id: str):
    return get_store().delete_wechat_remote_draft(remote_id)


def delete_wechat_remote_draft_page(remote_id: str):
    return delete_wechat_remote_draft(remote_id)
