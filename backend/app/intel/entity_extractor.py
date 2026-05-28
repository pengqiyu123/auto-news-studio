from __future__ import annotations

from hashlib import md5
import logging
import re
from typing import Any

from .entity_aliases import ALIAS_MAP
from .entity_types import CANONICAL_ENTITIES

try:
    import spacy  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    spacy = None


logger = logging.getLogger(__name__)
_NLP_UNSET = object()
_NLP: Any = _NLP_UNSET
_KEYWORD_ENTITIES = {**{name.lower(): name for name in CANONICAL_ENTITIES}, **ALIAS_MAP}
_ALLOWED_SPACY_LABELS = {"ORG", "PERSON", "PRODUCT", "EVENT", "GPE"}


APPLE_CONTEXT_KEYWORDS = {
    "ai",
    "airpods",
    "airtag",
    "app store",
    "apple arcade",
    "apple intelligence",
    "apple tv",
    "apple vision",
    "apple watch",
    "ios",
    "ipad",
    "iphone",
    "mac",
    "macbook",
    "macos",
    "siri",
    "visionos",
    "watchos",
    "官网",
    "以旧换新",
    "发布",
    "智能手机",
    "系统",
    "芯片",
}

OFFICIAL_SOURCE_HINTS = {
    "newsroom",
    "官方",
    "官网",
}

WATCHLIST_ALIAS_MAP: dict[str, tuple[str, ...]] = {
    "Apple": ("苹果", "苹果公司"),
    "Samsung": ("三星", "三星电子", "三星半导体"),
    "Xiaomi": ("小米", "小米手机"),
    "Huawei": ("华为", "华为终端"),
    "HONOR": ("honor", "honor official", "荣耀", "荣耀手机"),
    "OnePlus": ("oneplus", "one plus", "一加", "一加手机"),
    "ZTE": ("zte", "中兴", "中兴通讯"),
    "vivo": ("vivo", "维沃"),
    "OPPO": ("oppo",),
    "iQOO": ("iqoo",),
    "realme": ("realme", "真我"),
    "Meizu": ("meizu", "魅族"),
    "Lenovo": ("lenovo", "联想"),
    "Motorola": ("motorola", "moto", "摩托罗拉"),
    "Sony": ("sony", "索尼"),
    "Nokia": ("nokia", "诺基亚"),
    "LG": ("lg",),
    "Transsion": ("transsion", "传音"),
    "Baidu": ("baidu", "百度"),
    "ByteDance": ("bytedance", "字节跳动"),
    "Alibaba": ("alibaba", "阿里巴巴"),
    "Tencent": ("tencent", "腾讯"),
    "Zhipu AI": ("zhipu ai", "智谱", "智谱 ai", "智谱清言"),
    "iFLYTEK": ("iflytek", "科大讯飞", "讯飞"),
    "DeepSeek": ("deepseek", "深度求索"),
    "Moonshot AI": ("moonshot ai", "月之暗面", "kimi"),
    "MiniMax": ("minimax",),
    "Inspur": ("inspur", "浪潮"),
    "Cambricon": ("cambricon", "寒武纪"),
    "Moore Threads": ("moore threads", "摩尔线程"),
    "Sugon": ("sugon", "中科曙光"),
    "Kuaishou": ("kuaishou", "快手"),
    "Meitu": ("meitu", "美图"),
    "Kingsoft Office": ("kingsoft office", "金山办公"),
    "Megvii": ("megvii", "旷视"),
    "SenseTime": ("sensetime", "商汤"),
    "Yitu": ("yitu", "依图"),
    "CloudWalk": ("cloudwalk", "云从"),
    "Horizon Robotics": ("horizon robotics", "地平线"),
    "Mobvoi": ("mobvoi", "出门问问"),
}


def _normalize_alias(value: str) -> str:
    compact = re.sub(r"\s+", " ", str(value or "").strip())
    if not compact:
        return ""
    return ALIAS_MAP.get(compact.lower(), compact)


def canonical_entity_name(name: str) -> str:
    return _normalize_alias(name)


def entity_type_for_name(name: str) -> str:
    canonical = _normalize_alias(name)
    if not canonical:
        return "ORG"
    return str(CANONICAL_ENTITIES.get(canonical) or "ORG")


def entity_id_for_name(name: str) -> str:
    canonical = _normalize_alias(name)
    return md5(canonical.encode("utf-8")).hexdigest()[:12]


def _compact_key(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).lower()


def _has_context(text: str, keywords: set[str]) -> bool:
    lowered = text.lower()
    return any(keyword.lower() in lowered for keyword in keywords)


def _watchlist_entities(watchlist: list[dict[str, Any]] | None) -> dict[str, dict[str, str]]:
    entities: dict[str, dict[str, str]] = {}
    for raw in watchlist or []:
        if not isinstance(raw, dict) or not raw.get("watchlisted", True):
            continue
        entity_name = str(raw.get("entity_name") or "").strip()
        if not entity_name:
            continue
        canonical = _normalize_alias(entity_name)
        if not canonical:
            continue
        entity_type = str(raw.get("entity_type") or CANONICAL_ENTITIES.get(canonical) or "ORG").strip().upper()
        if not entity_type:
            continue
        entities[_compact_key(entity_name)] = {
            "entity_id": entity_id_for_name(canonical),
            "entity_name": canonical,
            "entity_type": entity_type,
        }
        entities[_compact_key(canonical)] = {
            "entity_id": entity_id_for_name(canonical),
            "entity_name": canonical,
            "entity_type": entity_type,
        }
        for alias in WATCHLIST_ALIAS_MAP.get(canonical, ()):
            entities[_compact_key(alias)] = {
                "entity_id": entity_id_for_name(canonical),
                "entity_name": canonical,
                "entity_type": entity_type,
            }
    return entities


def _source_is_official_for(canonical: str, source_text: str) -> bool:
    if not canonical or not source_text:
        return False
    lowered = source_text.lower()
    canonical_lower = canonical.lower()
    if canonical_lower in lowered and _has_context(lowered, OFFICIAL_SOURCE_HINTS):
        return True
    source_parts = [_compact_key(part) for part in source_text.split("\n") if _compact_key(part)]
    return any(_compact_key(alias) in source_parts for alias in WATCHLIST_ALIAS_MAP.get(canonical, ()))


def _raw_alias_is_ambiguous(raw_alias: str, canonical: str) -> bool:
    return canonical == "Apple" and raw_alias in {"苹果", "苹果公司"}


def _accept_alias_match(*, raw_alias: str, canonical: str, text: str, source_text: str) -> bool:
    if not _raw_alias_is_ambiguous(raw_alias, canonical):
        return True
    return _has_context(text, APPLE_CONTEXT_KEYWORDS) or _source_is_official_for(canonical, source_text)


def entity_match_keys(entity_id: str | None = None, entity_name: str | None = None) -> set[str]:
    keys = {str(entity_id or "").strip()}
    canonical = _normalize_alias(str(entity_name or ""))
    if canonical:
        keys.add(canonical)
        keys.add(canonical.lower())
        keys.add(entity_id_for_name(canonical))
    raw_name = str(entity_name or "").strip()
    if raw_name:
        keys.add(raw_name)
        keys.add(raw_name.lower())
    return {key for key in keys if key}


def _keyword_patterns() -> list[tuple[re.Pattern[str], str]]:
    patterns: list[tuple[re.Pattern[str], str]] = []
    for raw, canonical in sorted(_KEYWORD_ENTITIES.items(), key=lambda item: len(item[0]), reverse=True):
        escaped = re.escape(raw)
        if re.search(r"[A-Za-z0-9]", raw) and not re.search(r"[\u4e00-\u9fff]", raw):
            escaped = escaped.replace(r"\ ", r"\s+")
            pattern = re.compile(rf"(?<![A-Za-z0-9]){escaped}(?![A-Za-z0-9])", re.IGNORECASE)
        else:
            pattern = re.compile(escaped, re.IGNORECASE)
        patterns.append((pattern, canonical))
    return patterns


KEYWORD_PATTERNS = _keyword_patterns()


def _get_nlp():
    global _NLP
    if _NLP is not _NLP_UNSET:
        return _NLP
    if spacy is None:  # pragma: no cover - depends on optional package
        _NLP = None
        return None
    for model_name in ("zh_core_web_lg", "zh_core_web_md"):
        try:
            _NLP = spacy.load(model_name)
            return _NLP
        except Exception:
            continue
    _NLP = None
    return None


def _add_entity(results: dict[str, dict[str, str]], canonical: str, entity_type: str) -> None:
    canonical = _normalize_alias(canonical)
    if not canonical or canonical in results:
        return
    entity_type = str(CANONICAL_ENTITIES.get(canonical) or entity_type or "").strip().upper()
    if not entity_type:
        return
    results[canonical] = {
        "entity_id": entity_id_for_name(canonical),
        "entity_name": canonical,
        "entity_type": entity_type,
    }


def _extract_keyword_entities(content: str, limit: int) -> list[dict[str, str]]:
    results: dict[str, dict[str, str]] = {}
    lowered = content.lower()
    try:
        for pattern, canonical in KEYWORD_PATTERNS:
            if not pattern.search(lowered):
                continue
            entity_type = CANONICAL_ENTITIES.get(canonical)
            if not entity_type:
                continue
            _add_entity(results, canonical, entity_type)
            if len(results) >= limit:
                break
    except Exception:
        logger.warning("entity extraction via keywords failed", exc_info=True)
    return list(results.values())[:limit]


def extract_keyword_entities(text: str, limit: int = 10) -> list[dict[str, str]]:
    content = str(text or "").strip()
    if not content:
        return []
    return _extract_keyword_entities(content, limit)


def extract_entities(text: str, limit: int = 10) -> list[dict[str, str]]:
    content = str(text or "").strip()
    if not content:
        return []
    results: dict[str, dict[str, str]] = {}

    try:
        nlp = _get_nlp()
        if nlp is not None:
            doc = nlp(content[:3000])
            for ent in doc.ents:
                label = str(getattr(ent, "label_", "") or "").upper()
                if label not in _ALLOWED_SPACY_LABELS:
                    continue
                canonical = _normalize_alias(getattr(ent, "text", ""))
                if not canonical:
                    continue
                if canonical in CANONICAL_ENTITIES:
                    _add_entity(results, canonical, CANONICAL_ENTITIES[canonical])
                else:
                    _add_entity(results, canonical, label)
                if len(results) >= limit:
                    return list(results.values())[:limit]
    except Exception:
        logger.warning("entity extraction via spaCy failed", exc_info=True)

    for item in _extract_keyword_entities(content, limit):
        _add_entity(results, str(item.get("entity_name") or ""), str(item.get("entity_type") or ""))
        if len(results) >= limit:
            break

    return list(results.values())[:limit]


def _add_result(results: dict[str, dict[str, str]], entity: dict[str, str], limit: int) -> bool:
    canonical = _normalize_alias(str(entity.get("entity_name") or ""))
    if not canonical:
        return False
    entity_type = str(entity.get("entity_type") or CANONICAL_ENTITIES.get(canonical) or "ORG").strip().upper()
    if not entity_type:
        return False
    results.setdefault(
        canonical,
        {
            "entity_id": entity_id_for_name(canonical),
            "entity_name": canonical,
            "entity_type": entity_type,
        },
    )
    return len(results) >= limit


def extract_entities_with_context(
    text: str,
    *,
    source_name: str | None = None,
    source_key: str | None = None,
    watchlist: list[dict[str, Any]] | None = None,
    limit: int = 10,
) -> list[dict[str, str]]:
    content = str(text or "").strip()
    source_text = "\n".join(part for part in [source_name, source_key] if part)
    haystack = " ".join(part for part in [content, source_text] if part)
    if not haystack:
        return []

    results: dict[str, dict[str, str]] = {}
    watchlist_lookup = _watchlist_entities(watchlist)

    for raw, canonical in sorted(_KEYWORD_ENTITIES.items(), key=lambda item: len(item[0]), reverse=True):
        if not canonical:
            continue
        escaped = re.escape(raw)
        if re.search(r"[A-Za-z0-9]", raw) and not re.search(r"[\u4e00-\u9fff]", raw):
            escaped = escaped.replace(r"\ ", r"\s+")
            pattern = re.compile(rf"(?<![A-Za-z0-9]){escaped}(?![A-Za-z0-9])", re.IGNORECASE)
        else:
            pattern = re.compile(escaped, re.IGNORECASE)
        text_match = pattern.search(content)
        source_match = pattern.search(source_text) and _source_is_official_for(canonical, source_text)
        if not text_match and not source_match:
            continue
        if text_match and not _accept_alias_match(raw_alias=raw, canonical=canonical, text=content, source_text=source_text):
            continue
        entity_type = CANONICAL_ENTITIES.get(canonical)
        if not entity_type:
            continue
        if _add_result(results, {"entity_name": canonical, "entity_type": entity_type}, limit):
            return list(results.values())[:limit]

    for raw_key, entity in sorted(watchlist_lookup.items(), key=lambda item: len(item[0]), reverse=True):
        if not raw_key:
            continue
        escaped = re.escape(raw_key).replace(r"\ ", r"\s+")
        if re.search(r"[a-z0-9]", raw_key) and not re.search(r"[\u4e00-\u9fff]", raw_key):
            pattern = re.compile(rf"(?<![A-Za-z0-9]){escaped}(?![A-Za-z0-9])", re.IGNORECASE)
        else:
            pattern = re.compile(escaped, re.IGNORECASE)
        text_match = pattern.search(content)
        source_match = pattern.search(source_text) and _source_is_official_for(entity["entity_name"], source_text)
        if not text_match and not source_match:
            continue
        if text_match and not _accept_alias_match(raw_alias=raw_key, canonical=entity["entity_name"], text=content, source_text=source_text):
            continue
        if _add_result(results, entity, limit):
            return list(results.values())[:limit]

    for item in extract_entities(content, limit=limit):
        if (
            canonical_entity_name(str(item.get("entity_name") or "")) == "Apple"
            and not _has_context(content, APPLE_CONTEXT_KEYWORDS)
            and not _source_is_official_for("Apple", source_text)
        ):
            continue
        if _add_result(results, item, limit):
            break

    return list(results.values())[:limit]
