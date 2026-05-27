from ...routes.common import get_store


def create_event_deep_dive(event_id: str, force: bool, triggered_by: str):
    return get_store().create_event_deep_dive(event_id, force=force, triggered_by=triggered_by)


def create_brief_from_event(event_id: str, triggered_by: str):
    return get_store().create_brief_from_event(event_id, triggered_by=triggered_by)


def create_daily_digest_brief(triggered_by: str):
    return get_store().create_daily_digest_brief(triggered_by=triggered_by)


def create_agent_article(payload):
    return get_store().create_agent_article(payload)


def abandon_agent_workflow(workflow_session_id: str, triggered_by: str):
    return get_store().abandon_agent_workflow(workflow_session_id, triggered_by=triggered_by)


def sync_brief_wechat_draft(brief_id: str, triggered_by: str):
    return get_store().sync_brief_wechat_draft(brief_id, triggered_by=triggered_by)


def delete_brief(brief_id: str, remote: str):
    return get_store().delete_brief(brief_id, remote=remote)


def create_event_deep_dive_page(event_id: str, force: bool, triggered_by: str):
    return {"item": create_event_deep_dive(event_id, force=force, triggered_by=triggered_by)}


def create_brief_from_event_page(event_id: str, triggered_by: str):
    return {"item": create_brief_from_event(event_id, triggered_by=triggered_by)}


def create_daily_digest_brief_page(triggered_by: str):
    return {"item": create_daily_digest_brief(triggered_by=triggered_by)}


def create_agent_article_page(payload):
    return {"item": create_agent_article(payload)}


def abandon_agent_workflow_page(workflow_session_id: str, triggered_by: str):
    return {"item": abandon_agent_workflow(workflow_session_id, triggered_by=triggered_by)}


def sync_brief_wechat_draft_page(brief_id: str, triggered_by: str):
    return {"item": sync_brief_wechat_draft(brief_id, triggered_by=triggered_by)}


def delete_brief_page(brief_id: str, remote: str):
    return delete_brief(brief_id, remote=remote)
