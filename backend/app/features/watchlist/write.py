from ...routes.common import get_store


def update_entity_watchlist(items):
    return get_store().update_entity_watchlist(items)
