from ...routes.common import get_store


def list_alerts():
    store = get_store()
    return store.list_intel_alerts(), store.list_intel_alert_history()


def list_alerts_page():
    items, history_items = list_alerts()
    return {
        "items": items,
        "history_items": history_items,
    }
