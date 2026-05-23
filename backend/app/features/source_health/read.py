from ...routes.common import get_store


def list_sources():
    return get_store().list_sources()


def list_intel_sources():
    return get_store().list_intel_sources()


def list_sources_page():
    return {"items": list_sources()}


def list_intel_sources_page():
    return {"items": list_intel_sources()}
