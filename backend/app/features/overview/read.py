from ...routes.common import get_store


def get_dashboard():
    return get_store().get_dashboard()


def get_dashboard_lite():
    return get_store().get_dashboard_lite()


def get_intel_snapshot():
    return get_store().get_intel_snapshot()


def get_intel_summary():
    return get_store().get_intel_summary()


def get_dashboard_page():
    return get_dashboard()


def get_dashboard_lite_page():
    return get_dashboard_lite()


def get_intel_snapshot_page():
    return {"item": get_intel_snapshot()}


def get_intel_summary_page():
    return {"item": get_intel_summary()}
