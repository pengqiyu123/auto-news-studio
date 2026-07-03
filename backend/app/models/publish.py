"""Publish/browser-related Pydantic models for Auto News Studio.

Extracted from models.py to reduce file size and improve domain grouping.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# Literal types that are primarily used by publish/browser models.
# Duplicated here to avoid circular imports; models.py re-exports these.
BackendHealth = Literal["healthy", "warning", "offline"]
PublishTaskStatus = Literal["pending", "running", "completed", "failed", "blocked"]


class PublishTask(BaseModel):
    id: str
    target_id: str
    action: str
    status: PublishTaskStatus
    stage: str
    message: str
    triggered_by: str
    created_at: str
    artifacts: list[str] = Field(default_factory=list)
    step_logs: list[str] = Field(default_factory=list)
    selector_profile: str = "wechat-mp-v1"


class BrowserSessionState(BaseModel):
    platform: Literal["wechat_mp", "douyin_creator"] = "wechat_mp"
    browser_name: str = "edge"
    user_data_dir: str = ""
    logged_in: bool = False
    last_checked_at: str | None = None
    last_opened_url: str | None = None
    last_error: str | None = None
    selectors_version: str = "wechat-mp-v1"
    last_screenshot: str | None = None
    last_selector_check: str | None = None
    current_page: str | None = None
    sidecar_health: BackendHealth = "offline"
    manager_alive: bool = False
    window_state: Literal["restored", "minimized", "unknown"] | None = "unknown"
    resident_page: str | None = None
    busy: bool = False
    last_reset_reason: str | None = None
    session_generation: int = 0
    last_action: str | None = None
    last_action_phase: str | None = None
    is_session_level_error: bool = False
    last_draft_check: WeChatDraftSyncCheckResult | None = None
    last_analytics_overview: WeChatAnalyticsOverview | None = None
    last_publish_history_check: WeChatPublishHistorySnapshot | None = None


class BrowserSessionPayload(BaseModel):
    browser_name: str
    user_data_dir: str


class WeChatRemoteDraftItem(BaseModel):
    title: str = ""
    url: str = ""
    appmsg_id: str | None = None
    updated_at: str | None = None
    remote_key: str | None = None


class WeChatDraftSyncCheckResult(BaseModel):
    checked_at: str
    remote_count: int = 0
    matched_count: int = 0
    missing_count: int = 0
    items: list[WeChatRemoteDraftItem] = Field(default_factory=list)
    message: str = ""
    check_ok: bool = True


class WeChatDraftSyncCheckResponse(BaseModel):
    item: WeChatDraftSyncCheckResult


class WeChatPublishRecordItem(BaseModel):
    title: str = ""
    url: str = ""
    appmsg_id: str | None = None
    published_at: str | None = None
    remote_key: str | None = None
    read_count: int = 0
    like_count: int = 0
    share_count: int = 0
    recommend_count: int = 0
    comment_count: int = 0
    highlight_count: int = 0
    tip_amount: str = "0.00"
    reprint_count: int = 0
    thumbnail: str = ""


class WeChatArticleMetrics(BaseModel):
    appmsg_id: str | None = None
    title: str = ""
    read_count: int = 0
    like_count: int = 0
    share_count: int = 0
    recommend_count: int = 0
    comment_count: int = 0
    highlight_count: int = 0
    tip_amount: str = "0.00"
    reprint_count: int = 0
    fetched_at: str = ""


class WeChatAnalyticsOverview(BaseModel):
    total_users: int = 0
    yesterday_reads: int = 0
    yesterday_shares: int = 0
    yesterday_new_follows: int = 0
    stats_window_label: str = ""
    fetched_at: str = ""
    avatar_url: str = ""
    account_name: str = ""
    original_count: int = 0


class WeChatPublishHistorySnapshot(BaseModel):
    checked_at: str
    record_count: int = 0
    items: list[WeChatPublishRecordItem] = Field(default_factory=list)
    overview: WeChatAnalyticsOverview | None = None
    message: str = ""
    check_ok: bool = True


class WeChatPublishHistoryResponse(BaseModel):
    item: WeChatPublishHistorySnapshot


class WeChatEditorDomField(BaseModel):
    key: str
    label: str
    found: bool = False
    visible: bool = False
    selector: str | None = None
    count: int = 0
    sample_text: str = ""
    sample_html: str = ""


class WeChatEditorDomSnapshot(BaseModel):
    checked_at: str
    url: str = ""
    page_title: str = ""
    body_excerpt: str = ""
    message: str = ""
    items: list[WeChatEditorDomField] = Field(default_factory=list)
    artifacts: list[str] = Field(default_factory=list)


class WeChatEditorDomResponse(BaseModel):
    item: WeChatEditorDomSnapshot


class WeChatAnalyticsDomSnapshot(BaseModel):
    checked_at: str
    url: str = ""
    page_title: str = ""
    body_excerpt: str = ""
    message: str = ""
    items: list[WeChatEditorDomField] = Field(default_factory=list)
    artifacts: list[str] = Field(default_factory=list)


class WeChatAnalyticsDomResponse(BaseModel):
    item: WeChatAnalyticsDomSnapshot


class DouyinArticleStructureField(BaseModel):
    key: str
    label: str
    found: bool = False
    visible: bool = False
    selector: str | None = None
    count: int = 0
    sample_text: str = ""
    sample_html: str = ""


class DouyinArticleStructureSnapshot(BaseModel):
    checked_at: str
    url: str = ""
    page_title: str = ""
    body_excerpt: str = ""
    message: str = ""
    items: list[DouyinArticleStructureField] = Field(default_factory=list)
    artifacts: list[str] = Field(default_factory=list)


class DouyinArticleStructureResponse(BaseModel):
    item: DouyinArticleStructureSnapshot


class DouyinArticleFillPayload(BaseModel):
    brief_id: str | None = None


class WeChatMappingStatus(str):
    pass


class WeChatMappingRow(BaseModel):
    remote_title: str = ""
    remote_key: str | None = None
    remote_appmsg_id: str | None = None
    remote_url: str = ""
    remote_updated_at: str | None = None
    local_brief_id: str | None = None
    local_brief_title: str | None = None
    local_stage: Literal["prepared", "synced", "failed"] | None = None
    mapping_status: str = "unresolved"


class WeChatMappingSnapshot(BaseModel):
    checked_at: str | None = None
    remote_count: int = 0
    matched_count: int = 0
    missing_count: int = 0
    message: str = ""
    items: list[WeChatRemoteDraftItem] = Field(default_factory=list)
    mapping_rows: list[WeChatMappingRow] = Field(default_factory=list)


class WeChatMappingResponse(BaseModel):
    item: WeChatMappingSnapshot


class PublishBackendStatus(BaseModel):
    key: str
    label: str
    health: BackendHealth
    detail: str
    configured: bool


class PublishBackendStatusResponse(BaseModel):
    items: list[PublishBackendStatus]


class WeChatChannelConfig(BaseModel):
    app_id: str = ""
    app_secret_masked: str = ""
    author: str = "Auto News Studio"
    default_cover_strategy: str = "auto"
    default_digest_strategy: str = "balanced"
    draft_mode: bool = True
    preview_enabled: bool = True
    auto_send_window: str = "09:00-10:00"
    risk_keywords: list[str] = Field(default_factory=list)
    browser_name: str = "edge"
    browser_profile_path: str = ""
    publish_entry_url: str = "https://mp.weixin.qq.com/"
    selectors_version: str = "wechat-mp-v1"
    sidecar_url: str = "http://127.0.0.1:8091"


class DouyinChannelConfig(BaseModel):
    browser_name: str = "edge"
    browser_profile_path: str = ""
    publish_entry_url: str = "https://creator.douyin.com/"
    selectors_version: str = "douyin-creator-v1"
    sidecar_url: str = "http://127.0.0.1:8091"


class ChannelConfigPayload(BaseModel):
    app_id: str
    app_secret_masked: str
    author: str
    default_cover_strategy: str
    default_digest_strategy: str
    draft_mode: bool
    preview_enabled: bool
    auto_send_window: str
    risk_keywords: list[str]
    browser_name: str
    browser_profile_path: str
    publish_entry_url: str
    selectors_version: str
    sidecar_url: str


class BrowserSessionResponse(BaseModel):
    item: BrowserSessionState


class WeChatChannelResponse(BaseModel):
    item: WeChatChannelConfig


class DouyinChannelResponse(BaseModel):
    item: DouyinChannelConfig


class PublishTasksResponse(BaseModel):
    items: list[PublishTask]
    total: int = 0
    page: int = 1
    page_size: int = 50
    has_more: bool = False
