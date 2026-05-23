from __future__ import annotations

from pathlib import Path

from .base import CONFIG_DIR, CONFIG_FILE, DATA_FILE
from .core import StoreCore

# 在模块级别延迟导入并构建类
def _build_studio_store():
    from ..store_mixins import AgentHtmlMixin, BriefsMixin, BrowserMixin, IntelMixin, RuntimeMixin, SettingsMixin, WeChatMixin

    class StudioStore(StoreCore, IntelMixin, BriefsMixin, BrowserMixin, RuntimeMixin, AgentHtmlMixin, SettingsMixin, WeChatMixin):
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
]