from __future__ import annotations

import re

try:  # jieba is declared as a runtime dependency; fallback keeps tests importable before install.
    import jieba  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - exercised in lean local envs
    jieba = None


STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "news",
    "update",
    "today",
    "发布",
    "宣布",
    "最新",
    "一个",
    "多个",
    "进行",
    "相关",
    "记者",
    "报道",
    "消息",
    "显示",
    "公司",
}


def _fallback_zh_tokens(text: str) -> list[str]:
    tokens: list[str] = []
    for segment in re.findall(r"[\u4e00-\u9fff]+", text):
        if len(segment) <= 4:
            tokens.append(segment)
            continue
        for size in (2, 3):
            tokens.extend(segment[index:index + size] for index in range(0, len(segment) - size + 1))
    return tokens


def tokenize_for_analysis(title: str) -> list[str]:
    text = str(title or "").strip()
    if not text:
        return []
    tokens: list[str] = []
    tokens.extend(item.lower() for item in re.findall(r"[A-Za-z][A-Za-z0-9.+-]{1,}", text))
    if jieba is not None:
        tokens.extend(str(item).strip().lower() for item in jieba.cut(text, cut_all=False))
    else:
        tokens.extend(_fallback_zh_tokens(text))
    cleaned: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        token = re.sub(r"^[^\w\u4e00-\u9fff]+|[^\w\u4e00-\u9fff]+$", "", token.lower())
        if len(token) < 2 or token in STOPWORDS:
            continue
        if re.fullmatch(r"\d+", token):
            continue
        if token not in seen:
            seen.add(token)
            cleaned.append(token)
    return cleaned
