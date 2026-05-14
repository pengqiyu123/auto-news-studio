from __future__ import annotations

from ._legacy import legacy_publishers


ARTIFACT_ROOT = legacy_publishers.ARTIFACT_ROOT
PROJECT_ROOT = legacy_publishers.PROJECT_ROOT
BROWSER_PROFILE_ROOT = legacy_publishers.BROWSER_PROFILE_ROOT
DEFAULT_BROWSER_LOCK_TIMEOUT_SECONDS = legacy_publishers.DEFAULT_BROWSER_LOCK_TIMEOUT_SECONDS
DEFAULT_EMPTY_CHECK_CONFIRMATIONS = legacy_publishers.DEFAULT_EMPTY_CHECK_CONFIRMATIONS
DEFAULT_BACKGROUND_POLL_INTERVAL_SECONDS = legacy_publishers.DEFAULT_BACKGROUND_POLL_INTERVAL_SECONDS
WINDOWS_BROWSER_PATHS = legacy_publishers.WINDOWS_BROWSER_PATHS
SELECTOR_PROFILES = legacy_publishers.SELECTOR_PROFILES

WechatBrowserManager = legacy_publishers.WechatBrowserManager
WECHAT_BROWSER_MANAGER = legacy_publishers.WECHAT_BROWSER_MANAGER
DOUYIN_BROWSER_MANAGER = legacy_publishers.DOUYIN_BROWSER_MANAGER

now_iso = legacy_publishers.now_iso
normalize_browser_name = legacy_publishers.normalize_browser_name
default_browser_profile_path = legacy_publishers.default_browser_profile_path
default_douyin_browser_profile_path = legacy_publishers.default_douyin_browser_profile_path
resolve_profile_path = legacy_publishers.resolve_profile_path
ensure_channel_defaults = legacy_publishers.ensure_channel_defaults
ensure_douyin_channel_defaults = legacy_publishers.ensure_douyin_channel_defaults
browser_channel_name = legacy_publishers.browser_channel_name
resolve_browser_executable = legacy_publishers.resolve_browser_executable
build_wechat_target_id = legacy_publishers.build_wechat_target_id
build_preview_url = legacy_publishers.build_preview_url
maybe_open_url = legacy_publishers.maybe_open_url
get_selector_profile = legacy_publishers.get_selector_profile
create_publish_task = legacy_publishers.create_publish_task
build_remote_draft_key = legacy_publishers.build_remote_draft_key
refresh_browser_session = legacy_publishers.refresh_browser_session
collect_backend_status = legacy_publishers.collect_backend_status
refresh_douyin_browser_session = legacy_publishers.refresh_douyin_browser_session
collect_douyin_backend_status = legacy_publishers.collect_douyin_backend_status
_write_debug_artifact = legacy_publishers._write_debug_artifact
_pick_selector = legacy_publishers._pick_selector
_pick_visible_locator = legacy_publishers._pick_visible_locator
_page_url = legacy_publishers._page_url
_is_page_closed = legacy_publishers._is_page_closed
_can_interact_with_page = legacy_publishers._can_interact_with_page
_count_context_pages = legacy_publishers._count_context_pages
_enforce_single_tab = legacy_publishers._enforce_single_tab

__all__ = [
    "ARTIFACT_ROOT",
    "PROJECT_ROOT",
    "BROWSER_PROFILE_ROOT",
    "DEFAULT_BROWSER_LOCK_TIMEOUT_SECONDS",
    "DEFAULT_EMPTY_CHECK_CONFIRMATIONS",
    "DEFAULT_BACKGROUND_POLL_INTERVAL_SECONDS",
    "WINDOWS_BROWSER_PATHS",
    "SELECTOR_PROFILES",
    "WechatBrowserManager",
    "WECHAT_BROWSER_MANAGER",
    "DOUYIN_BROWSER_MANAGER",
    "now_iso",
    "normalize_browser_name",
    "default_browser_profile_path",
    "default_douyin_browser_profile_path",
    "resolve_profile_path",
    "ensure_channel_defaults",
    "ensure_douyin_channel_defaults",
    "browser_channel_name",
    "resolve_browser_executable",
    "build_wechat_target_id",
    "build_preview_url",
    "maybe_open_url",
    "get_selector_profile",
    "create_publish_task",
    "build_remote_draft_key",
    "refresh_browser_session",
    "collect_backend_status",
    "refresh_douyin_browser_session",
    "collect_douyin_backend_status",
    "_write_debug_artifact",
    "_pick_selector",
    "_pick_visible_locator",
    "_page_url",
    "_is_page_closed",
    "_can_interact_with_page",
    "_count_context_pages",
    "_enforce_single_tab",
]
