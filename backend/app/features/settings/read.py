from ...routes.common import get_store
from ...llm.cc_switch import get_cc_switch_db_path, read_cc_switch_providers


def get_wechat_channel():
    return get_store().get_wechat_config()


def get_douyin_channel():
    return get_store().get_douyin_config()


def get_browser_session():
    return get_store().get_browser_session()


def get_douyin_browser_session():
    return get_store().get_douyin_browser_session()


def get_system_update(force: bool):
    return get_store().get_app_update_info(force=force)


def get_settings():
    return get_store().get_settings()


def get_system_doctor():
    return get_store().system_doctor()


def list_reference_projects():
    return get_store().list_reference_projects()


def get_llm_config():
    return get_store().get_llm_config()


def get_llm_usage():
    return get_store().get_llm_usage()


def get_runtime_status():
    return get_store().get_runtime_status()


def get_runtime_plan():
    return get_store().get_runtime_plan()


def list_automation_modes():
    store = get_store()
    return store.get_current_automation_mode(), store.list_automation_modes()


def list_automation_profiles():
    store = get_store()
    return store.get_current_automation_profile(), store.list_automation_profiles()


def export_system_config():
    return get_store().export_config_bundle()


def export_system_backup():
    return get_store().export_backup_bundle()


def list_cc_switch_providers():
    db_path = get_cc_switch_db_path()
    providers = read_cc_switch_providers(db_path) if db_path else []
    masked = []
    for provider in providers:
        key = provider.get("api_key", "")
        masked.append(
            {
                **{name: value for name, value in provider.items() if name != "api_key"},
                "has_api_key": bool(key.strip()),
                "api_key_preview": f"{key[:6]}...{key[-4:]}" if len(key) > 10 else "****" if key else "",
            }
        )
    return {"providers": masked, "db_available": db_path is not None}


def get_automation_modes_page():
    current, items = list_automation_modes()
    return {"current": current, "items": items}


def get_automation_profiles_page():
    current, items = list_automation_profiles()
    return {"current": current, "items": items}
