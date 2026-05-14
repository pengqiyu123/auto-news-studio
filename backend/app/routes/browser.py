from __future__ import annotations

from fastapi import APIRouter

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
        items, total, safe_page, safe_page_size, has_more = get_store().list_publish_tasks(
            page=page,
            page_size=page_size,
        )
        return PublishTasksResponse(
            items=items,
            total=total,
            page=safe_page,
            page_size=safe_page_size,
            has_more=has_more,
        )

    @router.get("/api/admin/channels/wechat", response_model=WeChatChannelResponse)
    def get_wechat_channel():
        return WeChatChannelResponse(item=get_store().get_wechat_config())

    @router.put("/api/admin/channels/wechat")
    def update_wechat_channel(payload: ChannelConfigPayload):
        return {"item": get_store().update_wechat_config(payload)}

    @router.get("/api/admin/channels/douyin", response_model=DouyinChannelResponse)
    def get_douyin_channel():
        return DouyinChannelResponse(item=get_store().get_douyin_config())

    @router.get("/api/admin/browser/wechat/session", response_model=BrowserSessionResponse)
    def get_browser_session():
        return BrowserSessionResponse(item=get_store().get_browser_session())

    @router.put("/api/admin/browser/wechat/session")
    def update_browser_session(payload: BrowserSessionPayload):
        return {"item": get_store().update_browser_session(payload)}

    @router.post("/api/admin/browser/wechat/open-dashboard", response_model=BrowserSessionResponse)
    def open_browser_dashboard():
        return BrowserSessionResponse(item=get_store().open_browser_dashboard())

    @router.post("/api/admin/browser/wechat/check", response_model=BrowserSessionResponse)
    def check_browser_session():
        return BrowserSessionResponse(item=get_store().check_browser_session())

    @router.get("/api/admin/browser/douyin/session", response_model=BrowserSessionResponse)
    def get_douyin_browser_session():
        return BrowserSessionResponse(item=get_store().get_douyin_browser_session())

    @router.put("/api/admin/browser/douyin/session")
    def update_douyin_browser_session(payload: BrowserSessionPayload):
        return {"item": get_store().update_douyin_browser_session(payload)}

    @router.post("/api/admin/browser/douyin/open-dashboard", response_model=BrowserSessionResponse)
    def open_douyin_browser_dashboard():
        return BrowserSessionResponse(item=get_store().open_douyin_browser_dashboard())

    @router.post("/api/admin/browser/douyin/check", response_model=BrowserSessionResponse)
    def check_douyin_browser_session():
        return BrowserSessionResponse(item=get_store().check_douyin_browser_session())

    @router.post("/api/admin/browser/douyin/open-article-publish", response_model=BrowserSessionResponse)
    def open_douyin_article_publish():
        return BrowserSessionResponse(item=get_store().open_douyin_article_publish())

    @router.post("/api/admin/browser/douyin/inspect-article-structure", response_model=DouyinArticleStructureResponse)
    def inspect_douyin_article_structure():
        return DouyinArticleStructureResponse(item=get_store().inspect_douyin_article_structure())

    @router.post("/api/admin/browser/douyin/fill-article", response_model=BriefResponse)
    def fill_douyin_article(payload: DouyinArticleFillPayload):
        try:
            return BriefResponse(item=get_store().fill_douyin_article(payload))
        except ValueError as exc:
            raise http_from_value_error(exc) from exc

    @router.get("/api/admin/publish/backends", response_model=PublishBackendStatusResponse)
    def get_publish_backends():
        return PublishBackendStatusResponse(items=get_store().get_publish_backends())

    return router
