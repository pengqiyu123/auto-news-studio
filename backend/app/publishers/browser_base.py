from __future__ import annotations

import ctypes
import webbrowser
from pathlib import Path
from uuid import uuid4

from ..store.base import PROJECT_ROOT, RUNTIME_TEMP_DIR, now_iso

# WechatBrowserManager is imported lazily to avoid circular imports
# (browser_manager.py imports from browser_base.py at module level)


ARTIFACT_ROOT = RUNTIME_TEMP_DIR / "publish_artifacts"
PROJECT_ROOT = PROJECT_ROOT
BROWSER_PROFILE_ROOT = PROJECT_ROOT / "runtime" / "browser"
DEFAULT_BROWSER_LOCK_TIMEOUT_SECONDS = 60
DEFAULT_EMPTY_CHECK_CONFIRMATIONS = 3
DEFAULT_BACKGROUND_POLL_INTERVAL_SECONDS = 120
WINDOWS_BROWSER_PATHS = {
    "edge": [
        Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    ],
    "chrome": [
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
    ],
}

try:
    USER32 = ctypes.windll.user32
except Exception:  # pragma: no cover - non-Windows safety
    USER32 = None

SELECTOR_PROFILES: dict[str, dict[str, list[str] | str]] = {
    "wechat-mp-v1": {
        "logged_in": [
            ".weui-desktop-account__thumb",
            ".weui-desktop-layout__main",
            ".weui-desktop-side-menu",
        ],
        "new_article": [
            ".new-creation__menu-item:has(.new-creation__menu-title:text-is('文章'))",
            ".new-creation__menu-content:has(.new-creation__menu-title:text-is('文章'))",
            ".new-creation__menu-title:text-is('文章')",
        ],
        "draft_box": [
            "a#menu_10125[href*='action=list_card']",
            "a.weui-desktop-menu__link.menu_report[href*='action=list_card']",
            "a:has-text('草稿箱')",
            "div:has-text('草稿箱')",
            "a[href*='action=list_card']",
            "text=草稿箱",
            "a[href*='draft']",
            "text=草稿箱",
        ],
        "publish_history": [
            "a#menu_10126[href*='appmsgpublish']",
            "a.weui-desktop-menu__link.menu_report[href*='appmsgpublish']",
            "a:has-text('发表记录')",
            "div:has-text('发表记录')",
            "a[href*='appmsgpublish']",
            "text=发表记录",
        ],
        "analytics": [
            "a[href*='/misc/appmsganalysis'][title='内容分析']",
            "a[href*='appmsganalysis?action=report']",
            "a:has-text('内容分析')",
            "text=内容分析",
        ],
        "content_manage": [
            "span.weui-desktop-menu__link[title='内容管理']",
            "span.weui-desktop-menu__name:has-text('内容管理')",
            "a:has-text('内容管理')",
            "div:has-text('内容管理')",
            "text=内容管理",
        ],
        "title_input": [
            "div.ProseMirror[data-placeholder*='请在这里输入标题']",
            "div.ProseMirror[data-placeholder*='标题']",
            "textarea.js_article_title",
            "input[placeholder*='标题']",
            "textarea[placeholder*='标题']",
        ],
        "author_input": [
            "input.js_author",
            "input[placeholder*='作者']",
        ],
        "digest_input": [
            "textarea.js_desc",
            "textarea[placeholder*='摘要']",
        ],
        "editor": [
            "#edui1_iframeholder .mock-iframe-body .rich_media_content > div.ProseMirror[contenteditable='true']",
            "#edui1_iframeholder .mock-iframe-body .rich_media_content div.ProseMirror[contenteditable='true']",
            ".editor-v-root .mock-iframe-body .rich_media_content > div.ProseMirror[contenteditable='true']",
            "div.ProseMirror:not([data-placeholder*='请在这里输入标题']):not([data-placeholder*='标题'])",
            "div.ProseMirror:not([data-placeholder*='请在这里输入标题']):not([data-placeholder*='标题'])[style*='min-height']",
            ".rich_media_content .ProseMirror:not([data-placeholder*='请在这里输入标题']):not([data-placeholder*='标题'])",
            "div.ProseMirror:has(.editor_content_placeholder)",
            ".rich_media_content [contenteditable='true']",
            ".rich_media_content",
        ],
        "preview_button": [
            "button:has-text('预览')",
            "span:has-text('预览')",
            "text=预览",
        ],
        "save_draft_button": [
            "button:has-text('保存为草稿')",
            "span:has-text('保存为草稿')",
            "text=保存为草稿",
        ],
        "original_setting": [
            "#js_original",
            ".js_original_apply_cell",
            ".appmsg-editor__setting-group.origined__setting-group",
        ],
        "reward_setting": [
            "#js_reward_setting_area",
            ".reward__setting-group.js_reward_open_cell",
            ".reward__setting-group",
        ],
        "collection_setting": [
            "div.js_article_tags_label",
            "#js_article_tags_area .allow_click_opr",
            "#js_article_tags_area .js_article_tags_content",
            "#js_article_tags_area .lbl_content_desc",
        ],
        "collection_picker_input": [
            "span.weui-desktop-form__input-wrp:has(input.weui-desktop-form__input[placeholder='请选择合集'])",
            "span.weui-desktop-form__input-wrp:has(input[placeholder*='请选择合集'])",
            "input.weui-desktop-form__input[placeholder='请选择合集']",
            "input.weui-desktop-form__input[placeholder*='请选择合集']",
            ".weui-desktop-form__input-wrp input[placeholder*='合集']",
        ],
        "collection_ai_news_option": [
            "li.select-opt-li:has-text('AI新闻')",
            ".select-opt-li:has-text('AI新闻')",
            "li:has-text('AI新闻')",
        ],
        "claim_source_setting": [
            "div.js_claim_source_desc",
            "div.allow_click_opr.js_claim_source_desc",
            "label.claim_source_label_wrapper",
        ],
        "claim_source_personal_option": [
            "label.weui-desktop-form__check-label:has-text('个人观点，仅供参考')",
            ".weui-desktop-form__check-label:has-text('个人观点')",
        ],
        "primary_confirm_button": [
            "button.weui-desktop-btn.weui-desktop-btn_primary:has-text('确定')",
            "button.weui-desktop-btn_primary:has-text('确定')",
            "button:has-text('确定')",
        ],
        "option_confirm_button": [
            "button.weui-desktop-btn.weui-desktop-btn_primary:has-text('确认')",
            "button.weui-desktop-btn_primary:has-text('确认')",
            ".weui-desktop-btn_wrp button.weui-desktop-btn_primary:has-text('确认')",
            "button:has-text('确认')",
            "button.weui-desktop-btn.weui-desktop-btn_primary:has-text('确定')",
            "button.weui-desktop-btn_primary:has-text('确定')",
            "button:has-text('确定')",
        ],
        "cover_button": [
            "div.select-cover__btn.js_cover_btn_area.select-cover__mask",
            ".js_cover_btn_area.select-cover__mask",
            ".js_cover_btn_area",
            "span.js_share_type_none_image:has-text('拖拽或选择封面')",
        ],
        "ai_image_button": [
            "a.pop-opr__button.js_aiImage:has-text('AI 配图')",
            "a.js_aiImage",
            ".js_aiImage",
            "text=AI 配图",
        ],
        "ai_image_prompt": [
            "textarea#ai-image-prompt",
            "textarea[name='ai-image-prompt']",
            "textarea[placeholder*='请描述你想要创作的内容']",
        ],
        "ai_image_send_button": [
            "button.send-btn",
            ".send-btn",
        ],
        "ai_image_generated_tip": [
            "p.ai-image__tips:has-text('已为你生成图片')",
            ".ai-image__tips:has-text('已为你生成图片')",
        ],
        "ai_image_use_button": [
            ".ai-image-operation-group .ai-image-op-btn:has-text('使用')",
            ".ai-image-op-btn:has-text('使用')",
            "div:has-text('使用')",
        ],
        "cover_confirm_button": [
            ".weui-desktop-btn_wrp button.weui-desktop-btn_primary:has-text('确认')",
            "button.weui-desktop-btn_primary:has-text('确认')",
            "button:has-text('确认')",
        ],
        "article_publish_button": [
            "#js_send button.mass_send:has-text('发表')",
            "#js_send .send_wording:has-text('发表')",
            "#js_send button.mass_send",
            "button.mass_send:has-text('发表')",
        ],
        "publish_modal_button": [
            ".weui-desktop-popover__wrp .weui-desktop-btn_wrp[slot='target'] button.weui-desktop-btn_primary:has-text('发表')",
            ".weui-desktop-popover__wrp button.weui-desktop-btn_primary:has-text('发表')",
            ".weui-desktop-dialog__wrp button.weui-desktop-btn_primary:has-text('发表')",
            ".weui-dialog button.weui-desktop-btn_primary:has-text('发表')",
            "[role='dialog'] button.weui-desktop-btn_primary:has-text('发表')",
        ],
        "continue_publish_button": [
            "button.weui-desktop-btn_primary:has-text('继续发表')",
            ".weui-desktop-btn_wrp button:has-text('继续发表')",
            "button:has-text('继续发表')",
        ],
        "wechat_verify_qrcode": [
            ".dialog:has-text('微信验证') img.js_qrcode",
            ".safe_check img.js_qrcode",
            "img.js_qrcode[alt='微信二维码']",
            "img.js_qrcode",
        ],
        "publish_button": [
            "button:has-text('发表')",
            "span:has-text('发表')",
            "text=发表",
        ],
        "confirm_publish": [
            "button:has-text('确定')",
            ".weui-dialog__btn_primary",
            "text=确认",
        ],
    },
    "douyin-creator-v1": {
        "logged_in": [
            "text=发布文章",
            "text=发布作品",
            "text=内容管理",
            "text=创作者中心",
            "[href*='content/manage']",
            "[href*='creator-micro']",
        ],
        "publish_entry": [
            "text=发布文章",
            "div:has-text('发布文章')",
            ".title-HvY9Az:has-text('发布文章')",
            "text=发布作品",
            "text=去发布",
            "a[href*='upload']",
            "a[href*='publish']",
            "button:has-text('发布文章')",
            "button:has-text('发布作品')",
        ],
        "start_article": [
            "text=我要发文",
            "button:has-text('我要发文')",
            ".semi-button-content:has-text('我要发文')",
        ],
        "title_input": [
            "input[placeholder*='标题']",
            "div:has-text('文章标题') input",
            "textarea[placeholder*='标题']",
            "[contenteditable='true'][data-placeholder*='标题']",
            "div[contenteditable='true'][placeholder*='标题']",
        ],
        "summary_input": [
            "textarea[placeholder*='摘要']",
            "input[placeholder*='摘要']",
            "div:has-text('文章摘要') textarea",
            "div:has-text('文章摘要') input",
        ],
        "content_editor": [
            "div:has-text('文章正文') .ProseMirror[contenteditable='true']",
            "[contenteditable='true'][data-placeholder*='正文']",
            "[contenteditable='true'][placeholder*='正文']",
            ".ProseMirror[contenteditable='true']",
            "div[role='textbox'][contenteditable='true']",
            "[contenteditable='true']",
        ],
        "cover_upload": [
            "input[type='file']",
            "text=上传封面",
            "text=添加封面",
            "text=上传图片",
            "button:has-text('上传图片')",
        ],
        "images_panel": [
            "text=图片",
            "text=封面",
            "text=配图",
            "[class*='upload']",
            "[class*='image']",
        ],
        "submit_button": [
            "button:has-text('发布')",
            "button:has-text('提交')",
            "button:has-text('保存')",
            "button:has-text('预览')",
        ],
        "ai_illustration": [
            "text=AI 配图",
            "span:has-text('AI 配图')",
            "[class*='iconContainer']:has-text('AI 配图')",
            "[class*='mycard-info-text-icon']:has-text('AI 配图')",
        ],
    },
}


def normalize_browser_name(value: object | None) -> str:
    compact = str(value or "").strip().lower()
    if compact in {"edge", "chrome"}:
        return compact
    return "edge"


def default_browser_profile_path(browser_name: str = "edge") -> Path:
    compact = normalize_browser_name(browser_name)
    return BROWSER_PROFILE_ROOT / f"wechat-{compact}-profile"


def default_douyin_browser_profile_path(browser_name: str = "edge") -> Path:
    compact = normalize_browser_name(browser_name)
    return BROWSER_PROFILE_ROOT / f"douyin-{compact}-profile"


def resolve_profile_path(value: object | None, browser_name: object | None = None) -> Path:
    compact = str(value or "").strip()
    if compact:
        return Path(compact).expanduser()
    return default_browser_profile_path(normalize_browser_name(browser_name))


def ensure_channel_defaults(channel: dict[str, object]) -> dict[str, object]:
    next_channel = dict(channel)
    browser_name = normalize_browser_name(next_channel.get("browser_name"))
    next_channel["browser_name"] = browser_name
    next_channel["browser_profile_path"] = str(resolve_profile_path(next_channel.get("browser_profile_path"), browser_name))
    next_channel["publish_entry_url"] = str(next_channel.get("publish_entry_url") or "https://mp.weixin.qq.com/")
    next_channel["selectors_version"] = str(next_channel.get("selectors_version") or "wechat-mp-v1")
    next_channel["sidecar_url"] = str(next_channel.get("sidecar_url") or "http://127.0.0.1:8091")
    return next_channel


def ensure_douyin_channel_defaults(channel: dict[str, object]) -> dict[str, object]:
    next_channel = dict(channel)
    browser_name = normalize_browser_name(next_channel.get("browser_name"))
    next_channel["browser_name"] = browser_name
    profile_path = str(next_channel.get("browser_profile_path") or "").strip()
    next_channel["browser_profile_path"] = profile_path or str(default_douyin_browser_profile_path(browser_name))
    next_channel["publish_entry_url"] = str(next_channel.get("publish_entry_url") or "https://creator.douyin.com/")
    next_channel["selectors_version"] = str(next_channel.get("selectors_version") or "douyin-creator-v1")
    next_channel["sidecar_url"] = str(next_channel.get("sidecar_url") or "http://127.0.0.1:8091")
    return next_channel


def browser_channel_name(browser_name: str) -> str:
    return "msedge" if normalize_browser_name(browser_name) == "edge" else "chrome"


def resolve_browser_executable(browser_name: str) -> str | None:
    compact = normalize_browser_name(browser_name)
    for path in WINDOWS_BROWSER_PATHS.get(compact, []):
        if path.exists():
            return str(path)
    return None


def build_wechat_target_id(target_id: str) -> str:
    return f"wx_shadow_{target_id.replace('brief-', '')}"


def build_preview_url(target_id: str) -> str:
    return f"https://mp.weixin.qq.com/cgi-bin/home?t=home/index&draft={target_id.replace('brief-', '')}"


def maybe_open_url(url: str) -> None:
    try:  # pragma: no cover - depends on host shell
        webbrowser.open(url, new=2)
    except Exception:
        pass


def get_selector_profile(version: str) -> dict[str, list[str] | str]:
    return SELECTOR_PROFILES.get(version, SELECTOR_PROFILES["wechat-mp-v1"])


def create_publish_task(
    target_id: str,
    action: str,
    status: str,
    message: str,
    triggered_by: str,
    selector_profile: str,
    artifacts: list[str] | None = None,
    step_logs: list[str] | None = None,
) -> dict[str, object]:
    return {
        "id": f"task-{uuid4().hex[:8]}",
        "target_id": target_id,
        "action": action,
        "status": status,
        "stage": action,
        "message": message,
        "triggered_by": triggered_by,
        "created_at": now_iso(),
        "artifacts": artifacts or [],
        "step_logs": step_logs or [],
        "selector_profile": selector_profile,
    }


def build_remote_draft_key(
    title: str,
    url: str,
    appmsg_id: str | None = None,
    updated_at: str | None = None,
    occurrence: int | None = None,
) -> str:
    compact_url = str(url or "").strip()
    compact_id = str(appmsg_id or "").strip()
    if compact_id:
        return f"appmsg:{compact_id}"
    if compact_url:
        return f"url:{compact_url}"
    if occurrence is not None:
        return f"card:{occurrence}"
    return ""


def refresh_browser_session(channel: dict[str, object], current: dict[str, object]) -> dict[str, object]:
    channel = ensure_channel_defaults(channel)
    profile_path = resolve_profile_path(channel.get("browser_profile_path"), channel.get("browser_name"))
    selector_version = str(channel.get("selectors_version", "wechat-mp-v1"))
    entry_url = str(channel.get("publish_entry_url", "https://mp.weixin.qq.com/"))
    last_opened_url = str(current.get("last_opened_url") or "") or entry_url
    current_page = str(current.get("current_page") or current.get("last_opened_url") or "") or entry_url

    next_state = dict(current)
    next_state.update(
        {
            "browser_name": channel.get("browser_name", "edge"),
            "user_data_dir": str(profile_path),
            "logged_in": bool(current.get("logged_in")) and profile_path.exists() and profile_path.is_dir(),
            "last_checked_at": now_iso(),
            "last_error": None if profile_path.exists() else "浏览器用户目录尚未创建，请先打开公众号后台完成首次登录。",
            "selectors_version": selector_version,
            "last_selector_check": selector_version,
            "last_opened_url": last_opened_url,
            "current_page": current_page,
            "sidecar_health": "offline",
            "manager_alive": bool(current.get("manager_alive")),
            "window_state": str(current.get("window_state") or "unknown"),
            "resident_page": current.get("resident_page"),
            "busy": bool(current.get("busy")),
            "last_reset_reason": current.get("last_reset_reason"),
            "session_generation": int(current.get("session_generation") or 0),
            "last_action": current.get("last_action"),
            "last_action_phase": current.get("last_action_phase"),
            "is_session_level_error": bool(current.get("is_session_level_error")),
        }
    )
    if not profile_path.parent.exists():
        profile_path.parent.mkdir(parents=True, exist_ok=True)
    from .browser_manager import WECHAT_BROWSER_MANAGER
    next_state.update(WECHAT_BROWSER_MANAGER.manager_state())
    return next_state


def collect_backend_status(channel: dict[str, object], browser: dict[str, object]) -> list[dict[str, object]]:
    channel = ensure_channel_defaults(channel)
    profile_path = resolve_profile_path(channel.get("browser_profile_path"), channel.get("browser_name"))
    if browser.get("logged_in"):
        browser_detail = "已匹配浏览器 profile，公众号登录态可复用。"
    elif profile_path.exists():
        browser_detail = "已匹配浏览器 profile，等待扫码登录后再验证。"
    else:
        browser_detail = "浏览器 profile 尚未生成，请先完成配置。"
    selector_profile = str(channel.get("selectors_version", "wechat-mp-v1"))
    selector_detail = f"当前选择器配置 {selector_profile}，包含 {len(get_selector_profile(selector_profile)) - 1} 组动作锚点。"
    return [
        {
            "key": "browser",
            "label": "浏览器登录会话",
            "health": "healthy" if browser.get("logged_in") else "warning",
            "detail": browser_detail,
            "configured": bool(str(channel.get("browser_profile_path", ""))),
        },
        {
            "key": "selectors",
            "label": "页面选择器配置",
            "health": "healthy" if selector_profile in SELECTOR_PROFILES else "warning",
            "detail": selector_detail,
            "configured": True,
        },
    ]


def refresh_douyin_browser_session(channel: dict[str, object], current: dict[str, object]) -> dict[str, object]:
    channel = ensure_douyin_channel_defaults(channel)
    profile_path = Path(str(channel.get("browser_profile_path") or "")).expanduser()
    selector_version = str(channel.get("selectors_version", "douyin-creator-v1"))
    entry_url = str(channel.get("publish_entry_url", "https://creator.douyin.com/"))
    next_state = dict(current)
    next_state.update(
        {
            "platform": "douyin_creator",
            "browser_name": channel.get("browser_name", "edge"),
            "user_data_dir": str(profile_path),
            "logged_in": bool(current.get("logged_in")) and profile_path.exists() and profile_path.is_dir(),
            "last_checked_at": now_iso(),
            "last_error": None if profile_path.exists() else "浏览器用户目录尚未创建，请先打开抖音创作者中心完成首次登录。",
            "selectors_version": selector_version,
            "last_selector_check": selector_version,
            "last_opened_url": str(current.get("last_opened_url") or "") or entry_url,
            "current_page": str(current.get("current_page") or current.get("last_opened_url") or "") or entry_url,
            "sidecar_health": "offline",
            "manager_alive": False,
            "window_state": str(current.get("window_state") or "unknown"),
            "resident_page": current.get("resident_page"),
            "busy": False,
            "last_reset_reason": current.get("last_reset_reason"),
            "session_generation": int(current.get("session_generation") or 0),
            "last_action": current.get("last_action"),
            "last_action_phase": current.get("last_action_phase"),
            "is_session_level_error": bool(current.get("is_session_level_error")),
        }
    )
    if not profile_path.parent.exists():
        profile_path.parent.mkdir(parents=True, exist_ok=True)
    return next_state


def collect_douyin_backend_status(channel: dict[str, object], browser: dict[str, object]) -> list[dict[str, object]]:
    channel = ensure_douyin_channel_defaults(channel)
    profile_path = Path(str(channel.get("browser_profile_path") or "")).expanduser()
    if browser.get("logged_in"):
        browser_detail = "已匹配浏览器 profile，抖音创作者中心登录态可复用。"
    elif profile_path.exists():
        browser_detail = "已匹配浏览器 profile，等待登录抖音创作者中心后再验证。"
    else:
        browser_detail = "浏览器 profile 尚未生成，请先完成配置。"
    selector_profile = str(channel.get("selectors_version", "douyin-creator-v1"))
    selector_detail = f"当前选择器配置 {selector_profile}，包含 {len(get_selector_profile(selector_profile)) - 1} 组动作锚点。"
    return [
        {
            "key": "douyin-browser",
            "label": "抖音浏览器登录会话",
            "health": "healthy" if browser.get("logged_in") else "warning",
            "detail": browser_detail,
            "configured": bool(str(channel.get("browser_profile_path", ""))),
        },
        {
            "key": "douyin-selectors",
            "label": "抖音页面选择器配置",
            "health": "healthy" if selector_profile in SELECTOR_PROFILES else "warning",
            "detail": selector_detail,
            "configured": True,
        },
    ]


def _write_debug_artifact(target: Path, lines: list[str]) -> str:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(target)


def _pick_selector(page, selectors: list[str] | str, timeout: int = 2200) -> str | None:
    selector_list = selectors if isinstance(selectors, list) else [selectors]
    for selector in selector_list:
        try:
            locator = page.locator(str(selector))
            count = locator.count()
            if count <= 0:
                continue
            matched_visible = False
            for index in range(count):
                candidate = locator.nth(index)
                try:
                    candidate.wait_for(state="visible", timeout=timeout)
                    matched_visible = True
                    break
                except Exception:
                    continue
            if matched_visible:
                return str(selector)
            locator.first.wait_for(timeout=timeout)
            return str(selector)
        except Exception:
            continue
    return None


def _pick_visible_locator(page, selector: str, timeout: int = 2200):
    locator = page.locator(selector)
    count = locator.count()
    if count <= 0:
        return locator.first
    for index in range(count):
        candidate = locator.nth(index)
        try:
            candidate.wait_for(state="visible", timeout=timeout)
            return candidate
        except Exception:
            continue
    return locator.first


def _page_url(page) -> str:
    try:
        return str(getattr(page, "url", "") or "")
    except Exception:
        return ""


def _is_page_closed(page) -> bool:
    try:
        checker = getattr(page, "is_closed", None)
        if callable(checker):
            return bool(checker())
    except Exception:
        return False
    return bool(getattr(page, "closed", False))


def _count_context_pages(context) -> int:
    try:
        pages = list(getattr(context, "pages", []) or [])
    except Exception:
        return 0
    return sum(0 if _is_page_closed(page) else 1 for page in pages)


def _list_live_context_pages(context) -> list[object]:
    try:
        pages = list(getattr(context, "pages", []) or [])
    except Exception:
        return []
    return [page for page in pages if not _is_page_closed(page)]


def _can_interact_with_page(page) -> bool:
    if page is None or _is_page_closed(page):
        return False
    try:
        evaluator = getattr(page, "evaluate", None)
        if callable(evaluator):
            evaluator("() => document.readyState")
        else:
            _ = getattr(page, "url", "")
        return True
    except Exception:
        return False


def _enforce_single_tab(context, page, step_logs: list[str], *, phase: str, allow_recover: bool = False) -> None:
    pages = _list_live_context_pages(context)
    page_count = len(pages)
    step_logs.append(f"单标签页检查 phase={phase} page_count={page_count}")
    if page_count <= 1:
        return

    home_page = None
    for candidate in pages:
        candidate_url = _page_url(candidate)
        if "mp.weixin.qq.com" in candidate_url and "appmsg" not in candidate_url and "action=list_card" not in candidate_url:
            home_page = candidate
            break

    if allow_recover:
        keep_page = home_page or page
        closed_count = 0
        for candidate in pages:
            if candidate is keep_page:
                continue
            try:
                candidate.close()
                closed_count += 1
            except Exception:
                pass
        step_logs.append(f"单标签页恢复 phase={phase} closed_tabs={closed_count}")
        remaining = _count_context_pages(context)
        step_logs.append(f"单标签页恢复后 page_count={remaining}")
        if remaining <= 1:
            return

    raise RuntimeError(f"违反单标签页约束：检测到 {page_count} 个标签页。")


__all__ = [
    "ARTIFACT_ROOT",
    "PROJECT_ROOT",
    "BROWSER_PROFILE_ROOT",
    "DEFAULT_BROWSER_LOCK_TIMEOUT_SECONDS",
    "DEFAULT_EMPTY_CHECK_CONFIRMATIONS",
    "DEFAULT_BACKGROUND_POLL_INTERVAL_SECONDS",
    "WINDOWS_BROWSER_PATHS",
    "SELECTOR_PROFILES",
    "now_iso",
    "normalize_browser_name",
    "default_browser_profile_path",
    "default_douyin_browser_profile_path",
    "resolve_profile_path",
    "ensure_channel_defaults",
    "ensure_douyin_channel_defaults",
    "browser_channel_name",
    "resolve_browser_executable",
    "build_wechat_target_id",
    "build_preview_url",
    "maybe_open_url",
    "get_selector_profile",
    "create_publish_task",
    "build_remote_draft_key",
    "refresh_browser_session",
    "collect_backend_status",
    "refresh_douyin_browser_session",
    "collect_douyin_backend_status",
    "_write_debug_artifact",
    "_pick_selector",
    "_pick_visible_locator",
    "_page_url",
    "_is_page_closed",
    "_list_live_context_pages",
    "_can_interact_with_page",
    "_count_context_pages",
    "_enforce_single_tab",
]
