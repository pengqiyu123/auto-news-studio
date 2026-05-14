from __future__ import annotations

from ._legacy import legacy_publishers


_build_douyin_title = legacy_publishers._build_douyin_title
_build_douyin_summary = legacy_publishers._build_douyin_summary
launch_douyin_dashboard = legacy_publishers.launch_douyin_dashboard
inspect_douyin_session = legacy_publishers.inspect_douyin_session
open_douyin_article_publish = legacy_publishers.open_douyin_article_publish
inspect_douyin_article_structure = legacy_publishers.inspect_douyin_article_structure
fill_douyin_article_from_brief = legacy_publishers.fill_douyin_article_from_brief

__all__ = [
    "_build_douyin_title",
    "_build_douyin_summary",
    "launch_douyin_dashboard",
    "inspect_douyin_session",
    "open_douyin_article_publish",
    "inspect_douyin_article_structure",
    "fill_douyin_article_from_brief",
]
