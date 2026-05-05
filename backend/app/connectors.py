from __future__ import annotations

from datetime import datetime, timezone
from html import unescape
from http.client import IncompleteRead
import json
import os
import re
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

try:
    import feedparser  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    feedparser = None


UTC = timezone.utc
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AutoNewsStudio/1.0"
SOURCE_TIMEOUT_SECONDS = 12


def now_utc() -> datetime:
    return datetime.now(UTC)


def now_iso() -> str:
    return now_utc().replace(microsecond=0).isoformat()


def _clean_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", unescape(text)).strip()


def _warning_only(message: str) -> tuple[list[dict[str, Any]], str]:
    return [], message


def _is_http_url(value: str | None) -> bool:
    compact = str(value or "").strip().lower()
    return compact.startswith("https://") or compact.startswith("http://")


def _fetch_text(url: str, timeout: int = SOURCE_TIMEOUT_SECONDS) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=timeout) as response:  # noqa: S310 - controlled URLs from config
        charset = response.headers.get_content_charset() or "utf-8"
        try:
            return response.read().decode(charset, errors="ignore")
        except IncompleteRead as exc:
            return exc.partial.decode(charset, errors="ignore")


def _fetch_json(url: str, timeout: int = SOURCE_TIMEOUT_SECONDS) -> dict[str, Any]:
    return json.loads(_fetch_text(url, timeout=timeout))


def _parse_compact_number(value: str | None) -> int:
    compact = str(value or "").strip().lower().replace(",", "")
    if not compact:
        return 0
    multiplier = 1
    if compact.endswith("k"):
        multiplier = 1000
        compact = compact[:-1]
    elif compact.endswith("m"):
        multiplier = 1000_000
        compact = compact[:-1]
    try:
        return int(float(compact) * multiplier)
    except ValueError:
        return 0


def _fetch_github_repo_metrics(repo_full_name: str, token: str | None = None) -> dict[str, int]:
    headers = {"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"}
    auth_token = str(token or os.getenv("GITHUB_TOKEN") or "").strip()
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"
    request = Request(f"https://api.github.com/repos/{repo_full_name}", headers=headers)
    with urlopen(request, timeout=SOURCE_TIMEOUT_SECONDS) as response:  # noqa: S310 - controlled GitHub API URL
        payload = json.loads(response.read().decode("utf-8", errors="ignore"))
    return {
        "stars_total": int(payload.get("stargazers_count", 0) or 0),
        "forks_total": int(payload.get("forks_count", 0) or 0),
        "watchers_total": int(payload.get("subscribers_count", payload.get("watchers_count", 0)) or 0),
        "open_issues": int(payload.get("open_issues_count", 0) or 0),
    }


def _github_heat_score(stars_total: int, forks_total: int, watchers_total: int, stars_today: int) -> int:
    return int(
        round(
            stars_today * 25
            + min(stars_total, 50_000) * 0.04
            + min(forks_total, 10_000) * 0.3
            + min(watchers_total, 5_000) * 0.2
        )
    )


def _parse_rss_source(source: dict[str, Any], limit: int = 8) -> tuple[list[dict[str, Any]], str | None]:
    if not source.get("url"):
        return _warning_only("RSS URL 未配置，未写入素材。")
    if feedparser is None:
        return _warning_only("feedparser 不可用，未写入素材。")
    try:
        feed_text = _fetch_text(str(source["url"]), timeout=SOURCE_TIMEOUT_SECONDS)
        feed = feedparser.parse(feed_text.encode("utf-8", errors="ignore"))
        entries = getattr(feed, "entries", [])[:limit]
        if not entries:
            return _warning_only("RSS 源没有返回条目，未写入素材。")
        items: list[dict[str, Any]] = []
        for entry in entries:
            title = _clean_html(getattr(entry, "title", "") or "")
            link = str(getattr(entry, "link", "") or "").strip()
            summary = _clean_html(getattr(entry, "summary", "") or getattr(entry, "description", ""))[:320]
            published = getattr(entry, "published", None) or getattr(entry, "updated", None)
            if not title or not _is_http_url(link) or not published:
                continue
            items.append(
                {
                    "id": f"raw-{uuid4().hex[:10]}",
                    "source_key": source["key"],
                    "source_name": source["name"],
                    "source_kind": source["kind"],
                    "title": title,
                    "link": link,
                    "published_at": published,
                    "collected_at": now_iso(),
                    "summary": summary or title,
                    "content": summary or title,
                    "author": source["name"],
                    "tags": source.get("tags", []),
                    "engagement": {
                        "score": 0,
                        "comments": 0,
                        "views": 0,
                    },
                    "metadata": {"collector": "feedparser"},
                }
            )
            metadata = items[-1]["metadata"]
            entry_id = getattr(entry, "id", None) or getattr(entry, "guid", None) or link
            if entry_id:
                metadata["source_native_id"] = str(entry_id)
        if not items:
            return _warning_only("RSS 条目不完整或缺少链接/时间，未写入素材。")
        return items, None
    except Exception as exc:  # pragma: no cover - network dependent
        return _warning_only(f"{source['name']} 拉取失败，未写入素材: {exc}")


def _collect_reddit(source: dict[str, Any]) -> tuple[list[dict[str, Any]], str | None]:
    subreddit = source.get("auth", {}).get("subreddit", "technology")
    url = f"https://www.reddit.com/r/{subreddit}/hot.json?limit=8"
    try:
        payload = _fetch_json(url)
        children = payload.get("data", {}).get("children", [])
        if not children:
            return _warning_only("Reddit 没有返回内容，未写入素材。")
        items: list[dict[str, Any]] = []
        for child in children[:8]:
            data = child.get("data", {})
            title = str(data.get("title", "") or "").strip()
            permalink = str(data.get("permalink", "") or "").strip()
            if not title or not permalink:
                continue
            items.append(
                {
                    "id": f"raw-{uuid4().hex[:10]}",
                    "source_key": source["key"],
                    "source_name": source["name"],
                    "source_kind": source["kind"],
                    "title": title,
                    "link": f"https://www.reddit.com{permalink}",
                    "published_at": datetime.fromtimestamp(data.get("created_utc", now_utc().timestamp()), tz=UTC).isoformat(),
                    "collected_at": now_iso(),
                    "summary": _clean_html(data.get("selftext", ""))[:320] or "Reddit 社区热帖",
                    "content": _clean_html(data.get("selftext", ""))[:1800],
                    "author": data.get("author", subreddit),
                    "tags": source.get("tags", []),
                    "engagement": {
                        "score": data.get("score", 0),
                        "comments": data.get("num_comments", 0),
                        "upvote_ratio": data.get("upvote_ratio", 0),
                    },
                    "metadata": {"collector": "reddit_json", "subreddit": subreddit},
                }
            )
            items[-1]["metadata"]["source_native_id"] = str(data.get("id") or permalink)
        if not items:
            return _warning_only("Reddit 返回了数据，但缺少可用标题或链接，未写入素材。")
        return items, None
    except Exception as exc:  # pragma: no cover - network dependent
        return _warning_only(f"Reddit 抓取失败，未写入素材: {exc}")


def _collect_hackernews(source: dict[str, Any]) -> tuple[list[dict[str, Any]], str | None]:
    try:
        payload = _fetch_json("https://hn.algolia.com/api/v1/search?tags=front_page")
        hits = payload.get("hits", [])
        if not hits:
            return _warning_only("Hacker News 无返回，未写入素材。")
        items: list[dict[str, Any]] = []
        for hit in hits[:8]:
            title = str(hit.get("title") or hit.get("story_title") or "").strip()
            link = str(hit.get("url") or "").strip()
            if not link and hit.get("objectID"):
                link = f"https://news.ycombinator.com/item?id={hit.get('objectID')}"
            published_at = hit.get("created_at")
            if not title or not _is_http_url(link) or not published_at:
                continue
            items.append(
                {
                    "id": f"raw-{uuid4().hex[:10]}",
                    "source_key": source["key"],
                    "source_name": source["name"],
                    "source_kind": source["kind"],
                    "title": title,
                    "link": link,
                    "published_at": published_at,
                    "collected_at": now_iso(),
                    "summary": hit.get("story_text") or "Hacker News 首页热门条目",
                    "content": hit.get("story_text") or hit.get("comment_text") or "",
                    "author": hit.get("author", "hn"),
                    "tags": source.get("tags", []),
                    "engagement": {
                        "score": hit.get("points", 0),
                        "comments": hit.get("num_comments", 0),
                    },
                    "metadata": {"collector": "hn_algolia"},
                }
            )
            items[-1]["metadata"]["source_native_id"] = str(hit.get("objectID") or link)
        if not items:
            return _warning_only("Hacker News 返回了数据，但缺少可用标题、链接或时间，未写入素材。")
        return items, None
    except Exception as exc:  # pragma: no cover - network dependent
        return _warning_only(f"Hacker News 抓取失败，未写入素材: {exc}")


def _collect_github_trending(source: dict[str, Any]) -> tuple[list[dict[str, Any]], str | None]:
    try:
        html = _fetch_text("https://github.com/trending?spoken_language_code=")
        articles = re.findall(r"<article[\s\S]*?</article>", html)
        items: list[dict[str, Any]] = []
        for article in articles[:8]:
            repo_match = re.search(r'href="(/[^"]+/[^"]+)"', article)
            if not repo_match:
                continue
            repo_full_name = repo_match.group(1).strip("/")
            title = re.sub(r"\s+", "", repo_full_name)
            desc_match = re.search(r"<p[^>]*>([\s\S]*?)</p>", article)
            stars_match = re.search(r'href="[^"]+/stargazers"[^>]*>([\s\S]*?)</a>', article)
            forks_match = re.search(r'href="[^"]+/forks"[^>]*>([\s\S]*?)</a>', article)
            article_text = _clean_html(article)
            stars_today_match = re.search(r"([\d.,]+[kKmM]?)\s+stars?\s+today", article_text, re.IGNORECASE)

            stars_total = _parse_compact_number(_clean_html(stars_match.group(1)) if stars_match else "")
            forks_total = _parse_compact_number(_clean_html(forks_match.group(1)) if forks_match else "")
            stars_today = _parse_compact_number(stars_today_match.group(1) if stars_today_match else "")
            watchers_total = 0
            open_issues = 0

            if stars_total == 0 or forks_total == 0:
                try:
                    metrics = _fetch_github_repo_metrics(repo_full_name, token=source.get("auth", {}).get("github_token"))
                    stars_total = max(stars_total, metrics.get("stars_total", 0))
                    forks_total = max(forks_total, metrics.get("forks_total", 0))
                    watchers_total = metrics.get("watchers_total", 0)
                    open_issues = metrics.get("open_issues", 0)
                except Exception:
                    pass

            github_heat = _github_heat_score(stars_total, forks_total, watchers_total, stars_today)
            items.append(
                {
                    "id": f"raw-{uuid4().hex[:10]}",
                    "source_key": source["key"],
                    "source_name": source["name"],
                    "source_kind": source["kind"],
                    "title": title,
                    "link": f"https://github.com/{repo_full_name}",
                    "published_at": now_iso(),
                    "collected_at": now_iso(),
                    "summary": _clean_html(desc_match.group(1) if desc_match else "GitHub Trending 项目"),
                    "content": _clean_html(desc_match.group(1) if desc_match else "GitHub Trending 项目"),
                    "author": "github",
                    "tags": source.get("tags", []),
                    "engagement": {
                        "score": github_heat,
                        "comments": 0,
                    },
                    "metadata": {
                        "collector": "github_trending_html",
                        "published_at_inferred": True,
                        "source_native_id": repo_full_name,
                        "github_repo": repo_full_name,
                        "github_stars_total": stars_total,
                        "github_forks_total": forks_total,
                        "github_watchers_total": watchers_total,
                        "github_open_issues": open_issues,
                        "github_stars_today": stars_today,
                        "github_heat_score": github_heat,
                    },
                }
            )
        if not items:
            return _warning_only("GitHub Trending 解析为空，未写入素材。")
        return items, None
    except Exception as exc:  # pragma: no cover - network dependent
        return _warning_only(f"GitHub Trending 抓取失败，未写入素材: {exc}")


def _collect_vvhan_hotlist(source: dict[str, Any]) -> tuple[list[dict[str, Any]], str | None]:
    try:
        payload = _fetch_json("https://api.vvhan.com/api/hotlist/all", timeout=15)
        data = payload.get("data", {}) if isinstance(payload, dict) else {}
        items: list[dict[str, Any]] = []
        for category, entries in data.items():
            if not isinstance(entries, list):
                continue
            for entry in entries[:5]:
                title = str(entry.get("title", "")).strip()
                if not title:
                    continue
                hot = int(entry.get("hot", 0) or 0)
                url = str(entry.get("url", "")).strip() or ""
                if not _is_http_url(url):
                    continue
                items.append(
                    {
                        "id": f"raw-{uuid4().hex[:10]}",
                        "source_key": source["key"],
                        "source_name": f"VVhan·{category}",
                        "source_kind": source["kind"],
                        "title": title,
                        "link": url,
                        "published_at": now_iso(),
                        "collected_at": now_iso(),
                        "summary": str(entry.get("desc", ""))[:280] or title,
                        "content": str(entry.get("desc", ""))[:1200] or title,
                        "author": "vvhan",
                        "tags": [*source.get("tags", []), category],
                        "engagement": {"score": hot, "comments": 0},
                        "metadata": {"collector": "vvhan_hotlist", "category": category, "published_at_inferred": True},
                    }
                )
                items[-1]["metadata"]["source_native_id"] = str(entry.get("id") or f"{category}:{url}")
        if not items:
            return _warning_only("VVhan 热榜返回为空或缺少可用链接，未写入素材。")
        items.sort(key=lambda x: x["engagement"]["score"], reverse=True)
        return items[:16], None
    except Exception as exc:  # pragma: no cover - network dependent
        return _warning_only(f"VVhan 热榜抓取失败，未写入素材: {exc}")


def _collect_youtube_channel(source: dict[str, Any]) -> tuple[list[dict[str, Any]], str | None]:
    api_key = os.getenv("YOUTUBE_API_KEY", "")
    if not api_key:
        return _warning_only("YouTube: 未配置 YOUTUBE_API_KEY，跳过。")
    channel_id = str(source.get("auth", {}).get("channel_id", "") or "").strip()
    handle = str(source.get("auth", {}).get("handle", "") or "").strip()
    if not channel_id and not handle:
        return _warning_only(f"YouTube: {source['name']} 未配置 channel_id 或 handle，跳过。")
    try:
        if handle:
            search_param = f"forHandle={handle}"
        else:
            search_param = f"channelId={channel_id}"
        url = (
            f"https://www.googleapis.com/youtube/v3/search"
            f"?part=snippet&{search_param}&maxResults=5&order=date&type=video&key={api_key}"
        )
        payload = _fetch_json(url, timeout=15)
        items_data = payload.get("items", [])
        if not items_data:
            return _warning_only(f"YouTube: {source['name']} 频道无最新视频。")
        items: list[dict[str, Any]] = []
        for entry in items_data[:5]:
            snippet = entry.get("snippet", {}) or {}
            video_id = (entry.get("id", {}) or {}).get("videoId", "")
            title = str(snippet.get("title", "") or "").strip()
            if not title or not video_id:
                continue
            desc = _clean_html(snippet.get("description", "") or "")
            published = snippet.get("publishedAt", "")
            thumbnail = (snippet.get("thumbnails", {}) or {}).get("high", {}) or {}
            thumb_url = str(thumbnail.get("url", "") or "").strip()
            items.append(
                {
                    "id": f"raw-{uuid4().hex[:10]}",
                    "source_key": source["key"],
                    "source_name": source["name"],
                    "source_kind": source["kind"],
                    "title": title,
                    "link": f"https://www.youtube.com/watch?v={video_id}",
                    "published_at": published,
                    "collected_at": now_iso(),
                    "summary": desc[:320] or title,
                    "content": desc[:1800] or title,
                    "author": str(snippet.get("channelTitle", "") or source["name"]),
                    "tags": source.get("tags", []),
                    "engagement": {"youtube_video_id": video_id},
                    "metadata": {
                        "collector": "youtube_channel",
                        "channel_id": channel_id,
                        "source_native_id": video_id,
                        "thumbnail_url": thumb_url,
                    },
                }
            )
        if not items:
            return _warning_only(f"YouTube: {source['name']} 返回数据但无可用视频。")
        return items, None
    except Exception as exc:
        return _warning_only(f"YouTube 抓取失败，未写入素材: {exc}")


def _collect_wordpress(source: dict[str, Any]) -> tuple[list[dict[str, Any]], str | None]:
    site_url = str(source.get("url", "") or "").strip().rstrip("/")
    if not site_url or not _is_http_url(site_url):
        return _warning_only(f"WordPress: {source['name']} URL 无效，跳过。")
    try:
        api_url = f"{site_url}/wp-json/wp/v2/posts?per_page=8&orderby=date"
        payload = _fetch_json(api_url, timeout=12)
        if not isinstance(payload, list) or not payload:
            return _warning_only(f"WordPress: {source['name']} 无文章返回，可能不是 WordPress 站点。")
        items: list[dict[str, Any]] = []
        for post in payload[:8]:
            title = _clean_html(str(post.get("title", {}) or {}).get("rendered", "") or "")
            link = str(post.get("link", "") or "").strip()
            if not title or not _is_http_url(link):
                continue
            content_raw = str(post.get("content", {}) or {}).get("rendered", "") or ""
            excerpt_raw = str(post.get("excerpt", {}) or {}).get("rendered", "") or ""
            published = post.get("date", "")
            author_info = post.get("author", 0)
            items.append(
                {
                    "id": f"raw-{uuid4().hex[:10]}",
                    "source_key": source["key"],
                    "source_name": source["name"],
                    "source_kind": source["kind"],
                    "title": title,
                    "link": link,
                    "published_at": published,
                    "collected_at": now_iso(),
                    "summary": _clean_html(excerpt_raw)[:320] or title,
                    "content": _clean_html(content_raw)[:1800] or title,
                    "author": str(author_info) if author_info else "",
                    "tags": source.get("tags", []),
                    "engagement": {"comment_count": int(post.get("comment_count", 0) or 0)},
                    "metadata": {
                        "collector": "wordpress_rest",
                        "site_url": site_url,
                        "source_native_id": str(post.get("id", "") or ""),
                    },
                }
            )
        if not items:
            return _warning_only(f"WordPress: {source['name']} 返回数据但无可用文章。")
        return items, None
    except Exception as exc:
        return _warning_only(f"WordPress 抓取失败，未写入素材: {exc}")


def _unsupported_connector(source: dict[str, Any]) -> tuple[list[dict[str, Any]], str | None]:
    label = source.get("driver", source["kind"])
    return _warning_only(f"{source['name']} 当前连接器 {label} 尚未适配，未写入素材。")


COLLECTORS: dict[str, Callable[[dict[str, Any]], tuple[list[dict[str, Any]], str | None]]] = {
    "reddit_hot": _collect_reddit,
    "hackernews_frontpage": _collect_hackernews,
    "github_trending": _collect_github_trending,
    "vvhan_hotlist": _collect_vvhan_hotlist,
    "youtube_channel": _collect_youtube_channel,
    "wordpress_rest": _collect_wordpress,
}


def collect_from_source(source: dict[str, Any]) -> tuple[list[dict[str, Any]], str | None]:
    if source["kind"] in {"rss", "rsshub"}:
        return _parse_rss_source(source)
    collector = COLLECTORS.get(source["driver"], _unsupported_connector)
    return collector(source)


def _collect_with_retry(source: dict[str, Any], max_retries: int = 2) -> tuple[list[dict[str, Any]], str | None]:
    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            return collect_from_source(source)
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            last_error = exc
            if attempt < max_retries:
                import time
                time.sleep(2 ** attempt)
    return _warning_only(f"{source['name']} 拉取失败（重试 {max_retries} 次后放弃）: {last_error}")


DEFAULT_MAX_WORKERS = 8


def collect_enabled_sources(
    sources: list[dict[str, Any]], max_workers: int = DEFAULT_MAX_WORKERS
) -> tuple[list[dict[str, Any]], list[str]]:
    enabled = [s for s in sources if s.get("enabled")]
    raw_items: list[dict[str, Any]] = []
    warnings: list[str] = []

    from concurrent.futures import ThreadPoolExecutor, as_completed

    def _safe_collect(source: dict[str, Any]) -> tuple[list[dict[str, Any]], str | None, str]:
        try:
            items, warning = _collect_with_retry(source)
            return items, warning or "", ""
        except Exception as exc:
            return [], "", f"{source['name']}: 抓取器异常: {exc}"

    with ThreadPoolExecutor(max_workers=max(1, min(max_workers, 20))) as pool:
        futures = {pool.submit(_safe_collect, s): s for s in enabled}
        for future in as_completed(futures):
            try:
                items, warning, error = future.result()
                raw_items.extend(items)
                if warning:
                    warnings.append(warning)
                if error:
                    warnings.append(error)
            except Exception:
                pass

    raw_items.sort(key=lambda item: item["collected_at"], reverse=True)
    return raw_items, warnings
