from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..features.draft_box.read import (
    check_wechat_draft_box_page as check_wechat_draft_box_page_view,
    get_wechat_mapping_page as get_wechat_mapping_page_view,
    refresh_wechat_mapping_page as refresh_wechat_mapping_page_view,
)
from ..features.draft_box.write import delete_wechat_remote_draft_page as delete_wechat_remote_draft_page_action
from ..features.publish_history.read import check_wechat_publish_history_page as check_wechat_publish_history_page_view
from ..models import (
    BrowserSessionResponse,
    DictOkResponse,
    WeChatDraftSyncCheckResponse,
    WeChatAnalyticsDomResponse,
    WeChatEditorDomResponse,
    WeChatMappingResponse,
    WeChatPublishHistoryResponse,
)
from .common import get_store, http_from_value_error


def build_wechat_router() -> APIRouter:
    router = APIRouter()

    @router.post("/api/admin/browser/wechat/check-drafts", response_model=WeChatDraftSyncCheckResponse)
    def check_wechat_draft_box(triggered_by: str = "dashboard"):
        try:
            return WeChatDraftSyncCheckResponse(**check_wechat_draft_box_page_view(triggered_by=triggered_by))
        except ValueError as exc:
            raise http_from_value_error(exc) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"微信草稿箱检查失败：{exc}") from exc

    @router.post("/api/admin/browser/wechat/check-publish-history", response_model=WeChatPublishHistoryResponse)
    def check_wechat_publish_history(triggered_by: str = "dashboard"):
        try:
            return WeChatPublishHistoryResponse(**check_wechat_publish_history_page_view(triggered_by=triggered_by))
        except ValueError as exc:
            raise http_from_value_error(exc) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"微信发表记录检查失败：{exc}") from exc

    @router.post("/api/admin/browser/wechat/inspect-editor-dom", response_model=WeChatEditorDomResponse)
    def inspect_editor_dom():
        try:
            return WeChatEditorDomResponse(item=get_store().inspect_wechat_editor_dom())
        except ValueError as exc:
            raise http_from_value_error(exc) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"微信编辑页源码导出失败：{exc}") from exc

    @router.post("/api/admin/browser/wechat/inspect-analytics-dom", response_model=WeChatAnalyticsDomResponse)
    def inspect_analytics_dom():
        try:
            return WeChatAnalyticsDomResponse(item=get_store().inspect_wechat_analytics_dom())
        except ValueError as exc:
            raise http_from_value_error(exc) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"微信数据分析页源码导出失败：{exc}") from exc

    @router.post("/api/admin/browser/wechat/open-editor-debug", response_model=BrowserSessionResponse)
    def open_editor_debug():
        try:
            return BrowserSessionResponse(item=get_store().open_wechat_editor_debug())
        except ValueError as exc:
            raise http_from_value_error(exc) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"打开微信编辑页失败：{exc}") from exc

    @router.post("/api/admin/browser/wechat/fill-author-only", response_model=BrowserSessionResponse)
    def fill_author_only():
        try:
            return BrowserSessionResponse(item=get_store().fill_wechat_author_only())
        except ValueError as exc:
            raise http_from_value_error(exc) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"填写微信作者失败：{exc}") from exc

    @router.post("/api/admin/browser/wechat/test-publish-settings-only", response_model=BrowserSessionResponse)
    def test_publish_settings_only():
        try:
            return BrowserSessionResponse(item=get_store().test_wechat_publish_settings_only())
        except ValueError as exc:
            raise http_from_value_error(exc) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"微信后半段流程测试失败：{exc}") from exc

    @router.get("/api/admin/wechat/mapping", response_model=WeChatMappingResponse)
    def get_wechat_mapping():
        return WeChatMappingResponse(**get_wechat_mapping_page_view())

    @router.post("/api/admin/wechat/mapping/refresh", response_model=WeChatMappingResponse)
    def refresh_wechat_mapping(triggered_by: str = "dashboard"):
        try:
            return WeChatMappingResponse(**refresh_wechat_mapping_page_view(triggered_by=triggered_by))
        except ValueError as exc:
            raise http_from_value_error(exc) from exc

    @router.delete("/api/admin/wechat/remote-drafts/{remote_id}", response_model=DictOkResponse)
    def delete_wechat_remote_draft(remote_id: str):
        try:
            return delete_wechat_remote_draft_page_action(remote_id)
        except ValueError as exc:
            raise http_from_value_error(exc) from exc

    return router
