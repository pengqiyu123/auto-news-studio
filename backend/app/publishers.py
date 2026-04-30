from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import subprocess
from urllib.parse import parse_qs, urlparse
import webbrowser
from uuid import uuid4


UTC = timezone.utc
ARTIFACT_ROOT = Path(__file__).resolve().parent.parent / "data" / "artifacts"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
BROWSER_PROFILE_ROOT = PROJECT_ROOT / "runtime" / "browser"
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

SELECTOR_PROFILES: dict[str, dict[str, list[str] | str]] = {
    "wechat-mp-v1": {
        "logged_in": [
            ".weui-desktop-account__thumb",
            ".weui-desktop-layout__main",
            ".weui-desktop-side-menu",
        ],
        "new_article": [
            "div.new-creation__menu-item:has-text('文章')",
            "text=文章",
            "a[href*='appmsg']",
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
        "content_manage": [
            "span.weui-desktop-menu__link[title='内容管理']",
            "span.weui-desktop-menu__name:has-text('内容管理')",
            "a:has-text('内容管理')",
            "div:has-text('内容管理')",
            "text=内容管理",
        ],
        "title_input": [
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
            ".ProseMirror",
            ".rich_media_content [contenteditable='true']",
            "[contenteditable='true']",
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
    }
}


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def normalize_browser_name(value: object | None) -> str:
    compact = str(value or "").strip().lower()
    if compact in {"edge", "chrome"}:
        return compact
    return "edge"


def default_browser_profile_path(browser_name: str = "edge") -> Path:
    compact = normalize_browser_name(browser_name)
    return BROWSER_PROFILE_ROOT / f"wechat-{compact}-profile"


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


def browser_channel_name(browser_name: str) -> str:
    return "msedge" if normalize_browser_name(browser_name) == "edge" else "chrome"


def resolve_browser_executable(browser_name: str) -> str | None:
    compact = normalize_browser_name(browser_name)
    for path in WINDOWS_BROWSER_PATHS.get(compact, []):
        if path.exists():
            return str(path)
    return None


def build_wechat_draft_id(draft_id: str) -> str:
    return f"wx_shadow_{draft_id.replace('draft-', '')}"


def build_preview_url(draft_id: str) -> str:
    return f"https://mp.weixin.qq.com/cgi-bin/home?t=home/index&draft={draft_id.replace('draft-', '')}"


def maybe_open_url(url: str) -> None:
    try:  # pragma: no cover - depends on host shell
        webbrowser.open(url, new=2)
    except Exception:
        pass


def get_selector_profile(version: str) -> dict[str, list[str] | str]:
    return SELECTOR_PROFILES.get(version, SELECTOR_PROFILES["wechat-mp-v1"])


def create_publish_task(
    draft_id: str,
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
        "draft_id": draft_id,
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
        }
    )
    if not profile_path.parent.exists():
        profile_path.parent.mkdir(parents=True, exist_ok=True)
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


def _write_debug_artifact(target: Path, lines: list[str]) -> str:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(target)


def _pick_selector(page, selectors: list[str] | str, timeout: int = 2200) -> str | None:
    selector_list = selectors if isinstance(selectors, list) else [selectors]
    for selector in selector_list:
        try:
            page.locator(str(selector)).first.wait_for(timeout=timeout)
            return str(selector)
        except Exception:
            continue
    return None


def _plain_text_from_markdown(markdown: str) -> str:
    lines: list[str] = []
    for raw in markdown.splitlines():
        line = raw.strip()
        if not line:
            if lines and lines[-1] != "":
                lines.append("")
            continue
        if line.startswith("#"):
            line = line.lstrip("#").strip()
        if line.startswith(("- ", "* ")):
            line = f"• {line[2:].strip()}"
        lines.append(line)
    text = "\n".join(lines).strip()
    return text[:12000]


def _clamp_author(author: str) -> str:
    compact = author.strip()
    if not compact:
        return ""
    return compact[:8]


def _fill_wechat_editor(page, draft: dict[str, object], channel: dict[str, object], selector_profile: dict[str, list[str] | str], step_logs: list[str]) -> None:
    title_selector = _pick_selector(page, selector_profile.get("title_input", []))
    author_selector = _pick_selector(page, selector_profile.get("author_input", []))
    digest_selector = _pick_selector(page, selector_profile.get("digest_input", []))
    editor_selector = _pick_selector(page, selector_profile.get("editor", []), timeout=4000)
    if not title_selector or not editor_selector:
        raise RuntimeError("未定位到标题框或正文编辑区。")

    title = str(draft.get("title", "")).strip()[:64]
    author = _clamp_author(str(channel.get("author") or ""))
    digest = str(draft.get("summary") or "").strip()[:120]
    body_text = _plain_text_from_markdown(str(draft.get("markdown") or ""))

    page.locator(title_selector).first.fill(title)
    step_logs.append(f"已填充标题 selector={title_selector}")
    if author_selector and author:
        page.locator(author_selector).first.fill(author)
        step_logs.append(f"已填充作者 selector={author_selector}")
    if digest_selector and digest:
        page.locator(digest_selector).first.fill(digest)
        step_logs.append(f"已填充摘要 selector={digest_selector}")
    editor = page.locator(editor_selector).first
    editor.click()
    try:
        editor.fill(body_text)
    except Exception:
        page.evaluate(
            """({ selector, value }) => {
                const node = document.querySelector(selector);
                if (!node) return;
                node.focus();
                node.textContent = value;
                node.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: value }));
            }""",
            {"selector": editor_selector, "value": body_text},
        )
    step_logs.append(f"已填充正文 selector={editor_selector}")


def _locate_editor_page(context, fallback_page, timeout_ms: int = 12000):
    deadline = datetime.now(UTC).timestamp() + (timeout_ms / 1000)
    candidate = fallback_page
    while datetime.now(UTC).timestamp() < deadline:
        for page in context.pages:
            if "appmsg" in page.url or "media/appmsg_edit" in page.url:
                try:
                    page.wait_for_load_state("domcontentloaded", timeout=1500)
                except Exception:
                    pass
                return page
            candidate = page
        try:
            fallback_page.wait_for_timeout(500)
        except Exception:
            break
    return candidate


def extract_wechat_appmsg_id(url: str | None) -> str | None:
    if not url:
        return None
    try:
        values = parse_qs(urlparse(url).query).get("appmsgid", [])
    except Exception:
        return None
    for value in values:
        compact = str(value).strip()
        if compact:
            return compact
    return None


def resolve_editor_url(draft: dict[str, object], browser_state: dict[str, object], entry_url: str) -> str:
    candidates = [
        draft.get("wechat_editor_url"),
        browser_state.get("last_opened_url"),
        browser_state.get("current_page"),
        draft.get("preview_url"),
        entry_url,
    ]
    for candidate in candidates:
        compact = str(candidate or "").strip()
        if "appmsg" in compact:
            return compact
    return str(entry_url)


def detect_editor_blockers(page) -> list[str]:
    try:
        body_text = page.locator("body").inner_text(timeout=2500)
    except Exception:
        return []
    text = str(body_text or "")
    blockers: list[str] = []
    if "必须插入一张图片" in text:
        blockers.append("微信校验未通过：正文必须至少插入一张图片。")
    if "请在这里输入标题" in text:
        blockers.append("微信校验未通过：标题仍为空。")
    return blockers


def _scrape_wechat_draft_items(page) -> list[dict[str, str | None]]:
    try:
        rows = page.evaluate(
            """() => {
                const normalize = (value) => String(value || "").replace(/\\s+/g, " ").trim();
                const results = [];
                const seen = new Set();
                const pushItem = (title, url, updatedAt) => {
                    const cleanTitle = normalize(title);
                    const cleanUrl = normalize(url);
                    if (cleanTitle.length < 8) return;
                    const normalizedUrl = cleanUrl.startsWith('javascript:') ? '' : cleanUrl;
                    const key = `${cleanTitle}||${normalizedUrl}`;
                    if (seen.has(key)) return;
                    seen.add(key);
                    let appmsgId = null;
                    try {
                        if (normalizedUrl) {
                            const parsed = new URL(normalizedUrl, window.location.origin);
                            appmsgId = parsed.searchParams.get("appmsgid");
                        }
                    } catch (_) {}
                    results.push({
                        title: cleanTitle,
                        url: normalizedUrl,
                        appmsg_id: appmsgId,
                        updated_at: normalize(updatedAt),
                    });
                };

                const containers = Array.from(
                    document.querySelectorAll(
                        '.publish_card_container, .weui-desktop-card.weui-desktop-publish, .weui-desktop-media__list-col .weui-desktop-card'
                    )
                );

                containers.forEach((container) => {
                    const titleNode =
                        container.querySelector('.weui-desktop-publish__cover__title span') ||
                        container.querySelector('.weui-desktop-publish__cover__title') ||
                        container.querySelector('.weui-desktop-card__title');
                    const title = normalize(titleNode ? titleNode.textContent : '');
                    const linkNode =
                        container.querySelector('.weui-desktop-publish__cover__title') ||
                        container.querySelector('a[href]');
                    const href = normalize(linkNode ? linkNode.getAttribute('href') : '');
                    const containerText = normalize(container.innerText || '');
                    const updatedAtMatch = containerText.match(/更新于\\s*([0-9]{1,2}:[0-9]{2}|[0-9]{4}[-/.][0-9]{1,2}[-/.][0-9]{1,2})/);
                    const updatedAt = updatedAtMatch ? `更新于 ${updatedAtMatch[1]}` : '';
                    pushItem(title, href, updatedAt);
                });

                return results
                    .filter((item) => item.title || item.url)
                    .slice(0, 80);
            }"""
        )
    except Exception:
        return []
    if not isinstance(rows, list):
        return []
    items: list[dict[str, str | None]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        items.append(
            {
                "title": str(row.get("title") or "").strip(),
                "url": str(row.get("url") or "").strip(),
                "appmsg_id": str(row.get("appmsg_id") or "").strip() or None,
                "updated_at": str(row.get("updated_at") or "").strip() or None,
            }
        )
    return items


def _open_wechat_draft_box(page, selector_profile: dict[str, list[str] | str], step_logs: list[str]) -> bool:
    content_manage_selector = _pick_selector(page, selector_profile.get("content_manage", []), timeout=2500)
    if content_manage_selector:
        try:
            page.locator(content_manage_selector).first.click()
            page.wait_for_timeout(1200)
            step_logs.append(f"已展开内容管理 selector={content_manage_selector}")
        except Exception:
            step_logs.append(f"尝试展开内容管理失败 selector={content_manage_selector}")

    draft_box_selector = _pick_selector(page, selector_profile.get("draft_box", []), timeout=4000)
    if not draft_box_selector:
        return False

    page.locator(draft_box_selector).first.click()
    try:
        page.wait_for_url("**action=list_card**", timeout=8000)
    except Exception:
        page.wait_for_timeout(2500)
    step_logs.append(f"已点击草稿箱入口 selector={draft_box_selector}")
    current_url = str(page.url or "")
    if "action=list_card" not in current_url:
        step_logs.append(f"草稿箱页面未命中目标 URL: {current_url}")
        return False
    step_logs.append(f"已进入草稿箱页面 url={current_url}")
    return True


def inspect_wechat_draft_box(
    channel: dict[str, object],
    browser_state: dict[str, object],
) -> tuple[dict[str, object], list[str], list[str], list[dict[str, str | None]]]:
    channel = ensure_channel_defaults(channel)
    selector_version = str(channel.get("selectors_version", "wechat-mp-v1"))
    entry_url = str(channel.get("publish_entry_url", "https://mp.weixin.qq.com/"))
    selector_profile = get_selector_profile(selector_version)
    step_logs = [
        f"selector_profile={selector_version}",
        f"entry_url={entry_url}",
        "action=check_draft_box",
    ]
    artifacts: list[str] = []
    browser_state = dict(browser_state)

    if not browser_state.get("logged_in"):
        browser_state["last_error"] = "浏览器登录态不可用，无法检查微信草稿箱。"
        return browser_state, artifacts, step_logs + ["未执行草稿箱检查：登录态不可用。"], []

    artifact_dir = ARTIFACT_ROOT / "session"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    screenshot_path = artifact_dir / f"check-draft-box-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}.png"

    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except Exception:
        browser_state["last_error"] = "Playwright 不可用，暂时无法检查微信草稿箱。"
        return browser_state, artifacts, step_logs + ["Playwright 不可用，未执行草稿箱检查。"], []

    with sync_playwright() as playwright:  # pragma: no cover - depends on host browser
        context = playwright.chromium.launch_persistent_context(
            str(resolve_profile_path(channel.get("browser_profile_path"), channel.get("browser_name"))),
            headless=False,
            channel=browser_channel_name(str(channel.get("browser_name"))),
        )
        try:
            page = context.new_page()
            page.goto(entry_url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(1800)

            if not _open_wechat_draft_box(page, selector_profile, step_logs):
                raise RuntimeError("未能进入正式草稿箱页面（/cgi-bin/appmsg?...action=list_card...）。")

            current_page = context.pages[-1] if context.pages else page
            current_page.wait_for_timeout(2000)
            if "action=list_card" not in str(current_page.url or ""):
                raise RuntimeError(f"当前页面不是正式草稿箱：{current_page.url}")
            items = _scrape_wechat_draft_items(current_page)
            current_page.screenshot(path=str(screenshot_path), full_page=True)
            artifacts.append(str(screenshot_path))
            browser_state["last_opened_url"] = current_page.url
            browser_state["current_page"] = current_page.url
            browser_state["last_screenshot"] = str(screenshot_path)
            # 正式草稿箱页已成功打开时，空列表应视为“草稿箱当前为空”，
            # 不能当成失败，否则本地 synced 状态无法在远端删除后回退。
            browser_state["last_error"] = None
            step_logs.append(f"共读取到 {len(items)} 条微信草稿记录。")
            return browser_state, artifacts, step_logs, items
        except Exception as exc:
            try:
                page.screenshot(path=str(screenshot_path), full_page=True)
                artifacts.append(str(screenshot_path))
                browser_state["last_opened_url"] = page.url
                browser_state["current_page"] = page.url
                browser_state["last_screenshot"] = str(screenshot_path)
            except Exception:
                pass
            browser_state["last_error"] = str(exc)
            step_logs.append(f"草稿箱检查失败：{exc}")
            return browser_state, artifacts, step_logs, []
        finally:
            context.close()


def launch_wechat_dashboard(channel: dict[str, object], browser_state: dict[str, object]) -> tuple[dict[str, object], list[str], list[str]]:
    channel = ensure_channel_defaults(channel)
    browser_state = dict(browser_state)
    profile_path = resolve_profile_path(channel.get("browser_profile_path"), channel.get("browser_name"))
    entry_url = str(channel.get("publish_entry_url", "https://mp.weixin.qq.com/"))
    browser_name = normalize_browser_name(channel.get("browser_name"))
    step_logs = [
        f"browser={browser_name}",
        f"profile={profile_path}",
        f"entry_url={entry_url}",
    ]
    executable = resolve_browser_executable(browser_name)
    if executable is None:
        browser_state["last_error"] = f"未找到 {browser_name} 浏览器可执行文件。"
        return browser_state, [], step_logs + ["浏览器启动失败：未找到可执行文件。"]

    profile_path.parent.mkdir(parents=True, exist_ok=True)
    creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    subprocess.Popen(  # noqa: S603,S607 - controlled local executable path
        [
            executable,
            f"--user-data-dir={profile_path}",
            "--no-first-run",
            "--new-window",
            entry_url,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
    )
    browser_state.update(
        {
            "browser_name": browser_name,
            "user_data_dir": str(profile_path),
            "last_checked_at": now_iso(),
            "last_opened_url": entry_url,
            "current_page": entry_url,
            "last_error": None,
        }
    )
    return browser_state, [], step_logs + ["已启动浏览器，请在新窗口完成公众号扫码登录。"]


def inspect_wechat_session(channel: dict[str, object], browser_state: dict[str, object]) -> tuple[dict[str, object], list[str], list[str]]:
    channel = ensure_channel_defaults(channel)
    browser_state = dict(browser_state)
    profile_path = resolve_profile_path(channel.get("browser_profile_path"), channel.get("browser_name"))
    entry_url = str(channel.get("publish_entry_url", "https://mp.weixin.qq.com/"))
    selector_version = str(channel.get("selectors_version", "wechat-mp-v1"))
    selector_profile = get_selector_profile(selector_version)
    artifact_dir = ARTIFACT_ROOT / "session"
    screenshot_path = artifact_dir / f"check-browser-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}.png"
    debug_text_path = artifact_dir / f"check-browser-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}.txt"
    step_logs = [
        f"selector_profile={selector_version}",
        f"profile={profile_path}",
        f"entry_url={entry_url}",
    ]
    artifacts: list[str] = []

    if not profile_path.exists():
        browser_state["logged_in"] = False
        browser_state["last_checked_at"] = now_iso()
        browser_state["last_error"] = "浏览器用户目录尚未创建，请先打开公众号后台完成首次登录。"
        return browser_state, artifacts, step_logs + ["会话检查终止：浏览器 profile 不存在。"]

    try:
        from playwright.sync_api import Error as PlaywrightError  # type: ignore
        from playwright.sync_api import sync_playwright  # type: ignore
    except Exception:
        artifact = _write_debug_artifact(
            debug_text_path,
            [
                "Playwright 未安装或当前不可用。",
                f"profile={profile_path}",
                f"entry_url={entry_url}",
            ],
        )
        browser_state["logged_in"] = False
        browser_state["last_checked_at"] = now_iso()
        browser_state["last_screenshot"] = artifact
        browser_state["last_error"] = "Playwright 不可用，暂时无法验证登录态。"
        artifacts.append(artifact)
        return browser_state, artifacts, step_logs + ["Playwright 不可用，已写入调试文本。"]

    try:
        with sync_playwright() as playwright:  # pragma: no cover - depends on host browser
            context = playwright.chromium.launch_persistent_context(
                str(profile_path),
                headless=True,
                channel=browser_channel_name(browser_name := normalize_browser_name(channel.get("browser_name"))),
            )
            try:
                page = context.pages[0] if context.pages else context.new_page()
                page.goto(entry_url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(1500)

                logged_in = False
                matched_selector = None
                for selector in selector_profile.get("logged_in", []):
                    try:
                        page.wait_for_selector(str(selector), timeout=1200)
                        logged_in = True
                        matched_selector = str(selector)
                        break
                    except PlaywrightError:
                        continue

                page.screenshot(path=str(screenshot_path), full_page=True)
                artifacts.append(str(screenshot_path))
                browser_state["browser_name"] = browser_name
                browser_state["user_data_dir"] = str(profile_path)
                browser_state["logged_in"] = logged_in
                browser_state["last_checked_at"] = now_iso()
                browser_state["last_opened_url"] = page.url
                browser_state["current_page"] = page.url
                browser_state["last_screenshot"] = str(screenshot_path)
                browser_state["last_error"] = None if logged_in else "未检测到公众号后台登录态，当前可能仍停留在登录页。"
                if matched_selector:
                    step_logs.append(f"检测到登录态选择器：{matched_selector}")
                else:
                    step_logs.append("未命中登录态选择器。")
            finally:
                context.close()
    except Exception as exc:  # pragma: no cover - host/browser dependent
        artifact = _write_debug_artifact(
            debug_text_path,
            [
                "浏览器会话检查失败。",
                f"profile={profile_path}",
                f"entry_url={entry_url}",
                f"error={exc}",
            ],
        )
        artifacts.append(artifact)
        browser_state["logged_in"] = False
        browser_state["last_checked_at"] = now_iso()
        browser_state["last_screenshot"] = artifact
        browser_state["last_error"] = f"浏览器会话检查失败：{exc}"
        return browser_state, artifacts, step_logs + [f"会话检查失败：{exc}"]

    return browser_state, artifacts, step_logs


def run_browser_action(
    action: str,
    draft: dict[str, object],
    channel: dict[str, object],
    browser_state: dict[str, object],
) -> tuple[dict[str, object], list[str], list[str]]:
    channel = ensure_channel_defaults(channel)
    selector_version = str(channel.get("selectors_version", "wechat-mp-v1"))
    entry_url = str(channel.get("publish_entry_url", "https://mp.weixin.qq.com/"))
    selector_profile = get_selector_profile(selector_version)
    step_logs = [
        f"selector_profile={selector_version}",
        f"action={action}",
        f"entry_url={entry_url}",
    ]
    artifacts: list[str] = []
    browser_state = dict(browser_state)

    if not browser_state.get("logged_in"):
        browser_state["last_error"] = "浏览器用户目录不存在或尚未建立登录态。"
        return browser_state, artifacts, step_logs + ["未执行浏览器动作：登录态不可用。"]

    if action == "open_dashboard":
        maybe_open_url(entry_url)
        browser_state["last_opened_url"] = entry_url
        browser_state["current_page"] = entry_url
        browser_state["last_error"] = None
        return browser_state, artifacts, step_logs + [f"已打开公众号后台入口 {entry_url}"]

    artifact_dir = ARTIFACT_ROOT / draft["id"]
    artifact_dir.mkdir(parents=True, exist_ok=True)
    screenshot_path = artifact_dir / f"{action}-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}.png"

    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except Exception:
        screenshot_path.write_text(
            "Playwright 未安装或浏览器未准备好，当前记录为占位调试产物。\n"
            f"action={action}\nselector_profile={selector_version}\nentry={entry_url}\n",
            encoding="utf-8",
        )
        browser_state["last_screenshot"] = str(screenshot_path)
        browser_state["current_page"] = entry_url
        browser_state["last_error"] = "Playwright 不可用，已改为记录占位调试产物。"
        artifacts.append(str(screenshot_path))
        return browser_state, artifacts, step_logs + ["Playwright 不可用，未执行页面点击。"]

    with sync_playwright() as playwright:  # pragma: no cover - depends on host browser
        browser_type = getattr(playwright, "chromium")
        context = browser_type.launch_persistent_context(
            str(resolve_profile_path(channel.get("browser_profile_path"), channel.get("browser_name"))),
            headless=False,
            channel=browser_channel_name(str(channel.get("browser_name"))),
        )
        try:
            page = context.new_page()
            page.goto(entry_url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(1200)
            try:
                if action == "sync_wechat_draft":
                    new_article_selector = _pick_selector(page, selector_profile.get("new_article", []), timeout=5000)
                    if not new_article_selector:
                        raise RuntimeError("未找到“文章”入口。")
                    page.locator(new_article_selector).first.click()
                    page.wait_for_timeout(2500)
                    target = _locate_editor_page(context, page)
                    target.wait_for_timeout(2500)
                    step_logs.append(f"编辑页 URL={target.url}")
                    _fill_wechat_editor(target, draft, channel, selector_profile, step_logs)
                    save_selector = _pick_selector(target, selector_profile.get("save_draft_button", []), timeout=6000)
                    if not save_selector:
                        raise RuntimeError("未找到“保存为草稿”按钮。")
                    target.locator(save_selector).first.click()
                    target.wait_for_timeout(3500)
                    target.screenshot(path=str(screenshot_path), full_page=True)
                    browser_state["last_opened_url"] = target.url
                    browser_state["current_page"] = target.url
                    step_logs.append(f"已点击保存草稿 selector={save_selector}")
                elif action == "open_preview":
                    editor_url = resolve_editor_url(draft, browser_state, entry_url)
                    page.goto(editor_url, wait_until="domcontentloaded", timeout=30000)
                    page.wait_for_timeout(2200)
                    target = _locate_editor_page(context, page)
                    target.wait_for_timeout(1800)
                    preview_selector = _pick_selector(target, selector_profile.get("preview_button", []), timeout=6000)
                    if not preview_selector:
                        raise RuntimeError("未找到“预览”按钮。")
                    target.locator(preview_selector).first.click()
                    target.wait_for_timeout(2500)
                    blockers = detect_editor_blockers(target)
                    if blockers:
                        raise RuntimeError("；".join(blockers))
                    target.screenshot(path=str(screenshot_path), full_page=True)
                    browser_state["last_opened_url"] = target.url
                    browser_state["current_page"] = target.url
                    step_logs.append(f"已打开稿件编辑页 URL={target.url}")
                    step_logs.append(f"已点击预览 selector={preview_selector}")
                else:
                    page.screenshot(path=str(screenshot_path), full_page=True)
                    browser_state["last_opened_url"] = page.url
                    browser_state["current_page"] = page.url
                    step_logs.append(f"已打开页面 {page.url}")
                    if action == "publish" and draft.get("preview_url"):
                        step_logs.append("当前版本不会在无页面校准证据时自动点击最终发布按钮。")

                browser_state["last_error"] = None
            except Exception as exc:
                try:
                    active_page = _locate_editor_page(context, page, timeout_ms=2500)
                    active_page.screenshot(path=str(screenshot_path), full_page=True)
                    browser_state["last_opened_url"] = active_page.url
                    browser_state["current_page"] = active_page.url
                except Exception:
                    _write_debug_artifact(
                        screenshot_path.with_suffix(".txt"),
                        [f"action={action}", f"error={exc}", f"entry_url={entry_url}"],
                    )
                    browser_state["last_opened_url"] = entry_url
                    browser_state["current_page"] = entry_url
                browser_state["last_error"] = str(exc)
                step_logs.append(f"浏览器动作失败：{exc}")

            browser_state["last_screenshot"] = str(screenshot_path)
            artifacts.append(str(screenshot_path))
        finally:
            context.close()
    return browser_state, artifacts, step_logs
