from __future__ import annotations

from fastapi import APIRouter

from ..features.briefs.read import get_brief
from ..features.draft_box.read import list_publish_tasks_page
from ..features.logs.read import list_logs as list_logs_view
from ..features.settings.read import (
    get_browser_session as get_browser_session_view,
    get_douyin_browser_session as get_douyin_browser_session_view,
    get_douyin_channel as get_douyin_channel_view,
    get_wechat_channel as get_wechat_channel_view,
)
from ..features.settings.write import (
    check_browser_session as check_browser_session_action,
    check_douyin_browser_session as check_douyin_browser_session_action,
    fill_douyin_article as fill_douyin_article_action,
    inspect_douyin_article_structure as inspect_douyin_article_structure_action,
    open_browser_dashboard as open_browser_dashboard_action,
    open_douyin_article_publish as open_douyin_article_publish_action,
    open_douyin_browser_dashboard as open_douyin_browser_dashboard_action,
    update_browser_session as update_browser_session_action,
    update_douyin_browser_session as update_douyin_browser_session_action,
    update_wechat_channel as update_wechat_channel_action,
)
from ..models import (
    BriefResponse,
    BrowserSessionPayload,
    BrowserSessionResponse,
    ChannelConfigPayload,
    DouyinArticleFillPayload,
    DouyinArticleStructureResponse,
    DouyinChannelResponse,
    PublishBackendStatusResponse,
    PublishTasksResponse,
    WeChatChannelResponse,
)
from .common import get_store, http_from_value_error


def build_browser_router() -> APIRouter:
    router = APIRouter()

    @router.get("/api/admin/publish-tasks", response_model=PublishTasksResponse)
    def list_publish_tasks(page: int = 1, page_size: int = 50):
        payload = list_publish_tasks_page(page=page, page_size=page_size)
        return PublishTasksResponse(
            items=payload["items"],
            total=payload["total"],
            page=payload["page"],
            page_size=payload["page_size"],
            has_more=payload["has_more"],
        )

    @router.get("/api/admin/channels/wechat", response_model=WeChatChannelResponse)
    def get_wechat_channel():
        return WeChatChannelResponse(item=get_wechat_channel_view())

    @router.put("/api/admin/channels/wechat")
    def update_wechat_channel(payload: ChannelConfigPayload):
        return {"item": update_wechat_channel_action(payload)}

    @router.get("/api/admin/channels/douyin", response_model=DouyinChannelResponse)
    def get_douyin_channel():
        return DouyinChannelResponse(item=get_douyin_channel_view())

    @router.get("/api/admin/browser/wechat/session", response_model=BrowserSessionResponse)
    def get_browser_session():
        return BrowserSessionResponse(item=get_browser_session_view())

    @router.put("/api/admin/browser/wechat/session")
    def update_browser_session(payload: BrowserSessionPayload):
        return {"item": update_browser_session_action(payload)}

    @router.post("/api/admin/browser/wechat/open-dashboard", response_model=BrowserSessionResponse)
    def open_browser_dashboard():
        return BrowserSessionResponse(item=open_browser_dashboard_action())

    @router.post("/api/admin/browser/wechat/check", response_model=BrowserSessionResponse)
    def check_browser_session():
        return BrowserSessionResponse(item=check_browser_session_action())

    @router.get("/api/admin/browser/douyin/session", response_model=BrowserSessionResponse)
    def get_douyin_browser_session():
        return BrowserSessionResponse(item=get_douyin_browser_session_view())

    @router.put("/api/admin/browser/douyin/session")
    def update_douyin_browser_session(payload: BrowserSessionPayload):
        return {"item": update_douyin_browser_session_action(payload)}

    @router.post("/api/admin/browser/douyin/open-dashboard", response_model=BrowserSessionResponse)
    def open_douyin_browser_dashboard():
        return BrowserSessionResponse(item=open_douyin_browser_dashboard_action())

    @router.post("/api/admin/browser/douyin/check", response_model=BrowserSessionResponse)
    def check_douyin_browser_session():
        return BrowserSessionResponse(item=check_douyin_browser_session_action())

    @router.post("/api/admin/browser/douyin/open-article-publish", response_model=BrowserSessionResponse)
    def open_douyin_article_publish():
        return BrowserSessionResponse(item=open_douyin_article_publish_action())

    @router.post("/api/admin/browser/douyin/inspect-article-structure", response_model=DouyinArticleStructureResponse)
    def inspect_douyin_article_structure():
        return DouyinArticleStructureResponse(item=inspect_douyin_article_structure_action())

    @router.post("/api/admin/browser/douyin/fill-article", response_model=BriefResponse)
    def fill_douyin_article(payload: DouyinArticleFillPayload):
        try:
            return BriefResponse(item=fill_douyin_article_action(payload))
        except ValueError as exc:
            raise http_from_value_error(exc) from exc

    @router.get("/api/admin/publish/backends", response_model=PublishBackendStatusResponse)
    def get_publish_backends():
        return PublishBackendStatusResponse(items=get_store().get_publish_backends())

    return router
