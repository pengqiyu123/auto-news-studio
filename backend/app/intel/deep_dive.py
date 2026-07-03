from __future__ import annotations

import re
from html import unescape
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx
import trafilatura
from readability import Document

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
TAVILY_SEARCH_URL = "https://api.tavily.com/search"


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if text:
            self._parts.append(text)

    def text(self) -> str:
        return " ".join(self._parts)


def canonicalize_url(url: str) -> str:
    raw = str(url or "").strip()
    if not raw:
        return ""
    parts = urlsplit(raw)
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, parts.query, ""))


def domain_label(url: str) -> str:
    parts = urlsplit(str(url or "").strip())
    return parts.netloc.lower()


def _clean_text(value: str) -> str:
    text = unescape(str(value or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _html_to_text(html: str) -> str:
    parser = _HTMLTextExtractor()
    parser.feed(html)
    return _clean_text(parser.text())


def _extract_with_trafilatura(html: str, url: str) -> str:
    extracted = trafilatura.extract(
        html,
        url=url,
        favor_precision=True,
        include_comments=False,
        include_tables=False,
        no_fallback=False,
    )
    return _clean_text(extracted or "")


def _extract_with_readability(html: str) -> str:
    try:
        doc = Document(html)
        summary_html = doc.summary(html_partial=True)
    except Exception:
        return ""
    return _html_to_text(summary_html)


def extract_best_text(html: str, url: str) -> tuple[str, str]:
    text = _extract_with_trafilatura(html, url)
    if len(text) >= 180:
        return text, "trafilatura"
    fallback = _extract_with_readability(html)
    if len(fallback) >= 180:
        return fallback, "readability"
    return (text or fallback), "failed"


def _pick_quotes(text: str, limit: int = 3) -> list[str]:
    normalized = str(text or "").replace("。", "。\n").replace("！", "！\n").replace("？", "？\n")
    segments = [_clean_text(item) for item in normalized.splitlines() if _clean_text(item)]
    quotes: list[str] = []
    for segment in segments:
        if len(segment) < 24:
            continue
        quotes.append(segment[:160])
        if len(quotes) >= limit:
            break
    return quotes


def search_tavily(
    *,
    api_key: str,
    query: str,
    max_results: int = 5,
) -> list[dict[str, Any]]:
    if not str(api_key or "").strip() or not str(query or "").strip():
        return []
    payload = {
        "query": str(query).strip(),
        "topic": "news",
        "search_depth": "advanced",
        "max_results": max(1, min(int(max_results), 10)),
        "include_answer": False,
        "include_raw_content": False,
    }
    try:
        with httpx.Client(timeout=20.0, headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}) as client:
            response = client.post(TAVILY_SEARCH_URL, json=payload)
            response.raise_for_status()
            data = response.json()
    except Exception:
        return []
    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in data.get("results", []) or []:
        link = str(item.get("url") or "").strip()
        canonical = canonicalize_url(link)
        identity = canonical or link
        if not identity or identity in seen:
            continue
        seen.add(identity)
        results.append(
            {
                "discovery_item_id": "",
                "source_key": "tavily",
                "source_name": str(item.get("site_name") or domain_label(link) or "Tavily").strip(),
                "title": str(item.get("title") or "").strip(),
                "summary": str(item.get("content") or "").strip(),
                "link": link,
                "canonical_link": canonical or link,
                "published_at": item.get("published_date"),
                "collected_at": None,
                "entity_names": [],
                "tavily_score": float(item.get("score", 0) or 0),
            }
        )
    return results


def fetch_and_extract_link(
    item: dict[str, Any],
    *,
    timeout_seconds: float,
) -> dict[str, Any]:
    original_link = str(item.get("link") or "").strip()
    canonical_link = canonicalize_url(original_link)
    result = {
        "source_key": str(item.get("source_key") or ""),
        "source_name": str(item.get("source_name") or ""),
        "original_link": original_link,
        "canonical_link": canonical_link or original_link,
        "title": str(item.get("title") or ""),
        "published_at": item.get("published_at"),
        "fetch_status": "pending",
        "extract_status": "pending",
        "word_count": 0,
        "cleaned_full_text": "",
        "excerpt": "",
        "quotes": [],
        "error": None,
    }
    if not original_link:
        result["fetch_status"] = "fetch_failed"
        result["extract_status"] = "extract_failed"
        result["error"] = "缺少链接"
        return result

    try:
        with httpx.Client(
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
            },
            follow_redirects=True,
            timeout=timeout_seconds,
        ) as client:
            response = client.get(original_link)
        if response.status_code >= 400:
            result["fetch_status"] = "fetch_failed"
            result["extract_status"] = "extract_failed"
            result["error"] = f"HTTP {response.status_code}"
            return result
        content_type = str(response.headers.get("content-type") or "").lower()
        if "text/html" not in content_type and "application/xhtml+xml" not in content_type:
            result["fetch_status"] = "non_html"
            result["extract_status"] = "extract_failed"
            result["error"] = f"非 HTML 内容：{content_type or 'unknown'}"
            return result
        html = response.text
        result["fetch_status"] = "fetched"
        canonical = canonicalize_url(str(response.url))
        if canonical:
            result["canonical_link"] = canonical
        extracted, extractor = extract_best_text(html, str(response.url))
        if not extracted:
            result["extract_status"] = "extract_failed"
            result["error"] = "正文提取失败"
            return result
        word_count = len(re.sub(r"\s+", "", extracted))
        result["word_count"] = word_count
        result["cleaned_full_text"] = extracted
        result["excerpt"] = extracted[:280]
        result["quotes"] = _pick_quotes(extracted)
        if word_count < 120:
            result["extract_status"] = "too_short"
            result["error"] = f"正文过短（{word_count}）"
        else:
            result["extract_status"] = "extracted"
            if not result["title"]:
                result["title"] = _clean_text(Document(html).title())
        if extractor == "failed" and result["extract_status"] == "extracted":
            result["extract_status"] = "too_short"
        return result
    except httpx.HTTPStatusError as exc:
        result["fetch_status"] = "fetch_failed"
        result["extract_status"] = "extract_failed"
        result["error"] = f"HTTP {exc.response.status_code}"
        return result
    except httpx.TimeoutException:
        result["fetch_status"] = "fetch_failed"
        result["extract_status"] = "extract_failed"
        result["error"] = "抓取超时"
        return result
    except httpx.HTTPError as exc:
        result["fetch_status"] = "fetch_blocked"
        result["extract_status"] = "extract_failed"
        result["error"] = str(exc)
        return result
    except Exception as exc:  # noqa: BLE001
        result["fetch_status"] = "fetch_failed"
        result["extract_status"] = "extract_failed"
        result["error"] = str(exc)
        return result
