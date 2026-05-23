from ...routes.common import get_store


def update_source(source_key: str, payload):
    return get_store().update_source(source_key, payload)


def create_source(payload):
    return get_store().create_source(payload)


def delete_source(source_key: str):
    return get_store().delete_source(source_key)


def sync_sources(triggered_by: str):
    return get_store().sync_sources(triggered_by=triggered_by)


def sync_source(source_key: str, triggered_by: str):
    return get_store().sync_source(source_key, triggered_by=triggered_by)
