from ...routes.common import get_store


def watch_event(event_id: str):
    return get_store().watchlist_event(event_id)


def ignore_event(event_id: str):
    return get_store().ignore_event(event_id)
