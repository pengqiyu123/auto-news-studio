from __future__ import annotations

from pathlib import Path

from .briefing import build_agent_article_writing_guide, build_prompt_package_markdown, build_rule_brief_payload
from .deep_dive import canonicalize_url, fetch_and_extract_link, search_tavily
from .models import AgentHtmlRun, AgentHtmlTargetCreatePayload
from .store_base import CONFIG_DIR, CONFIG_FILE, DATA_FILE
from .store_core import StoreCore
from .store_mixins import AgentHtmlMixin, BriefsMixin, BrowserMixin, IntelMixin, RuntimeMixin, SettingsMixin, WeChatMixin


class StudioStore(StoreCore, IntelMixin, BriefsMixin, BrowserMixin, RuntimeMixin, AgentHtmlMixin, SettingsMixin, WeChatMixin):
    def __init__(self, data_file: Path | None = None):
        super().__init__(data_file=data_file)


__all__ = [
    "StudioStore",
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
