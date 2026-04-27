from __future__ import annotations

from datetime import datetime, timezone
from html import unescape
import json
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


def _fetch_text(url: str, timeout: int = 12) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=timeout) as response:  # noqa: S310 - controlled URLs from config
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="ignore")


def _fetch_json(url: str, timeout: int = 12) -> dict[str, Any]:
    return json.loads(_fetch_text(url, timeout=timeout))


def _parse_rss_source(source: dict[str, Any], limit: int = 8) -> tuple[list[dict[str, Any]], str | None]:
    if not source.get("url"):
        return _warning_only("RSS URL 未配置，未写入素材。")
    if feedparser is None:
        return _warning_only("feedparser 不可用，未写入素材。")
    try:
        feed = feedparser.parse(source["url"])
        entries = getattr(feed, "entries", [])[:limit]
        if not entries:
            return _warning_only("RSS 源没有返回条目，未写入素材。")
        items: list[dict[str, Any]] = []
        for index, entry in enumerate(entries, start=1):
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
                        "score": 90 + index * 10,
                        "comments": 12 + index * 2,
                        "views": 1200 + index * 500,
                    },
                    "metadata": {"collector": "feedparser"},
                }
            )
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
            title = re.sub(r"\s+", "", repo_match.group(1).strip("/"))
            desc_match = re.search(r"<p[^>]*>([\s\S]*?)</p>", article)
            stars_match = re.search(r'href="[^"]+/stargazers"[^>]*>\s*([\d,]+)\s*</a>', article)
            items.append(
                {
                    "id": f"raw-{uuid4().hex[:10]}",
                    "source_key": source["key"],
                    "source_name": source["name"],
                    "source_kind": source["kind"],
                    "title": title,
                    "link": f"https://github.com{repo_match.group(1)}",
                    "published_at": now_iso(),
                    "collected_at": now_iso(),
                    "summary": _clean_html(desc_match.group(1) if desc_match else "GitHub Trending 项目"),
                    "content": _clean_html(desc_match.group(1) if desc_match else "GitHub Trending 项目"),
                    "author": "github",
                    "tags": source.get("tags", []),
                    "engagement": {
                        "score": int((stars_match.group(1) if stars_match else "0").replace(",", "") or 0),
                        "comments": 0,
                    },
                    "metadata": {"collector": "github_trending_html", "published_at_inferred": True},
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
        if not items:
            return _warning_only("VVhan 热榜返回为空或缺少可用链接，未写入素材。")
        items.sort(key=lambda x: x["engagement"]["score"], reverse=True)
        return items[:16], None
    except Exception as exc:  # pragma: no cover - network dependent
        return _warning_only(f"VVhan 热榜抓取失败，未写入素材: {exc}")


def _unsupported_connector(source: dict[str, Any]) -> tuple[list[dict[str, Any]], str | None]:
    label = source.get("driver", source["kind"])
    return _warning_only(f"{source['name']} 当前连接器 {label} 尚未适配，未写入素材。")


COLLECTORS: dict[str, Callable[[dict[str, Any]], tuple[list[dict[str, Any]], str | None]]] = {
    "reddit_hot": _collect_reddit,
    "hackernews_frontpage": _collect_hackernews,
    "github_trending": _collect_github_trending,
    "vvhan_hotlist": _collect_vvhan_hotlist,
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
