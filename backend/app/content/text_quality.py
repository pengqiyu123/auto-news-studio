"""Text quality scoring utilities for article critique."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .briefing import _AI_STYLE_BANNED_PHRASES


@dataclass(frozen=True)
class TextQualityReport:
    burstiness_score: float
    avg_sentence_length: float
    sentence_count: int
    banned_phrase_hits: list[str]
    banned_phrase_count: int
    paragraph_count: int
    avg_paragraph_length: float
    passed: bool


_SENTENCE_PATTERN = re.compile(r"[。！？；\.\!\?;]+")
_PARAGRAPH_SPLIT = re.compile(r"\n\s*\n|\n")
_AI_FILLER = re.compile(
    r"(接下来我们|让我们|下面将|本文将从|综上所述|总而言之|总的来说|"
    r"值得注意的是|与此同时|不难发现|由此可见|毫无疑问|"
    r"不言而喻|不可或缺|蓬勃发展|与日俱增|日新月异)"
)


def score_text_quality(text: str, *, max_banned: int = 3, min_burstiness: float = 0.4) -> TextQualityReport:
    """Score article text for burstiness (sentence-length variance) and AI-style markers."""
    sentences = [s.strip() for s in _SENTENCE_PATTERN.split(text) if s.strip() and len(s.strip()) > 2]
    paragraphs = [p.strip() for p in _PARAGRAPH_SPLIT.split(text) if p.strip()]

    if not sentences:
        return TextQualityReport(
            burstiness_score=0, avg_sentence_length=0, sentence_count=0,
            banned_phrase_hits=[], banned_phrase_count=0,
            paragraph_count=len(paragraphs), avg_paragraph_length=0, passed=False,
        )

    lengths = [len(s) for s in sentences]
    avg_len = sum(lengths) / len(lengths)
    variance = sum((length - avg_len) ** 2 for length in lengths) / len(lengths)
    std_dev = variance**0.5
    burstiness = std_dev / avg_len if avg_len > 0 else 0

    banned_hits: list[str] = []
    for phrase in _AI_STYLE_BANNED_PHRASES:
        try:
            if re.search(phrase, text):
                banned_hits.append(phrase)
        except re.error:
            if phrase in text:
                banned_hits.append(phrase)

    for m in _AI_FILLER.finditer(text):
        hit = m.group(0)
        if hit not in banned_hits:
            banned_hits.append(hit)

    avg_para_len = sum(len(p) for p in paragraphs) / len(paragraphs) if paragraphs else 0

    passed = len(banned_hits) <= max_banned and burstiness >= min_burstiness

    return TextQualityReport(
        burstiness_score=round(burstiness, 3),
        avg_sentence_length=round(avg_len, 1),
        sentence_count=len(sentences),
        banned_phrase_hits=banned_hits,
        banned_phrase_count=len(banned_hits),
        paragraph_count=len(paragraphs),
        avg_paragraph_length=round(avg_para_len, 1),
        passed=passed,
    )
