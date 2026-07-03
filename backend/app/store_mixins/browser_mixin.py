from __future__ import annotations

from datetime import datetime
from typing import Any

from ..content.briefing import (
    build_douyin_article_markdown,
    build_douyin_summary,
    build_douyin_title,
    should_refresh_douyin_summary,
)
from ..models import (
    BriefItem,
    BrowserSessionPayload,
    BrowserSessionState,
    DouyinArticleFillPayload,
    DouyinArticleStructureSnapshot,
    DouyinChannelConfig,
)
from ..publishers import (
    create_publish_task,
    ensure_douyin_channel_defaults,
    fill_douyin_article_from_brief,
    inspect_douyin_article_structure,
    inspect_douyin_session,
    launch_douyin_dashboard,
)
from ..publishers import (
    open_douyin_article_publish as open_douyin_article_publish_page,
)
from ..store.base import UTC, parse_time


class BrowserMixin:
    def get_douyin_config(self) -> DouyinChannelConfig:
        config = self._upgrade_user_settings(self._read_config())
        return DouyinChannelConfig(**ensure_douyin_channel_defaults(config.get("douyin", {})))

    def get_douyin_browser_session(self) -> BrowserSessionState:
        state = self._read_live()
        browser = self._refresh_douyin_browser_session(state)
        self._write(state)
        return BrowserSessionState(**browser)

    def update_douyin_browser_session(self, payload: BrowserSessionPayload) -> BrowserSessionState:
        state = self._upgrade_state(self._read())
        state["channels"]["douyin"]["browser_name"] = payload.browser_name
        state["channels"]["douyin"]["browser_profile_path"] = payload.user_data_dir
        state["channels"]["douyin"] = ensure_douyin_channel_defaults(state["channels"]["douyin"])
        config = self._read_config()
        config.setdefault("douyin", {})
        config["douyin"]["browser_name"] = state["channels"]["douyin"]["browser_name"]
        config["douyin"]["browser_profile_path"] = state["channels"]["douyin"]["browser_profile_path"]
        browser = self._refresh_douyin_browser_session(state)
        self._append_log(state, "info", "browser", "已刷新抖音浏览器会话配置。")
        self._write_config(self._upgrade_user_settings(config))
        self._write(state)
        return BrowserSessionState(**browser)

    def open_douyin_browser_dashboard(self) -> BrowserSessionState:
        state = self._upgrade_state(self._read())
        browser = self._refresh_douyin_browser_session(state)
        browser, artifacts, step_logs = launch_douyin_dashboard(state["channels"]["douyin"], browser)
        state["browser"]["douyin"] = browser
        self._append_log(
            state,
            "info",
            "browser",
            "已打开抖音创作者中心窗口。",
            stream="business_event",
            actor="dashboard",
            detail=" | ".join(step_logs[:3]),
        )
        state["publish_tasks"].insert(
            0,
            create_publish_task(
                "session-douyin",
                "open_douyin_dashboard",
                "completed" if not browser.get("last_error") else "failed",
                "已打开抖音创作者中心窗口。",
                "dashboard",
                str(state["channels"]["douyin"]["selectors_version"]),
                artifacts=artifacts,
                step_logs=step_logs,
            ),
        )
        self._write(state)
        return BrowserSessionState(**browser)

    def check_douyin_browser_session(self) -> BrowserSessionState:
        state = self._upgrade_state(self._read())
        browser = self._refresh_douyin_browser_session(state)
        browser, artifacts, step_logs = inspect_douyin_session(state["channels"]["douyin"], browser)
        state["browser"]["douyin"] = browser
        self._append_log(
            state,
            "success" if browser.get("logged_in") else "warning",
            "browser",
            "已完成抖音浏览器会话检查。" if browser.get("logged_in") else "抖音浏览器会话未通过检查。",
            stream="business_event",
            actor="dashboard",
            detail=" | ".join(step_logs[-2:]),
        )
        state["publish_tasks"].insert(
            0,
            create_publish_task(
                "session-douyin",
                "check_douyin_browser",
                "completed" if browser.get("logged_in") else "blocked",
                "已完成抖音浏览器会话检查。",
                "dashboard",
                str(state["channels"]["douyin"]["selectors_version"]),
                artifacts=artifacts,
                step_logs=step_logs,
            ),
        )
        self._write(state)
        return BrowserSessionState(**browser)

    def open_douyin_article_publish(self) -> BrowserSessionState:
        state = self._upgrade_state(self._read())
        browser = self._refresh_douyin_browser_session(state)
        browser, artifacts, step_logs = open_douyin_article_publish_page(state["channels"]["douyin"], browser)
        state["browser"]["douyin"] = browser
        self._append_log(
            state,
            "success" if not browser.get("last_error") else "warning",
            "browser",
            "已打开抖音发布文章页。" if not browser.get("last_error") else "打开抖音发布文章页失败。",
            stream="business_event",
            actor="dashboard",
            detail=" | ".join(step_logs[-2:]),
        )
        state["publish_tasks"].insert(
            0,
            create_publish_task(
                "session-douyin",
                "open_douyin_article_publish",
                "completed" if not browser.get("last_error") else "failed",
                "已打开抖音发布文章页。",
                "dashboard",
                str(state["channels"]["douyin"]["selectors_version"]),
                artifacts=artifacts,
                step_logs=step_logs,
            ),
        )
        self._write(state)
        return BrowserSessionState(**browser)

    def inspect_douyin_article_structure(self) -> DouyinArticleStructureSnapshot:
        state = self._upgrade_state(self._read())
        browser = self._refresh_douyin_browser_session(state)
        browser, snapshot, artifacts, step_logs = inspect_douyin_article_structure(state["channels"]["douyin"], browser)
        state["browser"]["douyin"] = browser
        self._append_log(
            state,
            "success" if not browser.get("last_error") else "warning",
            "browser",
            "已探测抖音文章发布页结构。" if not browser.get("last_error") else "探测抖音文章发布页结构失败。",
            stream="business_event",
            actor="dashboard",
            detail=" | ".join(step_logs[-2:]),
        )
        state["publish_tasks"].insert(
            0,
            create_publish_task(
                "session-douyin",
                "inspect_douyin_article_structure",
                "completed" if not browser.get("last_error") else "failed",
                "已探测抖音文章发布页结构。",
                "dashboard",
                str(state["channels"]["douyin"]["selectors_version"]),
                artifacts=artifacts,
                step_logs=step_logs,
            ),
        )
        self._write(state)
        return DouyinArticleStructureSnapshot(**snapshot)

    def fill_douyin_article(self, payload: DouyinArticleFillPayload) -> BriefItem:
        state = self._upgrade_state(self._read())
        browser = self._refresh_douyin_browser_session(state)

        brief: dict[str, Any] | None = None
        brief_id = str(payload.brief_id or "").strip()
        if brief_id:
            brief = self._find_brief(state, brief_id)
        else:
            briefs = [item for item in state.get("briefs", []) if isinstance(item, dict)]
            briefs.sort(key=lambda item: parse_time(item.get("updated_at")) or datetime.min.replace(tzinfo=UTC), reverse=True)
            if briefs:
                brief = briefs[0]
        if not brief:
            raise ValueError("未找到可用于抖音填充的本地简报。")

        douyin_title = str(brief.get("douyin_title") or "").strip()
        douyin_summary = str(brief.get("douyin_summary") or "").strip()
        douyin_markdown = str(brief.get("douyin_markdown") or "").strip()
        is_douyin_daily_news = (
            str(brief.get("workflow_mode") or "traditional") == "traditional"
            and (
                str(brief.get("title") or "").startswith("今日5条科技要闻")
                or douyin_title.startswith("今日5条科技要闻")
            )
        )
        if not douyin_title:
            douyin_title = build_douyin_title(str(brief.get("title") or ""))
            brief["douyin_title"] = douyin_title
        source_summary = str(
            brief.get("summary")
            or brief.get("one_line")
            or brief.get("why_it_matters")
            or douyin_summary
            or ""
        )
        regenerated_summary = build_douyin_summary(
            source_summary,
            douyin_title or str(brief.get("title") or ""),
        )
        if should_refresh_douyin_summary(
            douyin_summary,
            douyin_title or str(brief.get("title") or ""),
        ):
            douyin_summary = regenerated_summary or douyin_summary
        if douyin_summary != str(brief.get("douyin_summary") or "").strip():
            douyin_summary = regenerated_summary
            brief["douyin_summary"] = douyin_summary
        if not douyin_markdown:
            douyin_markdown = build_douyin_article_markdown(
                title=douyin_title or str(brief.get("title") or ""),
                summary=douyin_summary,
                article_markdown=str(brief.get("wechat_markdown") or ""),
                one_line=str(brief.get("one_line") or ""),
                why_it_matters=str(brief.get("why_it_matters") or ""),
                facts=list(brief.get("facts", [])),
                quotes=list(brief.get("quotes", [])),
                timeline=list(brief.get("timeline", [])),
                source_links=list(brief.get("source_links", [])),
            )
            brief["douyin_markdown"] = douyin_markdown
        if is_douyin_daily_news and not (
            douyin_title.startswith("今日5条科技要闻")
            and "朋友们，今天咱们来盘一盘" in douyin_markdown
            and "最后一条" in douyin_markdown
            and "评论区" in douyin_markdown
        ):
            raise ValueError("抖音今日要闻必须使用固定 5 条口播短讯格式。")

        browser_payload = {
            "id": str(brief.get("id") or ""),
            "title": douyin_title or str(brief.get("title") or ""),
            "summary": douyin_summary or str(brief.get("one_line") or ""),
            "markdown": douyin_markdown or str(brief.get("wechat_markdown") or ""),
        }
        browser, artifacts, step_logs = fill_douyin_article_from_brief(
            state["channels"]["douyin"], browser, browser_payload
        )
        state["browser"]["douyin"] = browser
        self._append_log(
            state,
            "success" if not browser.get("last_error") else "warning",
            "browser",
            "已填充抖音文章页内容。" if not browser.get("last_error") else "填充抖音文章页内容失败。",
            stream="business_event",
            actor="dashboard",
            detail=" | ".join(step_logs[-3:]),
        )
        state["publish_tasks"].insert(
            0,
            create_publish_task(
                str(brief.get("id") or "session-douyin"),
                "fill_douyin_article",
                "completed" if not browser.get("last_error") else "failed",
                "已填充抖音文章页内容。",
                "dashboard",
                str(state["channels"]["douyin"]["selectors_version"]),
                artifacts=artifacts,
                step_logs=step_logs,
            ),
        )
        self._write(state)
        return BriefItem(**brief)
