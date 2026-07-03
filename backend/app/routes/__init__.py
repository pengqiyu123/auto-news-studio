from .agent_html import build_agent_html_router
from .analysis import build_analysis_router
from .base import build_base_router
from .browser import build_browser_router
from .content import build_content_router
from .intel import build_intel_router
from .runtime import build_runtime_router
from .settings import build_settings_router
from .wechat import build_wechat_router

__all__ = [
    "build_agent_html_router",
    "build_analysis_router",
    "build_base_router",
    "build_browser_router",
    "build_content_router",
    "build_intel_router",
    "build_runtime_router",
    "build_settings_router",
    "build_wechat_router",
]
