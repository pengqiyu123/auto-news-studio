from __future__ import annotations

from datetime import datetime

from ...store.base import UTC
from ..browser_base import ARTIFACT_ROOT, _pick_selector, ensure_channel_defaults, get_selector_profile
from ..browser_manager import WECHAT_BROWSER_MANAGER
from .dom import _extract_wechat_analytics_overview
from .session import _browser_session_error_kind, _safe_return_home

def _open_wechat_publish_history(page, selector_profile: dict[str, list[str] | str], step_logs: list[str]) -> bool:
    content_manage_selector = _pick_selector(page, selector_profile.get("content_manage", []), timeout=2500)
    if content_manage_selector:
        try:
            page.locator(content_manage_selector).first.click()
            page.wait_for_timeout(1200)
            step_logs.append(f"已展开内容管理 selector={content_manage_selector}")
        except Exception:
            step_logs.append(f"尝试展开内容管理失败 selector={content_manage_selector}")

    selector_candidates = selector_profile.get("publish_history", [])
    selector_list = selector_candidates if isinstance(selector_candidates, list) else [selector_candidates]
    if not selector_list:
        return False
    failed_selectors: list[str] = []
    for selector in [str(item) for item in selector_list if str(item).strip()]:
        try:
            locator = page.locator(selector).first
            try:
                locator.wait_for(timeout=4000)
            except Exception:
                href = ""
                try:
                    href = str(locator.get_attribute("href", timeout=1200) or "").strip()
                except Exception:
                    href = ""
                if href and "appmsgpublish" in href:
                    target_url = href if href.startswith("http") else f"https://mp.weixin.qq.com{href}"
                    page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
                    page.wait_for_timeout(1200)
                else:
                    raise
            else:
                try:
                    locator.click(timeout=2000)
                except Exception:
                    href = ""
                    try:
                        href = str(locator.get_attribute("href", timeout=1200) or "").strip()
                    except Exception:
                        href = ""
                    if href and "appmsgpublish" in href:
                        target_url = href if href.startswith("http") else f"https://mp.weixin.qq.com{href}"
                        page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
                        page.wait_for_timeout(1200)
                    else:
                        locator.click(timeout=2000, force=True)
            try:
                page.wait_for_url("**appmsgpublish**", timeout=8000)
            except Exception:
                page.wait_for_timeout(2500)
            current_url = str(page.url or "")
            if "appmsgpublish" not in current_url:
                failed_selectors.append(selector)
                step_logs.append(f"发表记录入口未跳转 selector={selector} url={current_url}")
                continue
            step_logs.append(f"已点击发表记录入口 selector={selector}")
            step_logs.append(f"已进入发表记录页面 url={current_url}")
            return True
        except Exception as exc:
            failed_selectors.append(selector)
            step_logs.append(f"发表记录入口点击失败 selector={selector} error={exc}")
            continue
    if failed_selectors:
        step_logs.append(f"发表记录入口全部尝试失败：{', '.join(failed_selectors)}")
    return False

def _inspect_wechat_publish_history_document(target) -> dict[str, object]:
    result = target.evaluate(
        """() => {
            const normalize = (value) => String(value || "").replace(/\\s+/g, " ").trim();
            // 2026-05 微信更新：扩展选择器以覆盖新旧结构
            const titleAnchors = Array.from(document.querySelectorAll(
                'a.weui-desktop-mass-appmsg__title, a.weui-desktop-publish__title, ' +
                'a[href*="mp.weixin.qq.com/s/"], a[href*="s?__biz="], ' +
                '.weui-desktop-mass-appmsg__bd a[href], .weui-desktop-mass-media a[href]'
            ));
            const timeNodes = Array.from(document.querySelectorAll(
                '.weui-desktop-mass__time, .weui-desktop-publish__time, .publish_time, ' +
                'em.weui-desktop-mass__time, .weui-desktop-card__time'
            ));
            const hoverCards = Array.from(document.querySelectorAll('.publish_hover_content'));
            const massCards = Array.from(document.querySelectorAll('.weui-desktop-mass-media, .weui-desktop-mass-appmsg'));
            const dataListNodes = Array.from(document.querySelectorAll('.weui-desktop-mass-media__data-list'));
            const sampleTitles = titleAnchors
                .map((node) => normalize(node.textContent || node.getAttribute('title') || ''))
                .filter(Boolean)
                .slice(0, 5);
            const sampleTimes = timeNodes
                .map((node) => normalize(node.textContent || ''))
                .filter(Boolean)
                .slice(0, 5);
            return {
                href: window.location.href,
                title: document.title || '',
                readyState: document.readyState || '',
                title_anchor_count: titleAnchors.length,
                time_count: timeNodes.length,
                hover_card_count: hoverCards.length,
                mass_card_count: massCards.length,
                data_list_count: dataListNodes.length,
                sample_titles: sampleTitles,
                sample_times: sampleTimes,
                body_text_head: normalize((document.body && document.body.innerText) || '').slice(0, 240),
            };
        }"""
    )
    if not isinstance(result, dict):
        return {}
    return result

def _scrape_wechat_publish_history_from_target(target) -> list[dict[str, str | None]]:
    rows = target.evaluate(
        """() => {
            const normalize = (value) => String(value || "").replace(/\\s+/g, " ").trim();
            const cleanTitleLabel = (value) => normalize(value).replace(/\\s*原创\\s*$/u, '').trim();
            const results = [];
            const seenStable = new Set();
            const cardSelector = '.publish_hover_content, .weui-desktop-mass-media, .weui-desktop-mass-appmsg, .publish_card_container, .weui-desktop-card.weui-desktop-publish, .weui-desktop-media__list-col .weui-desktop-card, .publish_list .publish_item';

            const absolutize = (value) => {
                const raw = normalize(value);
                if (!raw || raw.startsWith('javascript:')) return '';
                if (raw.startsWith('//')) return `${window.location.protocol}${raw}`;
                if (raw.startsWith('/')) return `${window.location.origin}${raw}`;
                return raw;
            };

            const extractThumbnail = (container) => {
                if (!container) return '';
                const thumb = container.querySelector('.weui-desktop-mass-appmsg__thumb');
                if (!thumb) return '';
                const bg = thumb.style?.backgroundImage || '';
                const m = bg.match(/url\\(["']?([^"')]+)["']?\\)/);
                return m ? absolutize(m[1]) : '';
            };

            const extractMetrics = (container) => {
                const zero = { read_count: 0, like_count: 0, share_count: 0, recommend_count: 0, comment_count: 0, highlight_count: 0, tip_amount: '0.00', reprint_count: 0 };
                if (!container) return zero;
                const dataList = container.querySelector('.weui-desktop-mass-media__data-list');
                if (!dataList) return zero;
                const parseNum = (el) => { const t = normalize(el?.textContent || '0'); const n = parseInt(t.replace(/[^0-9]/g, ''), 10); return isNaN(n) ? 0 : n; };
                const parseMoney = (el) => { const t = normalize(el?.textContent || '0'); return t.replace(/[^0-9.]/g, '') || '0.00'; };
                // 2026-05 微信更新了 DOM 结构：data-list > tooltip__wrp > data.xxx > data__inner
                // 使用更宽松的选择器，允许中间有 wrapper 层
                const findDataInner = (className) => {
                    const direct = dataList.querySelector(`${className} .weui-desktop-mass-media__data__inner`);
                    if (direct) return direct;
                    const viaWrapper = dataList.querySelector(`.weui-desktop-tooltip__wrp ${className} .weui-desktop-mass-media__data__inner`);
                    if (viaWrapper) return viaWrapper;
                    const dataNode = dataList.querySelector(className);
                    if (dataNode) return dataNode.querySelector('.weui-desktop-mass-media__data__inner');
                    return null;
                };
                return {
                    read_count: parseNum(findDataInner('.appmsg-view')),
                    like_count: parseNum(findDataInner('.appmsg-like')),
                    share_count: parseNum(findDataInner('.appmsg-share')),
                    recommend_count: parseNum(findDataInner('.appmsg-haokan')),
                    comment_count: parseNum(findDataInner('.appmsg-comment')),
                    highlight_count: parseNum(findDataInner('.appmsg-underline')),
                    tip_amount: parseMoney(findDataInner('.appmsg-reward')),
                    reprint_count: parseNum(findDataInner('.appmsg-forward')),
                };
            };

            const pushItem = (title, url, publishedAt, occurrence, metricsContainer) => {
                const cleanTitle = cleanTitleLabel(title);
                const normalizedUrl = absolutize(url);
                // 过滤赞赏统计条目（标题为 ¥0.00 或以 ¥ 开头）
                if (cleanTitle.startsWith('¥') || cleanTitle.length < 2) return;
                // 过滤赞赏统计链接（merchant/reward）
                if (normalizedUrl.includes('merchant/reward')) return;
                let appmsgId = null;
                try {
                    if (normalizedUrl) {
                        const parsed = new URL(normalizedUrl, window.location.origin);
                        appmsgId = parsed.searchParams.get('appmsgid');
                    }
                } catch (_) {}
                const stableKey = appmsgId
                    ? `appmsg:${appmsgId}`
                    : normalizedUrl
                        ? `url:${normalizedUrl}`
                        : `publish:${cleanTitle}|${normalize(publishedAt)}|${occurrence}`;
                if (seenStable.has(stableKey)) return;
                seenStable.add(stableKey);
                const metrics = extractMetrics(metricsContainer);
                results.push({
                    title: cleanTitle,
                    url: normalizedUrl,
                    appmsg_id: appmsgId,
                    published_at: normalize(publishedAt),
                    remote_key: stableKey,
                    read_count: metrics.read_count,
                    like_count: metrics.like_count,
                    share_count: metrics.share_count,
                    recommend_count: metrics.recommend_count,
                    comment_count: metrics.comment_count,
                    highlight_count: metrics.highlight_count,
                    tip_amount: metrics.tip_amount,
                    reprint_count: metrics.reprint_count,
                    thumbnail: extractThumbnail(metricsContainer),
                });
            };

            const extractPublishedAt = (container) => {
                const dateNode =
                    container?.querySelector('.weui-desktop-mass__time') ||
                    container?.querySelector('.weui-desktop-publish__time') ||
                    container?.querySelector('.publish_time') ||
                    container?.querySelector('.weui-desktop-card__time');
                let publishedAt = normalize(dateNode ? dateNode.textContent : '');
                if (!publishedAt) {
                    const text = normalize(container?.innerText || '');
                    const match = text.match(/((?:昨天|前天|星期[一二三四五六日天])?\\s*[0-9]{1,2}:[0-9]{2}|[0-9]{1,2}月[0-9]{1,2}日|[0-9]{4}[-/.][0-9]{1,2}[-/.][0-9]{1,2})/);
                    publishedAt = match ? normalize(match[1]) : '';
                }
                return publishedAt;
            };

            const findBestContainer = (node) => {
                if (!node) return null;
                const directPublish = node.closest('.publish_hover_content');
                if (directPublish) return directPublish;
                let current = node;
                while (current && current !== document.body) {
                    if (current.matches && current.matches(cardSelector)) {
                        const hasTimeNode = current.querySelector('.weui-desktop-mass__time, .weui-desktop-publish__time, .publish_time, .weui-desktop-card__time');
                        if (hasTimeNode) return current;
                    }
                    current = current.parentElement;
                }
                return node.closest(cardSelector) || node.parentElement || node;
            };

            const titleAnchors = Array.from(
                document.querySelectorAll(
                    'a.weui-desktop-mass-appmsg__title, a.weui-desktop-publish__title, ' +
                    'a[href*="mp.weixin.qq.com/s/"], a[href*="s?__biz="], ' +
                    '.weui-desktop-mass-appmsg__bd a[href], .weui-desktop-mass-media a[href]'
                )
            );
            titleAnchors.forEach((anchor, index) => {
                const container = findBestContainer(anchor);
                const href = anchor.getAttribute('href') || '';
                const title =
                    cleanTitleLabel(anchor.textContent || '') ||
                    cleanTitleLabel(anchor.getAttribute('title') || '') ||
                    cleanTitleLabel(anchor.querySelector('span')?.textContent || '');
                const publishedAt = extractPublishedAt(container);
                pushItem(title, href, publishedAt, index, container);
            });

            if (!results.length) {
                const containers = Array.from(document.querySelectorAll(cardSelector));
                containers.forEach((container, index) => {
                    const titleNode =
                        container.querySelector('.weui-desktop-mass-appmsg__title span') ||
                        container.querySelector('.weui-desktop-mass-appmsg__title') ||
                        container.querySelector('.weui-desktop-publish__title span') ||
                        container.querySelector('.weui-desktop-publish__title') ||
                        container.querySelector('.weui-desktop-publish__cover__title span') ||
                        container.querySelector('.weui-desktop-publish__cover__title') ||
                        container.querySelector('.weui-desktop-card__title') ||
                        container.querySelector('a[title]') ||
                        container.querySelector('a.weui-desktop-mass-appmsg__title span') ||
                        container.querySelector('a span') ||
                        container.querySelector('h3');
                    const linkNode =
                        container.querySelector('a.weui-desktop-mass-appmsg__title') ||
                        container.querySelector('a.weui-desktop-publish__title') ||
                        container.querySelector('a[href*="mp.weixin.qq.com/s/"]') ||
                        container.querySelector('a[href*="s?__biz="]') ||
                        container.querySelector('a[href]');
                    const title = cleanTitleLabel(titleNode ? titleNode.textContent : '');
                    const href = linkNode ? linkNode.getAttribute('href') || '' : '';
                    const publishedAt = extractPublishedAt(container);
                    pushItem(title, href, publishedAt, index, container);
                });
            }

            return results.slice(0, 80);
        }"""
    )
    if not isinstance(rows, list):
        raise RuntimeError("发表记录抓取结果格式异常。")
    items: list[dict[str, str | None]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        items.append(
            {
                "title": str(row.get("title") or "").strip(),
                "url": str(row.get("url") or "").strip(),
                "appmsg_id": str(row.get("appmsg_id") or "").strip() or None,
                "published_at": str(row.get("published_at") or "").strip() or None,
                "remote_key": str(row.get("remote_key") or "").strip() or None,
                "read_count": int(row.get("read_count") or 0),
                "like_count": int(row.get("like_count") or 0),
                "share_count": int(row.get("share_count") or 0),
                "recommend_count": int(row.get("recommend_count") or 0),
                "comment_count": int(row.get("comment_count") or 0),
                "highlight_count": int(row.get("highlight_count") or 0),
                "tip_amount": str(row.get("tip_amount") or "0.00"),
                "reprint_count": int(row.get("reprint_count") or 0),
                "thumbnail": str(row.get("thumbnail") or "").strip(),
            }
        )
    return items

def _scrape_wechat_publish_history_items(page, step_logs: list[str] | None = None) -> list[dict[str, str | None]]:
    diagnostic_logs = step_logs if step_logs is not None else []
    targets = [("page", page)]
    try:
        frames = list(page.frames)
    except Exception:
        frames = []
    for index, frame in enumerate(frames):
        if frame is page.main_frame:
            continue
        targets.append((f"frame[{index}]", frame))

    merged: list[dict[str, str | None]] = []
    seen: set[str] = set()
    for label, target in targets:
        try:
            diag = _inspect_wechat_publish_history_document(target)
            if diag:
                diagnostic_logs.append(
                    "发表记录DOM "
                    f"{label} url={diag.get('href') or ''} "
                    f"titleAnchors={diag.get('title_anchor_count', 0)} "
                    f"timeNodes={diag.get('time_count', 0)} "
                    f"hoverCards={diag.get('hover_card_count', 0)} "
                    f"massCards={diag.get('mass_card_count', 0)} "
                    f"dataLists={diag.get('data_list_count', 0)} "
                    f"samples={','.join(str(item) for item in (diag.get('sample_titles') or [])[:3]) or 'none'}"
                )
            rows = _scrape_wechat_publish_history_from_target(target)
            diagnostic_logs.append(f"发表记录抽取 {label} rows={len(rows)}")
        except Exception as exc:
            diagnostic_logs.append(f"发表记录抽取 {label} 失败：{exc}")
            continue
        for row in rows:
            stable_key = (
                str(row.get("remote_key") or "").strip()
                or str(row.get("url") or "").strip()
                or f"{str(row.get('title') or '').strip()}|{str(row.get('published_at') or '').strip()}"
            )
            if not stable_key or stable_key in seen:
                continue
            seen.add(stable_key)
            merged.append(row)
    return merged

def inspect_wechat_publish_history(
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
        "action=check_publish_history",
    ]
    artifacts: list[str] = []
    browser_state = dict(browser_state)
    browser_state["is_session_level_error"] = False

    if not browser_state.get("logged_in"):
        browser_state["last_error"] = "浏览器登录态不可用，无法检查微信发表记录。"
        browser_state["is_session_level_error"] = True
        return browser_state, artifacts, step_logs + ["未执行发表记录检查：登录态不可用。"], []

    artifact_dir = ARTIFACT_ROOT / "session"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    screenshot_path = artifact_dir / f"check-publish-history-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}.png"

    try:
        def _run(_context, page):
            WECHAT_BROWSER_MANAGER.set_action_state("check_publish_history", "go_home")
            _safe_return_home(page, entry_url, selector_profile, step_logs, step_name="check_publish_history_return_home")
            WECHAT_BROWSER_MANAGER.set_action_state("check_publish_history", "open_publish_history")
            if not _open_wechat_publish_history(page, selector_profile, step_logs):
                raise RuntimeError("未能进入正式发表记录页面（/cgi-bin/appmsgpublish?...）。")
            current_page = page
            current_page.wait_for_timeout(2000)
            if "appmsgpublish" not in str(current_page.url or ""):
                raise RuntimeError(f"当前页面不是发表记录：{current_page.url}")
            WECHAT_BROWSER_MANAGER.set_action_state("check_publish_history", "scrape")
            all_items: list[dict[str, str | None]] = []
            seen_keys: set[str] = set()
            for page_num in range(1, 11):
                current_page.wait_for_timeout(1500)
                page_items = _scrape_wechat_publish_history_items(current_page, step_logs)
                new_count = 0
                for row in page_items:
                    key = str(row.get("remote_key") or row.get("url") or "").strip()
                    if not key or key in seen_keys:
                        continue
                    seen_keys.add(key)
                    all_items.append(row)
                    new_count += 1
                step_logs.append(f"第 {page_num} 页抓取 {len(page_items)} 条，新增 {new_count} 条，累计 {len(all_items)} 条。")
                if new_count == 0:
                    break
                next_btn = current_page.locator("a.weui-desktop-btn:has-text('下一页')")
                if next_btn.count() == 0 or not next_btn.first.is_enabled():
                    break
                try:
                    next_btn.first.click()
                except Exception:
                    break
            current_page.screenshot(path=str(screenshot_path), full_page=True)
            artifacts.append(str(screenshot_path))
            browser_state["last_opened_url"] = current_page.url
            browser_state["current_page"] = current_page.url
            browser_state["last_screenshot"] = str(screenshot_path)
            browser_state["resident_page"] = "publish_history"
            WECHAT_BROWSER_MANAGER.set_resident_page("publish_history")
            browser_state["last_error"] = None
            step_logs.append(f"共读取到 {len(all_items)} 条微信发表记录。")
            WECHAT_BROWSER_MANAGER.set_action_state("check_publish_history", "return_home")
            _safe_return_home(page, entry_url, selector_profile, step_logs, step_name="check_publish_history_return_home_final")
            browser_state["last_opened_url"] = page.url
            browser_state["current_page"] = page.url
            browser_state["resident_page"] = "home"
            WECHAT_BROWSER_MANAGER.set_resident_page("home")
            return all_items

        remote_items = WECHAT_BROWSER_MANAGER.with_session(
            channel,
            restore_window=False,
            action_fn=_run,
        )
        browser_state.update(WECHAT_BROWSER_MANAGER.manager_state())
        return browser_state, artifacts, step_logs, remote_items
    except Exception as exc:
        browser_state.update(WECHAT_BROWSER_MANAGER.manager_state())
        browser_state["last_error"] = f"发表记录检查失败：{exc}"
        browser_state["is_session_level_error"] = _browser_session_error_kind(exc, recovery_ok=False)
        step_logs.append(f"发表记录检查失败：{exc}")
        ok, current_url = WECHAT_BROWSER_MANAGER.capture_screenshot(screenshot_path)
        if ok:
            artifacts.append(str(screenshot_path))
            browser_state["last_screenshot"] = str(screenshot_path)
            if current_url:
                browser_state["last_opened_url"] = current_url
                browser_state["current_page"] = current_url
        return browser_state, artifacts, step_logs, []

def inspect_wechat_publish_history_with_overview(
    channel: dict[str, object],
    browser_state: dict[str, object],
) -> tuple[dict[str, object], list[str], list[str], list[dict[str, str | None]], dict[str, object] | None]:
    channel = ensure_channel_defaults(channel)
    selector_version = str(channel.get("selectors_version", "wechat-mp-v1"))
    entry_url = str(channel.get("publish_entry_url", "https://mp.weixin.qq.com/"))
    selector_profile = get_selector_profile(selector_version)
    browser_state = dict(browser_state)
    step_logs = [
        f"selector_profile={selector_version}",
        f"entry_url={entry_url}",
        "action=check_publish_history_with_overview",
    ]
    artifacts: list[str] = []
    overview: dict[str, object] | None = None
    browser_state["is_session_level_error"] = False

    if not browser_state.get("logged_in"):
        browser_state["last_error"] = "浏览器登录态不可用，无法检查微信发表记录。"
        browser_state["is_session_level_error"] = True
        return browser_state, artifacts, step_logs + ["未执行发表记录检查：登录态不可用。"], [], None

    artifact_dir = ARTIFACT_ROOT / "session"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    screenshot_path = artifact_dir / f"check-publish-history-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}.png"

    try:
        def _run(_context, page):
            nonlocal overview
            WECHAT_BROWSER_MANAGER.set_action_state("check_publish_history", "go_home")
            _safe_return_home(page, entry_url, selector_profile, step_logs, step_name="check_publish_history_return_home")

            WECHAT_BROWSER_MANAGER.set_action_state("check_publish_history", "scrape_overview")
            page.wait_for_timeout(2000)
            try:
                overview = _extract_wechat_analytics_overview(page)
                step_logs.append(f"已抓取首页总览：总用户 {overview.get('total_users', '?')}，昨日阅读 {overview.get('yesterday_reads', '?')}。")
            except Exception as exc:
                overview = None
                step_logs.append(f"抓取首页总览失败：{exc}")

            WECHAT_BROWSER_MANAGER.set_action_state("check_publish_history", "open_publish_history")
            if not _open_wechat_publish_history(page, selector_profile, step_logs):
                raise RuntimeError("未能进入正式发表记录页面（/cgi-bin/appmsgpublish?...）。")
            current_page = page
            current_page.wait_for_timeout(2000)
            if "appmsgpublish" not in str(current_page.url or ""):
                raise RuntimeError(f"当前页面不是发表记录：{current_page.url}")

            WECHAT_BROWSER_MANAGER.set_action_state("check_publish_history", "scrape")
            all_items: list[dict[str, str | None]] = []
            seen_keys: set[str] = set()
            max_pages = 10
            for page_num in range(1, max_pages + 1):
                current_page.wait_for_timeout(1500)
                page_items = _scrape_wechat_publish_history_items(current_page, step_logs)
                new_count = 0
                for row in page_items:
                    key = str(row.get("remote_key") or row.get("url") or "").strip()
                    if not key or key in seen_keys:
                        continue
                    seen_keys.add(key)
                    all_items.append(row)
                    new_count += 1
                step_logs.append(f"第 {page_num} 页抓取 {len(page_items)} 条，新增 {new_count} 条，累计 {len(all_items)} 条。")
                if new_count == 0:
                    break
                next_btn = current_page.locator("a.weui-desktop-btn:has-text('下一页')")
                if next_btn.count() == 0 or not next_btn.first.is_enabled():
                    break
                try:
                    next_btn.first.click()
                    step_logs.append(f"点击下一页，进入第 {page_num + 1} 页。")
                except Exception as exc:
                    step_logs.append(f"点击下一页失败：{exc}")
                    break
            items = all_items
            current_page.screenshot(path=str(screenshot_path), full_page=True)
            artifacts.append(str(screenshot_path))
            browser_state["last_opened_url"] = current_page.url
            browser_state["current_page"] = current_page.url
            browser_state["last_screenshot"] = str(screenshot_path)
            browser_state["resident_page"] = "publish_history"
            WECHAT_BROWSER_MANAGER.set_resident_page("publish_history")
            browser_state["last_error"] = None
            step_logs.append(f"共读取到 {len(items)} 条微信发表记录。")

            WECHAT_BROWSER_MANAGER.set_action_state("check_publish_history", "return_home")
            _safe_return_home(page, entry_url, selector_profile, step_logs, step_name="check_publish_history_return_home_final")
            browser_state["last_opened_url"] = page.url
            browser_state["current_page"] = page.url
            browser_state["resident_page"] = "home"
            WECHAT_BROWSER_MANAGER.set_resident_page("home")
            return items

        remote_items = WECHAT_BROWSER_MANAGER.with_session(
            channel,
            restore_window=False,
            action_fn=_run,
        )
        browser_state.update(WECHAT_BROWSER_MANAGER.manager_state())
        return browser_state, artifacts, step_logs, remote_items, overview
    except Exception as exc:
        browser_state.update(WECHAT_BROWSER_MANAGER.manager_state())
        browser_state["last_error"] = f"发表记录检查失败：{exc}"
        browser_state["is_session_level_error"] = _browser_session_error_kind(exc, recovery_ok=False)
        step_logs.append(f"发表记录检查失败：{exc}")
        ok, current_url = WECHAT_BROWSER_MANAGER.capture_screenshot(screenshot_path)
        if ok:
            artifacts.append(str(screenshot_path))
            browser_state["last_screenshot"] = str(screenshot_path)
            if current_url:
                browser_state["last_opened_url"] = current_url
                browser_state["current_page"] = current_url
        return browser_state, artifacts, step_logs, [], overview
