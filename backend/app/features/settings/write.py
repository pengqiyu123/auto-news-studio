import ctypes
import subprocess
from pathlib import Path
import winreg

from ...routes.common import get_store
from ...cc_switch_bridge import get_cc_switch_db_path, read_cc_switch_providers


def update_wechat_channel(payload):
    return get_store().update_wechat_config(payload)


def update_browser_session(payload):
    return get_store().update_browser_session(payload)


def open_browser_dashboard():
    return get_store().open_browser_dashboard()


def check_browser_session():
    return get_store().check_browser_session()


def update_douyin_browser_session(payload):
    return get_store().update_douyin_browser_session(payload)


def open_douyin_browser_dashboard():
    return get_store().open_douyin_browser_dashboard()


def check_douyin_browser_session():
    return get_store().check_douyin_browser_session()


def open_douyin_article_publish():
    return get_store().open_douyin_article_publish()


def inspect_douyin_article_structure():
    return get_store().inspect_douyin_article_structure()


def fill_douyin_article(payload):
    return get_store().fill_douyin_article(payload)


def dismiss_system_update(payload):
    return get_store().dismiss_app_update(payload.version)


def update_settings(payload):
    return get_store().update_settings(payload)


def update_llm_config(payload):
    return get_store().update_llm_config(payload)


def test_llm_provider(provider_key: str):
    return get_store().test_llm_provider(provider_key)


def import_cc_switch_profiles(selected):
    return get_store().import_cc_switch_profiles(selected)


def update_runtime_plan(payload):
    return get_store().update_runtime_plan(payload)


def start_runtime():
    return get_store().start_runtime()


def stop_runtime():
    return get_store().stop_runtime()


def run_runtime_intent(intent: str):
    return get_store().run_runtime_intent(intent)


def set_current_automation_mode(mode: str):
    store = get_store()
    current = store.set_current_automation_mode(mode)
    return current, store.list_automation_modes()


def update_automation_profile(mode: str, payload):
    store = get_store()
    store.update_automation_profile(mode, payload)
    return store.get_current_automation_profile(), store.list_automation_profiles()


def open_cc_switch():
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            key = winreg.OpenKey(hive, r"Software\Microsoft\Windows\CurrentVersion\Uninstall")
            for index in range(winreg.QueryInfoKey(key)[0]):
                subkey_name = winreg.EnumKey(key, index)
                try:
                    with winreg.OpenKey(key, subkey_name) as subkey:
                        name = winreg.QueryValueEx(subkey, "DisplayName")[0] or ""
                        if "cc switch" in name.lower():
                            location = winreg.QueryValueEx(subkey, "InstallLocation")[0]
                            if location:
                                executable = Path(location) / "cc-switch.exe"
                                if executable.exists():
                                    subprocess.Popen(
                                        [str(executable)],
                                        creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
                                    )
                                    return {"ok": True}
                except (OSError, FileNotFoundError):
                    pass
            winreg.CloseKey(key)
        except (OSError, FileNotFoundError):
            pass

    desktop = Path.home() / "Desktop"
    for shortcut in desktop.glob("*CC*Switch*"):
        if shortcut.suffix == ".lnk":
            ctypes.windll.shell32.ShellExecuteW(None, "open", str(shortcut), None, None, 1)
            return {"ok": True}

    raise ValueError("未找到 CC-Switch，请确认已安装")


def dismiss_system_update_version(version: str):
    return get_store().dismiss_app_update(version)


def import_cc_switch_provider_ids(provider_ids: list[str]):
    db_path = get_cc_switch_db_path()
    if not db_path:
        raise ValueError("未找到 CC-Switch 数据库，请确认 CC-Switch 已安装")
    all_providers = read_cc_switch_providers(db_path)
    selected = [provider for provider in all_providers if provider.get("id") in provider_ids]
    if not selected:
        raise ValueError("未找到选中的 provider")
    return import_cc_switch_profiles(selected)


def set_current_automation_mode_page(mode: str):
    current, items = set_current_automation_mode(mode)
    return {"current": current, "items": items}


def update_automation_profile_page(mode: str, payload):
    current, items = update_automation_profile(mode, payload)
    return {"current": current, "items": items}
