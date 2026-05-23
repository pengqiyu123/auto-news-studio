from ...routes.common import get_store


def list_deep_dives():
    return get_store().list_event_deep_dives()


def get_deep_dive(event_id: str):
    return get_store().get_event_deep_dive(event_id)


def list_briefs(page: int, page_size: int, stage: str, q: str, workflow_mode: str):
    return get_store().list_briefs(page=page, page_size=page_size, stage=stage, q=q, workflow_mode=workflow_mode)


def list_agent_workflows():
    return get_store().list_agent_workflows()


def get_agent_workflow(workflow_session_id: str):
    return get_store().get_agent_workflow(workflow_session_id)


def get_brief(brief_id: str):
    return get_store().get_brief(brief_id)


def copy_brief_package(brief_id: str):
    return get_store().build_brief_copy_package(brief_id)


def list_deep_dives_page():
    return {"items": list_deep_dives()}


def get_deep_dive_page(event_id: str):
    return {"item": get_deep_dive(event_id)}


def list_briefs_page(page: int, page_size: int, stage: str, q: str, workflow_mode: str):
    items, total, safe_page, safe_page_size, has_more, stage_counts, record_counts = list_briefs(
        page=page,
        page_size=page_size,
        stage=stage,
        q=q,
        workflow_mode=workflow_mode,
    )
    return {
        "items": items,
        "total": total,
        "page": safe_page,
        "page_size": safe_page_size,
        "has_more": has_more,
        "stage_counts": stage_counts,
        "record_counts": record_counts,
    }


def list_agent_workflows_page():
    return {"items": list_agent_workflows()}


def get_agent_workflow_page(workflow_session_id: str):
    return {"item": get_agent_workflow(workflow_session_id)}


def get_brief_page(brief_id: str):
    return {"item": get_brief(brief_id)}


def copy_brief_package_page(brief_id: str):
    return {"markdown": copy_brief_package(brief_id)}
