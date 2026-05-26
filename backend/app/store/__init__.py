from __future__ import annotations

from pathlib import Path

from .base import CONFIG_DIR, CONFIG_FILE, DATA_FILE
from .core import StoreCore
from ..content.briefing import (
    build_agent_article_writing_guide,
    build_prompt_package_markdown,
    build_rule_brief_payload,
)
from ..intel.deep_dive import canonicalize_url, fetch_and_extract_link, search_tavily
from ..models import AgentHtmlRun, AgentHtmlTargetCreatePayload

# 在模块级别延迟导入并构建类
def _build_studio_store():
    from ..store_mixins import (
        AgentHtmlMixin,
        BriefsMixin,
        BrowserMixin,
        DashboardMixin,
        DeliveryMixin,
        IntelMixin,
        LLMEnhanceMixin,
        RuntimeMixin,
        SettingsMixin,
        SourceSyncMixin,
        WeChatMixin,
    )

    class StudioStore(
        StoreCore,
        DashboardMixin,
        DeliveryMixin,
        LLMEnhanceMixin,
        SourceSyncMixin,
        IntelMixin,
        BriefsMixin,
        BrowserMixin,
        RuntimeMixin,
        AgentHtmlMixin,
        SettingsMixin,
        WeChatMixin,
    ):
        def __init__(self, data_file: Path | None = None):
            super().__init__(data_file=data_file)

    return StudioStore

# 延迟构建，仅在首次访问时
_StudioStore_cache = None

def StudioStore(data_file: Path | None = None):
    global _StudioStore_cache
    if _StudioStore_cache is None:
        _StudioStore_cache = _build_studio_store()
    return _StudioStore_cache(data_file=data_file)

# 导出类本身供类型检查
def get_studio_store_class():
    global _StudioStore_cache
    if _StudioStore_cache is None:
        _StudioStore_cache = _build_studio_store()
    return _StudioStore_cache

__all__ = [
    "StudioStore",
    "get_studio_store_class",
    "CONFIG_DIR",
    "CONFIG_FILE",
    "DATA_FILE",
    "AgentHtmlRun",
    "AgentHtmlTargetCreatePayload",
    "build_agent_article_writing_guide",
    "build_prompt_package_markdown",
    "build_rule_brief_payload",
    "canonicalize_url",
    "fetch_and_extract_link",
    "search_tavily",
]
