from __future__ import annotations

from datetime import datetime, timedelta, timezone
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


def _sample_items(source: dict[str, Any], reason: str, count: int = 4) -> list[dict[str, Any]]:
    templates = {
        "github": [
            ("GitHub Trending 出现多项 AI 自动化基础设施项目", "开发者关注点正在从 Demo 走向生产编排。"),
            ("开源生态开始围绕浏览器自动化与 AI Agent 融合", "对运营自动化型产品特别有价值。"),
        ],
        "reddit": [
            ("Reddit 讨论浏览器自动化在内容运营里的边界", "稳定性与风控仍然是高频问题。"),
            ("社区比较不同大模型的工具调用质量", "选题很适合做对比与经验稿。"),
        ],
        "newsnow": [
            ("热点池里 AI Agent 运维话题持续升温", "读者开始关注可靠性和成本，而不只是模型能力。"),
            ("多源聚合型新闻助手再次成为热点", "信息供给质量重新成为内容生产的上游瓶颈。"),
        ],
        "page": [
            ("科技媒体集中报道浏览器自动化与 AI 协作", "适合做公众号专题稿。"),
            ("大模型运营工具链出现新的集成范式", "对自媒体工作流影响明显。"),
        ],
    }
    items = templates.get(source["kind"], templates.get(source["driver"], templates["newsnow"]))
    published_base = now_utc()
    material: list[dict[str, Any]] = []
    for index in range(count):
        title, summary = items[index % len(items)]
        published = (published_base - timedelta(hours=index * 2 + 1)).replace(microsecond=0).isoformat()
        material.append(
            {
                "id": f"raw-{uuid4().hex[:10]}",
                "source_key": source["key"],
                "source_name": source["name"],
                "source_kind": source["kind"],
                "title": f"{title} | {source['name']}",
                "link": f"https://example.com/{source['key']}/{index + 1}",
                "published_at": published,
                "collected_at": now_iso(),
                "summary": summary,
                "content": f"{summary} 该条目来自 {source['name']}，当前为回退样例。原因：{reason}",
                "author": source["name"],
                "tags": source.get("tags", []),
                "engagement": {
                    "score": 110 + index * 25,
                    "comments": 16 + index * 3,
                    "views": 2400 + index * 450,
                },
                "metadata": {"fallback": True, "reason": reason},
            }
        )
    return material


def _fetch_text(url: str, timeout: int = 12) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=timeout) as response:  # noqa: S310 - controlled URLs from config
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="ignore")


def _fetch_json(url: str, timeout: int = 12) -> dict[str, Any]:
    return json.loads(_fetch_text(url, timeout=timeout))


def _parse_rss_source(source: dict[str, Any], limit: int = 8) -> tuple[list[dict[str, Any]], str | None]:
    if not source.get("url"):
        return _sample_items(source, "RSS URL 未配置"), "RSS URL 未配置，已回退到样例素材。"
    if feedparser is None:
        return _sample_items(source, "feedparser 不可用"), "feedparser 不可用，已回退到样例素材。"
    try:
        feed = feedparser.parse(source["url"])
        entries = getattr(feed, "entries", [])[:limit]
        if not entries:
            return _sample_items(source, "RSS 源没有返回条目"), "RSS 源没有返回条目，已回退到样例素材。"
        items: list[dict[str, Any]] = []
        for index, entry in enumerate(entries, start=1):
            title = _clean_html(getattr(entry, "title", "") or f"{source['name']} 条目 {index}")
            link = getattr(entry, "link", None) or f"https://example.com/{source['key']}/{index}"
            summary = _clean_html(getattr(entry, "summary", "") or getattr(entry, "description", ""))[:320]
            published = getattr(entry, "published", None) or getattr(entry, "updated", None) or now_iso()
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
                    "summary": summary or f"{source['name']} 的 RSS 摘要。",
                    "content": summary or f"{source['name']} 的 RSS 摘要。",
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
        return items, None
    except Exception as exc:  # pragma: no cover - network dependent
        return _sample_items(source, str(exc)), f"{source['name']} 拉取失败，已回退到样例素材: {exc}"


def _collect_reddit(source: dict[str, Any]) -> tuple[list[dict[str, Any]], str | None]:
    subreddit = source.get("auth", {}).get("subreddit", "technology")
    url = f"https://www.reddit.com/r/{subreddit}/hot.json?limit=8"
    try:
        payload = _fetch_json(url)
        children = payload.get("data", {}).get("children", [])
        if not children:
            return _sample_items(source, "Reddit 没有返回内容"), "Reddit 没有返回内容，已回退到样例素材。"
        items: list[dict[str, Any]] = []
        for child in children[:8]:
            data = child.get("data", {})
            items.append(
                {
                    "id": f"raw-{uuid4().hex[:10]}",
                    "source_key": source["key"],
                    "source_name": source["name"],
                    "source_kind": source["kind"],
                    "title": data.get("title", "Reddit 热帖"),
                    "link": f"https://www.reddit.com{data.get('permalink', '')}",
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
        return items, None
    except Exception as exc:  # pragma: no cover - network dependent
        return _sample_items(source, str(exc)), f"Reddit 抓取失败，已回退到样例素材: {exc}"


def _collect_hackernews(source: dict[str, Any]) -> tuple[list[dict[str, Any]], str | None]:
    try:
        payload = _fetch_json("https://hn.algolia.com/api/v1/search?tags=front_page")
        hits = payload.get("hits", [])
        if not hits:
            return _sample_items(source, "Hacker News 无返回"), "Hacker News 无返回，已回退到样例素材。"
        items: list[dict[str, Any]] = []
        for hit in hits[:8]:
            items.append(
                {
                    "id": f"raw-{uuid4().hex[:10]}",
                    "source_key": source["key"],
                    "source_name": source["name"],
                    "source_kind": source["kind"],
                    "title": hit.get("title") or hit.get("story_title") or "Hacker News Front Page",
                    "link": hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}",
                    "published_at": hit.get("created_at", now_iso()),
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
        return items, None
    except Exception as exc:  # pragma: no cover - network dependent
        return _sample_items(source, str(exc)), f"Hacker News 抓取失败，已回退到样例素材: {exc}"


def _collect_github_trending(source: dict[str, Any]) -> tuple[list[dict[str, Any]], str | None]:
    try:
        html = _fetch_text("https://github.com/trending?spoken_language_code=")
        articles = re.findall(r"<article[\s\S]*?</article>", html)
        items: list[dict[str, Any]] = []
        for article in articles[:8]:
            repo_match = re.search(r'href="(/[^"]+/[^"]+)"', article)
            title = re.sub(r"\s+", "", repo_match.group(1).strip("/")) if repo_match else "GitHub Trending"
            desc_match = re.search(r"<p[^>]*>([\s\S]*?)</p>", article)
            stars_match = re.search(r'href="[^"]+/stargazers"[^>]*>\s*([\d,]+)\s*</a>', article)
            items.append(
                {
                    "id": f"raw-{uuid4().hex[:10]}",
                    "source_key": source["key"],
                    "source_name": source["name"],
                    "source_kind": source["kind"],
                    "title": title,
                    "link": f"https://github.com{repo_match.group(1)}" if repo_match else "https://github.com/trending",
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
                    "metadata": {"collector": "github_trending_html"},
                }
            )
        if not items:
            return _sample_items(source, "GitHub Trending 解析为空"), "GitHub Trending 解析为空，已回退到样例素材。"
        return items, None
    except Exception as exc:  # pragma: no cover - network dependent
        return _sample_items(source, str(exc)), f"GitHub Trending 抓取失败，已回退到样例素材: {exc}"


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
                items.append(
                    {
                        "id": f"raw-{uuid4().hex[:10]}",
                        "source_key": source["key"],
                        "source_name": f"VVhan·{category}",
                        "source_kind": source["kind"],
                        "title": title,
                        "link": url or f"https://example.com/vvhan/{uuid4().hex[:6]}",
                        "published_at": now_iso(),
                        "collected_at": now_iso(),
                        "summary": str(entry.get("desc", ""))[:280] or title,
                        "content": str(entry.get("desc", ""))[:1200] or title,
                        "author": "vvhan",
                        "tags": [*source.get("tags", []), category],
                        "engagement": {"score": hot, "comments": 0},
                        "metadata": {"collector": "vvhan_hotlist", "category": category},
                    }
                )
        if not items:
            return _sample_items(source, "VVhan 返回为空"), "VVhan 热榜返回为空，已回退到样例素材。"
        items.sort(key=lambda x: x["engagement"]["score"], reverse=True)
        return items[:16], None
    except Exception as exc:  # pragma: no cover - network dependent
        return _sample_items(source, str(exc)), f"VVhan 热榜抓取失败，已回退到样例素材: {exc}"


def _collect_placeholder_page(source: dict[str, Any]) -> tuple[list[dict[str, Any]], str | None]:
    label = source.get("driver", source["kind"])
    return _sample_items(source, f"{label} 连接器等待站点级适配"), f"{source['name']} 当前采用占位采集器，已写入可用样例素材。"


COLLECTORS: dict[str, Callable[[dict[str, Any]], tuple[list[dict[str, Any]], str | None]]] = {
    "reddit_hot": _collect_reddit,
    "hackernews_frontpage": _collect_hackernews,
    "github_trending": _collect_github_trending,
    "vvhan_hotlist": _collect_vvhan_hotlist,
    "newsnow_pool": _collect_placeholder_page,
    "legacy_bilibili": _collect_placeholder_page,
    "legacy_toutiao": _collect_placeholder_page,
    "legacy_youtube": _collect_placeholder_page,
}


def collect_from_source(source: dict[str, Any]) -> tuple[list[dict[str, Any]], str | None]:
    if source["kind"] in {"rss", "rsshub"}:
        return _parse_rss_source(source)
    collector = COLLECTORS.get(source["driver"], _collect_placeholder_page)
    return collector(source)


def collect_enabled_sources(sources: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    raw_items: list[dict[str, Any]] = []
    warnings: list[str] = []
    for source in sources:
        if not source.get("enabled"):
            continue
        try:
            items, warning = collect_from_source(source)
            raw_items.extend(items)
            if warning:
                warnings.append(f"{source['name']}: {warning}")
        except (HTTPError, URLError, TimeoutError) as exc:  # pragma: no cover - network dependent
            raw_items.extend(_sample_items(source, str(exc)))
            warnings.append(f"{source['name']}: 网络请求失败，已回退到样例素材: {exc}")
        except Exception as exc:  # pragma: no cover - defensive
            raw_items.extend(_sample_items(source, str(exc)))
            warnings.append(f"{source['name']}: 抓取器异常，已回退到样例素材: {exc}")
    raw_items.sort(key=lambda item: item["published_at"], reverse=True)
    return raw_items, warnings
