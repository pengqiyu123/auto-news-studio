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


def _normalize_alias(value: str) -> str:
    compact = re.sub(r"\s+", " ", str(value or "").strip())
    if not compact:
        return ""
    return ALIAS_MAP.get(compact.lower(), compact)


def entity_type_for_name(name: str) -> str:
    canonical = _normalize_alias(name)
    if not canonical:
        return "ORG"
    return str(CANONICAL_ENTITIES.get(canonical) or "ORG")


def entity_id_for_name(name: str) -> str:
    canonical = _normalize_alias(name)
    return md5(canonical.encode("utf-8")).hexdigest()[:12]


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
