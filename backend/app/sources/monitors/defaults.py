from __future__ import annotations

from typing import Any


def _yt(
    key: str,
    name: str,
    handle: str,
    *,
    priority: int,
    schedule: str = "*/60 * * * *",
    tags: list[str] | None = None,
    weight: float | None = None,
) -> dict[str, Any]:
    return {
        "key": key,
        "name": name,
        "platform": "youtube",
        "kind": "monitor",
        "driver": "youtube_channel",
        "enabled": True,
        "schedule": schedule,
        "interval_minutes": 60,
        "priority": priority,
        "weight": weight if weight is not None else 0.8,
        "auth": {"handle": handle},
        "url": f"https://www.youtube.com/@{handle}",
        "tags": tags or [],
        "capabilities": ["pull", "dedupe", "score"],
        "origin_repo": "auto-news-studio",
        "origin_license": "MIT",
        "health_status": "idle",
        "health_detail": "",
        "item_count": 0,
        "last_synced_at": None,
        "last_error": None,
        "updated_at": None,
    }


def register() -> list[dict[str, Any]]:
    return [
        # ── AI 平台 ──
        _yt("yt-openai", "OpenAI", "OpenAI", priority=9, tags=["ai", "official"], weight=0.9),
        _yt("yt-anthropic", "Anthropic (Claude)", "AnthropicAI", priority=9, tags=["ai", "official"], weight=0.9),
        _yt("yt-google", "Google", "google", priority=9, tags=["tech", "official"], weight=0.9),
        _yt("yt-deepmind", "Google DeepMind", "GoogleDeepMind", priority=9, tags=["ai", "research"], weight=0.9),
        _yt("yt-deepseek", "DeepSeek", "deepseek_ai", priority=8, tags=["ai", "cn"], weight=0.85),
        _yt("yt-meta", "Meta AI", "meta", priority=8, tags=["ai", "official"], weight=0.85),
        _yt("yt-mistral", "Mistral AI", "MistralAI", priority=8, tags=["ai", "official"], weight=0.85),
        _yt("yt-huggingface", "Hugging Face", "huggingface", priority=8, tags=["ai", "oss"], weight=0.85),
        _yt("yt-xai", "xAI (Grok)", "xaboratory", priority=8, tags=["ai", "official"], weight=0.85),
        _yt("yt-nvidia", "NVIDIA", "NVIDIA", priority=8, tags=["ai", "chip"], weight=0.85),
        _yt("yt-perplexity", "Perplexity", "perplexityai", priority=7, tags=["ai", "search"], weight=0.8),
        _yt("yt-cohere", "Cohere", "cohereai", priority=7, tags=["ai", "nlp"], weight=0.75),
        _yt("yt-stability", "Stability AI", "StabilityAI", priority=7, tags=["ai", "gen"], weight=0.75),
        _yt("yt-ibm", "IBM (watsonx)", "IBMTechnology", priority=7, tags=["ai", "enterprise"], weight=0.75),
        # ── 手机品牌 ──
        _yt("yt-apple", "Apple", "Apple", priority=9, tags=["phone", "official"], weight=0.9),
        _yt("yt-samsung", "Samsung", "Samsung", priority=8, tags=["phone", "official"], weight=0.85),
        _yt("yt-xiaomi", "Xiaomi", "Xiaomi", priority=8, tags=["phone", "cn"], weight=0.85),
        _yt("yt-oppo", "OPPO", "OPPO", priority=7, tags=["phone", "cn"], weight=0.8),
        _yt("yt-oneplus", "OnePlus", "oneplus", priority=7, tags=["phone", "cn"], weight=0.8),
        _yt("yt-vivo", "vivo", "vivo", priority=7, tags=["phone", "cn"], weight=0.8),
        _yt("yt-huawei", "Huawei", "Huawei", priority=8, tags=["phone", "cn", "chip"], weight=0.85),
        _yt("yt-honor", "Honor", "HonorOfficial", priority=7, tags=["phone", "cn"], weight=0.8),
        _yt("yt-nothing", "Nothing", "Nothing", priority=7, tags=["phone", "design"], weight=0.75),
        _yt("yt-googlepixel", "Google Pixel", "GooglePixel", priority=7, tags=["phone", "official"], weight=0.8),
        _yt("yt-motorola", "Motorola", "motorola", priority=6, tags=["phone"], weight=0.75),
        _yt("yt-realme", "Realme", "realmemobile", priority=6, tags=["phone", "cn"], weight=0.75),
        # ── 芯片品牌 ──
        _yt("yt-qualcomm", "Qualcomm", "Qualcomm", priority=8, tags=["chip", "mobile"], weight=0.85),
        _yt("yt-mediatek", "MediaTek", "MediaTekInc", priority=8, tags=["chip", "mobile"], weight=0.85),
        _yt("yt-intel", "Intel", "Intel", priority=8, tags=["chip", "official"], weight=0.85),
        _yt("yt-amd", "AMD", "AMD", priority=8, tags=["chip", "official"], weight=0.85),
        _yt("yt-arm", "ARM", "ARM", priority=7, tags=["chip", "ip"], weight=0.8),
        _yt("yt-applesilicon", "Apple Silicon", "apple", priority=7, tags=["chip", "official"], weight=0.8),
        # ── 数码评测 ──
        _yt("yt-mkbhd", "MKBHD", "mkbhd", priority=8, tags=["tech", "review"], weight=0.85),
        _yt("yt-googletech", "Google Tech", "GoogleTechDevelopers", priority=7, tags=["tech", "dev"], weight=0.8),
        _yt("yt-linus", "Linus Tech Tips", "LinusTechTips", priority=7, tags=["tech", "review"], weight=0.8),
    ]
