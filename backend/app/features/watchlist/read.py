from ...routes.common import get_store


def list_entity_watchlist():
    return get_store().list_entity_watchlist()


def list_entity_watchlist_page():
    return {"items": list_entity_watchlist()}
