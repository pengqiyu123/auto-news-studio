from __future__ import annotations

from ._legacy import legacy_publishers


_plain_text_from_markdown = legacy_publishers._plain_text_from_markdown
extract_wechat_appmsg_id = legacy_publishers.extract_wechat_appmsg_id
delete_wechat_remote_draft = legacy_publishers.delete_wechat_remote_draft
inspect_wechat_draft_box = legacy_publishers.inspect_wechat_draft_box
inspect_wechat_editor_dom = legacy_publishers.inspect_wechat_editor_dom
inspect_wechat_publish_history = legacy_publishers.inspect_wechat_publish_history
launch_wechat_dashboard = legacy_publishers.launch_wechat_dashboard
inspect_wechat_session = legacy_publishers.inspect_wechat_session
open_wechat_editor_debug = legacy_publishers.open_wechat_editor_debug
fill_wechat_author_only = legacy_publishers.fill_wechat_author_only
test_wechat_publish_settings_only = legacy_publishers.test_wechat_publish_settings_only
run_browser_action = legacy_publishers.run_browser_action
_wait_for_wechat_editor_in_current_page = legacy_publishers._wait_for_wechat_editor_in_current_page
_locate_editor_page_with_retry = legacy_publishers._locate_editor_page_with_retry
_converge_context_to_target = legacy_publishers._converge_context_to_target
_apply_wechat_publish_settings = legacy_publishers._apply_wechat_publish_settings
_fill_wechat_editor = legacy_publishers._fill_wechat_editor
_clamp_author = legacy_publishers._clamp_author

__all__ = [
    "_plain_text_from_markdown",
    "_apply_wechat_publish_settings",
    "_fill_wechat_editor",
    "_clamp_author",
    "_converge_context_to_target",
    "_locate_editor_page_with_retry",
    "extract_wechat_appmsg_id",
    "delete_wechat_remote_draft",
    "inspect_wechat_draft_box",
    "inspect_wechat_editor_dom",
    "inspect_wechat_publish_history",
    "launch_wechat_dashboard",
    "inspect_wechat_session",
    "open_wechat_editor_debug",
    "fill_wechat_author_only",
    "test_wechat_publish_settings_only",
    "run_browser_action",
    "_wait_for_wechat_editor_in_current_page",
]
