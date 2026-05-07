from __future__ import annotations

import argparse
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.connectors import USER_AGENT, collect_from_source  # noqa: E402


REQUEST_TIMEOUT_SECONDS = 8
MAX_WORKERS = 8
DEFAULT_OUTPUT_DIR = ROOT / "runtime" / "brand-source-audit"
COMMON_FEED_SUFFIXES = (
    "feed",
    "rss.xml",
    "atom.xml",
    "blog/rss.xml",
    "news/rss.xml",
    "press/feed",
)


@dataclass(frozen=True)
class BrandEntry:
    name: str
    category: str
    tier: str
    search_urls: tuple[str, ...]
    aliases: tuple[str, ...] = ()
    extra_candidates: tuple[tuple[str, str], ...] = ()


@dataclass
class CandidateSource:
    brand: str
    source_name: str
    url: str
    driver: str
    official: bool = True
    discovered_from: str | None = None


@dataclass
class CandidateTestResult:
    brand: str
    source_name: str
    url: str
    driver: str
    ok: bool
    item_count: int
    warning: str | None
    tested_at: str
    recommended_key: str | None = None
    recommended_name: str | None = None
    recommended_schedule: str | None = None
    recommended_priority: int | None = None
    recommended_tags: list[str] = field(default_factory=list)


@dataclass
class BrandAuditResult:
    brand: str
    category: str
    tier: str
    aliases: list[str]
    searched_pages: list[str]
    candidate_sources: list[dict[str, Any]]
    tested_sources: list[dict[str, Any]]
    usable_sources: list[dict[str, Any]]
    status: str
    note: str


def brand(
    name: str,
    category: str,
    tier: str,
    *search_urls: str,
    aliases: tuple[str, ...] = (),
    extra_candidates: tuple[tuple[str, str], ...] = (),
) -> BrandEntry:
    return BrandEntry(
        name=name,
        category=category,
        tier=tier,
        search_urls=tuple(search_urls),
        aliases=aliases,
        extra_candidates=extra_candidates,
    )


BRANDS: tuple[BrandEntry, ...] = (
    brand("Huawei", "digital", "major", "https://www.huawei.com/en/", "https://consumer.huawei.com/en/news/"),
    brand("Xiaomi", "digital", "major", "https://www.mi.com/global/", "https://www.mi.com/global/discover/", aliases=("小米",)),
    brand("OPPO", "digital", "major", "https://www.oppo.com/en/", "https://www.oppo.com/en/newsroom/"),
    brand("vivo", "digital", "major", "https://www.vivo.com/en/", "https://www.vivo.com/en/about-vivo/news"),
    brand("HONOR", "digital", "major", "https://www.honor.com/global/", "https://www.honor.com/global/news/"),
    brand("OnePlus", "digital", "minor", "https://www.oneplus.com/global", "https://www.oneplus.com/global/blog"),
    brand("Meizu", "digital", "minor", "https://www.meizu.com/en/"),
    brand("iQOO", "digital", "minor", "https://www.iqoo.com/en/"),
    brand("realme", "digital", "minor", "https://www.realme.com/global/", "https://www.realme.com/global/newsroom"),
    brand("nubia", "digital", "minor", "https://nubia.com/en/", "https://global.nubia.com/"),
    brand("REDMAGIC", "digital", "minor", "https://global.redmagic.gg/", "https://na.redmagic.gg/blogs/news"),
    brand("Black Shark", "digital", "minor", "https://global.blackshark.com/"),
    brand("ZTE", "digital", "minor", "https://www.zte.com.cn/global/", "https://www.zte.com.cn/global/about/news.html"),
    brand(
        "Lenovo",
        "digital",
        "major",
        "https://news.lenovo.com/",
        "https://www.lenovo.com/us/en/news/",
        extra_candidates=(("rss_feed", "https://news.lenovo.com/feed"),),
    ),
    brand(
        "Apple",
        "digital",
        "major",
        "https://www.apple.com/newsroom/",
        "https://www.apple.com/",
        extra_candidates=(("rss_feed", "https://www.apple.com/newsroom/rss-feed.rss"),),
    ),
    brand(
        "Samsung",
        "digital",
        "major",
        "https://news.samsung.com/global/",
        "https://samsungmobilepress.com/",
        extra_candidates=(("rss_feed", "https://news.samsung.com/global/feed/rss"),),
    ),
    brand(
        "Google",
        "digital",
        "major",
        "https://blog.google/",
        "https://blog.google/technology/",
        extra_candidates=(
            ("rss_feed", "https://blog.google/feed"),
            ("rss_feed", "https://blog.google/innovation-and-ai/technology/ai/rss/"),
        ),
    ),
    brand("Sony", "digital", "major", "https://www.sony.com/en/SonyInfo/News/", "https://www.sony.com/en/"),
    brand("Motorola", "digital", "minor", "https://motorolanews.com/", "https://www.motorola.com/"),
    brand("Nokia", "digital", "minor", "https://www.nokia.com/about-us/newsroom/", "https://www.nokia.com/"),
    brand("LG", "digital", "minor", "https://www.lgnewsroom.com/", "https://www.lg.com/global"),
    brand("Transsion", "digital", "minor", "https://www.transsion.com/en/", "https://www.transsion.com/en/news"),
    brand("Baidu", "cn-ai", "major", "https://www.baidu.com/", "https://ir.baidu.com/news-releases"),
    brand("ByteDance", "cn-ai", "major", "https://newsroom.bytedance.com/", "https://www.bytedance.com/en/"),
    brand(
        "Alibaba",
        "cn-ai",
        "major",
        "https://www.alizila.com/",
        "https://www.alibabagroup.com/en-US/",
        extra_candidates=(("rss_feed", "https://www.alizila.com/feed"),),
    ),
    brand("Tencent", "cn-ai", "major", "https://www.tencent.com/en-us/articles.html", "https://www.tencent.com/en-us/"),
    brand("Zhipu AI", "cn-ai", "major", "https://www.zhipuai.cn/", "https://open.bigmodel.cn/"),
    brand("iFLYTEK", "cn-ai", "major", "https://www.iflytek.com/en/", "https://www.iflytek.com/"),
    brand("DeepSeek", "cn-ai", "major", "https://www.deepseek.com/"),
    brand("Moonshot AI", "cn-ai", "major", "https://www.moonshot.cn/", "https://kimi.ai/"),
    brand("MiniMax", "cn-ai", "major", "https://www.minimaxi.com/en", "https://www.minimaxi.com/"),
    brand("Inspur", "cn-ai", "minor", "https://en.inspur.com/", "https://en.inspur.com/lm/about/news/index.html"),
    brand("Cambricon", "cn-ai", "minor", "https://www.cambricon.com/"),
    brand("MetaX", "cn-ai", "minor", "https://www.metax-tech.com/"),
    brand("Moore Threads", "cn-ai", "minor", "https://www.mthreads.com/"),
    brand("Sugon", "cn-ai", "minor", "https://www.sugon.com/"),
    brand("Kuaishou", "cn-ai", "minor", "https://www.kuaishou.com/new-reco", "https://www.kuaishou.com/"),
    brand("Meitu", "cn-ai", "minor", "https://www.meitu.com/en/", "https://www.meitu.com/"),
    brand("Kingsoft Office", "cn-ai", "minor", "https://www.wps.com/", "https://www.kingsoft.com/"),
    brand("Megvii", "cn-ai", "minor", "https://www.megvii.com/", "https://en.megvii.com/"),
    brand("SenseTime", "cn-ai", "minor", "https://www.sensetime.com/en/", "https://www.sensetime.com/"),
    brand("Yitu", "cn-ai", "minor", "https://www.yitutech.com/en/"),
    brand("CloudWalk", "cn-ai", "minor", "https://www.cloudwalk.com/"),
    brand("Horizon Robotics", "cn-ai", "minor", "https://en.horizon.auto/", "https://www.horizon.auto/"),
    brand("Mobvoi", "cn-ai", "minor", "https://www.mobvoi.com/"),
    brand("AISpeech", "cn-ai", "minor", "https://www.aispeech.com/"),
    brand("StepFun", "cn-ai", "minor", "https://www.stepfun.com/"),
    brand("Doubao", "cn-ai", "minor", "https://www.doubao.com/", "https://www.bytedance.com/en/"),
    brand("ERNIE", "cn-ai", "minor", "https://yiyan.baidu.com/", "https://ir.baidu.com/news-releases"),
    brand("Qwen", "cn-ai", "minor", "https://qwen.ai/", "https://www.alizila.com/"),
    brand("Pangu", "cn-ai", "minor", "https://www.huawei.com/en/", "https://consumer.huawei.com/en/news/"),
    brand("Hunyuan", "cn-ai", "minor", "https://www.tencent.com/en-us/articles.html", "https://www.tencent.com/en-us/"),
    brand("GLM", "cn-ai", "minor", "https://open.bigmodel.cn/", "https://www.zhipuai.cn/"),
    brand("Kimi", "cn-ai", "minor", "https://kimi.ai/", "https://www.moonshot.cn/"),
    brand("Doubao-Seed", "cn-ai", "minor", "https://www.doubao.com/", "https://www.bytedance.com/en/"),
    brand(
        "OpenAI",
        "intl-ai",
        "major",
        "https://openai.com/news/",
        "https://openai.com/blog/",
        extra_candidates=(("rss_feed", "https://openai.com/news/rss.xml"),),
    ),
    brand("Alphabet", "intl-ai", "major", "https://blog.google/", "https://abc.xyz/"),
    brand(
        "Amazon",
        "intl-ai",
        "major",
        "https://www.aboutamazon.com/news",
        "https://aws.amazon.com/blogs/",
        extra_candidates=(("rss_feed", "https://www.aboutamazon.com/rss/feed.rss"),),
    ),
    brand("Meta", "intl-ai", "major", "https://ai.meta.com/blog/", "https://about.fb.com/news/"),
    brand("Anthropic", "intl-ai", "major", "https://www.anthropic.com/news", "https://www.anthropic.com/"),
    brand(
        "Mistral AI",
        "intl-ai",
        "major",
        "https://mistral.ai/news/",
        "https://mistral.ai/",
        extra_candidates=(("rss_feed", "https://mistral.ai/news/feed"),),
    ),
    brand(
        "Hugging Face",
        "intl-ai",
        "major",
        "https://huggingface.co/blog",
        "https://huggingface.co/",
        extra_candidates=(("rss_feed", "https://huggingface.co/blog/feed"),),
    ),
    brand(
        "NVIDIA",
        "intl-ai",
        "major",
        "https://blogs.nvidia.com/",
        "https://www.nvidia.com/en-us/",
        extra_candidates=(("rss_feed", "https://blogs.nvidia.com/feed"),),
    ),
    brand(
        "Microsoft",
        "intl-ai",
        "major",
        "https://blogs.microsoft.com/",
        "https://news.microsoft.com/",
        extra_candidates=(
            ("rss_feed", "https://blogs.microsoft.com/feed"),
            ("rss_feed", "https://news.microsoft.com/source/feed"),
        ),
    ),
    brand("IBM", "intl-ai", "minor", "https://newsroom.ibm.com/", "https://research.ibm.com/blog"),
    brand("Salesforce", "intl-ai", "minor", "https://www.salesforce.com/news/", "https://www.salesforce.com/blog/"),
    brand("Cohere", "intl-ai", "minor", "https://cohere.com/blog", "https://cohere.com/"),
    brand("AI21 Labs", "intl-ai", "minor", "https://www.ai21.com/blog", "https://www.ai21.com/"),
    brand("Databricks", "intl-ai", "minor", "https://www.databricks.com/blog", "https://www.databricks.com/company/newsroom"),
    brand("Stability AI", "intl-ai", "minor", "https://stability.ai/news", "https://stability.ai/blog"),
    brand("EleutherAI", "intl-ai", "minor", "https://www.eleuther.ai/", "https://www.eleuther.ai/blog"),
    brand(
        "Google DeepMind",
        "intl-ai",
        "major",
        "https://deepmind.google/discover/blog/",
        "https://deepmind.google/",
        extra_candidates=(("rss_feed", "https://deepmind.google/discover/blog/feed"),),
    ),
    brand("Gemini", "intl-ai", "major", "https://blog.google/technology/google-deepmind/", "https://gemini.google.com/"),
    brand("Claude", "intl-ai", "major", "https://www.anthropic.com/news", "https://www.anthropic.com/"),
    brand("GPT", "intl-ai", "major", "https://openai.com/news/", "https://openai.com/blog/"),
    brand("Llama", "intl-ai", "major", "https://ai.meta.com/blog/", "https://about.fb.com/news/"),
    brand("Copilot", "intl-ai", "major", "https://blogs.microsoft.com/", "https://news.microsoft.com/"),
    brand("DALL·E", "intl-ai", "major", "https://openai.com/news/", "https://openai.com/blog/"),
    brand("Midjourney", "intl-ai", "minor", "https://www.midjourney.com/home", "https://updates.midjourney.com/"),
    brand(
        "Intel",
        "chip",
        "major",
        "https://newsroom.intel.com/",
        "https://www.intel.com/content/www/us/en/newsroom/home.html",
        extra_candidates=(("rss_feed", "https://newsroom.intel.com/feed"),),
    ),
    brand(
        "AMD",
        "chip",
        "major",
        "https://community.amd.com/t5/blogs/bg-p/amd-blogs",
        "https://www.amd.com/en/newsroom",
        extra_candidates=(("rss_feed", "https://community.amd.com/t5/blogs/bg-p/amd-blogs/rss.xml"),),
    ),
    brand("Qualcomm", "chip", "major", "https://www.qualcomm.com/news", "https://www.qualcomm.com/"),
    brand("MediaTek", "chip", "major", "https://corp.mediatek.com/news-events/press-releases", "https://www.mediatek.com/"),
    brand("UNISOC", "chip", "minor", "https://www.unisoc.com/en_us/", "https://www.unisoc.com/en_us/news_center"),
    brand("Intel Arc", "chip", "minor", "https://newsroom.intel.com/", "https://www.intel.com/content/www/us/en/newsroom/home.html"),
    brand("Kirin", "chip", "minor", "https://www.huawei.com/en/", "https://consumer.huawei.com/en/news/"),
    brand("Snapdragon", "chip", "major", "https://www.qualcomm.com/news", "https://www.qualcomm.com/"),
    brand("Dimensity", "chip", "major", "https://corp.mediatek.com/news-events/press-releases", "https://www.mediatek.com/"),
    brand("Apple Silicon", "chip", "major", "https://www.apple.com/newsroom/", "https://www.apple.com/"),
    brand("Exynos", "chip", "minor", "https://news.samsung.com/global/", "https://semiconductor.samsung.com/"),
    brand("Rockchip", "chip", "minor", "https://www.rock-chips.com/a/en/news/"),
    brand("Allwinner", "chip", "minor", "https://www.allwinnertech.com/index.php?c=news"),
    brand("Biren", "chip", "minor", "https://www.birentech.com/"),
    brand("Loongson", "chip", "minor", "https://www.loongson.cn/"),
    brand("GigaDevice", "chip", "minor", "https://www.gigadevice.com/"),
    brand("CXMT", "chip", "minor", "https://www.cxmt.com/"),
    brand(
        "ASUS",
        "hardware",
        "minor",
        "https://press.asus.com/",
        "https://www.asus.com/news/",
        extra_candidates=(("rss_feed", "https://press.asus.com/rss.xml"),),
    ),
    brand("Gigabyte", "hardware", "minor", "https://www.gigabyte.com/Press/News", "https://www.gigabyte.com/"),
    brand("MSI", "hardware", "minor", "https://www.msi.com/news", "https://www.msi.com/"),
    brand("Colorful", "hardware", "minor", "https://en.colorful.cn/en/home/news", "https://en.colorful.cn/"),
    brand("GALAX", "hardware", "minor", "https://www.galax.com/en/news", "https://www.galax.com/"),
    brand("ZOTAC", "hardware", "minor", "https://www.zotac.com/news", "https://www.zotac.com/"),
    brand("Sapphire", "hardware", "minor", "https://www.sapphiretech.com/en/news", "https://www.sapphiretech.com/"),
    brand("PowerColor", "hardware", "minor", "https://www.powercolor.com/news", "https://www.powercolor.com/"),
    brand("Gainward", "hardware", "minor", "https://www.gainward.com/main/news", "https://www.gainward.com/"),
    brand("Maxsun", "hardware", "minor", "https://www.maxsun.com/"),
    brand("Yeston", "hardware", "minor", "https://www.yeston.net/"),
    brand("Biostar", "hardware", "minor", "https://www.biostar.com.tw/app/en/news/", "https://www.biostar.com.tw/"),
    brand(
        "EVGA",
        "hardware",
        "minor",
        "https://www.evga.com/articles/",
        "https://www.evga.com/",
        extra_candidates=(("rss_feed", "https://www.evga.com/rss/rss.ashx"),),
    ),
    brand("ASRock", "hardware", "minor", "https://www.asrock.com/news/", "https://www.asrock.com/"),
    brand("Kingston", "hardware", "minor", "https://www.kingston.com/en/blog", "https://www.kingston.com/"),
    brand(
        "Western Digital",
        "hardware",
        "minor",
        "https://blog.westerndigital.com/",
        "https://www.westerndigital.com/company/newsroom",
        extra_candidates=(("rss_feed", "https://blog.westerndigital.com/feed"),),
    ),
    brand("Kioxia", "hardware", "minor", "https://www.kioxia.com/en-jp/about/news.html", "https://www.kioxia.com/"),
    brand("Corsair", "hardware", "minor", "https://www.corsair.com/us/en/explorer/", "https://www.corsair.com/"),
    brand("G.Skill", "hardware", "minor", "https://www.gskill.com/news", "https://www.gskill.com/"),
    brand("ADATA", "hardware", "minor", "https://www.adata.com/en/news/", "https://www.adata.com/"),
    brand("Gloway", "hardware", "minor", "https://www.gloway.com/"),
    brand("ZhiTai", "hardware", "minor", "https://www.ymtc.com/"),
    brand("FanXiang", "hardware", "minor", "https://www.fanxiangssd.com/"),
    brand("Kingbank", "hardware", "minor", "https://www.kingbank.com/"),
    brand("aigo", "hardware", "minor", "https://www.aigo.com/"),
    brand("Huntkey", "hardware", "minor", "https://en.huntkey.com/", "https://www.huntkey.com/"),
    brand("Great Wall", "hardware", "minor", "https://www.greatwall.cn/"),
    brand("Seasonic", "hardware", "minor", "https://seasonic.com/news/", "https://seasonic.com/"),
    brand("Super Flower", "hardware", "minor", "https://www.super-flower.com.tw/"),
    brand("Cooler Master", "hardware", "minor", "https://www.coolermaster.com/en-global/newsroom/", "https://www.coolermaster.com/"),
    brand(
        "Thermalright",
        "hardware",
        "minor",
        "https://www.thermalright.com/",
        extra_candidates=(("rss_feed", "https://www.thermalright.com/feed"),),
    ),
    brand("DeepCool", "hardware", "minor", "https://www.deepcool.com/"),
    brand("SAMA", "hardware", "minor", "https://www.sama.cn/"),
)


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "source"


def suggest_priority(tier: str, category: str) -> int:
    if tier == "major":
        return 9 if category in {"intl-ai", "cn-ai"} else 8
    if category in {"intl-ai", "cn-ai", "chip"}:
        return 7
    return 6


def suggest_schedule(tier: str, category: str) -> str:
    if tier == "major":
        return "*/20 * * * *"
    if category in {"intl-ai", "cn-ai"}:
        return "*/30 * * * *"
    return "0 */1 * * *"


def suggest_tags(entry: BrandEntry) -> list[str]:
    tags = [entry.category, "official", "brand"]
    if entry.category in {"intl-ai", "cn-ai"}:
        tags.insert(0, "ai")
    if entry.category == "chip":
        tags.insert(0, "chip")
    if entry.category == "digital":
        tags.insert(0, "digital")
    return tags


def fetch_text(url: str, timeout: int = REQUEST_TIMEOUT_SECONDS) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=timeout) as response:  # noqa: S310 - controlled brand URLs
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="ignore")


def dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        compact = value.strip()
        if not compact:
            continue
        key = compact.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(compact)
    return result


def page_origin(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def canonicalize_candidate_url(url: str) -> str:
    compact = url.strip()
    if compact.endswith("/"):
        compact = compact[:-1]
    compact = compact.replace("/feed.xml", "/feed")
    return compact


def extract_feed_links(html: str, base_url: str) -> list[str]:
    results: list[str] = []
    for href in re.findall(r"""<link[^>]+type=["']application/(?:rss\+xml|atom\+xml|xml)["'][^>]+href=["']([^"']+)["']""", html, re.IGNORECASE):
        results.append(urljoin(base_url, href))
    for href in re.findall(r"""<a[^>]+href=["']([^"']+)["']""", html, re.IGNORECASE):
        lowered = href.lower()
        if any(token in lowered for token in ("/feed", "/rss", "rss.xml", "atom.xml", "feed.xml")):
            results.append(urljoin(base_url, href))
    return dedupe_strings(results)


def looks_like_wordpress(html: str) -> bool:
    lowered = html.lower()
    return "wp-content" in lowered or "wp-json" in lowered or "wordpress" in lowered


def build_seed_feed_urls(url: str) -> list[str]:
    base = url.rstrip("/")
    return [f"{base}/{suffix}" for suffix in COMMON_FEED_SUFFIXES]


def discover_candidates(entry: BrandEntry) -> tuple[list[str], list[CandidateSource]]:
    searched_pages: list[str] = []
    candidates: list[CandidateSource] = []
    seen_urls: set[tuple[str, str]] = set()

    def add_candidate(driver: str, url: str, discovered_from: str | None) -> None:
        canonical_url = canonicalize_candidate_url(url)
        key = (driver, canonical_url)
        if key in seen_urls:
            return
        seen_urls.add(key)
        candidates.append(
            CandidateSource(
                brand=entry.name,
                source_name=f"{entry.name} Official {driver.upper()}",
                url=canonical_url,
                driver=driver,
                discovered_from=discovered_from,
            )
        )

    for driver, url in entry.extra_candidates:
        add_candidate(driver, url, "manual_verified")

    for search_url in entry.search_urls:
        searched_pages.append(search_url)
        seeded_feed_urls = build_seed_feed_urls(search_url)
        try:
            html = fetch_text(search_url)
        except Exception:
            for feed_url in seeded_feed_urls:
                add_candidate("rss_feed", feed_url, search_url)
            continue
        discovered_feed_urls = extract_feed_links(html, search_url)
        for feed_url in discovered_feed_urls:
            add_candidate("rss_feed", feed_url, search_url)
        if not discovered_feed_urls:
            for feed_url in seeded_feed_urls:
                add_candidate("rss_feed", feed_url, search_url)
        if looks_like_wordpress(html):
            add_candidate("wordpress_rest", page_origin(search_url), search_url)

    return dedupe_strings(searched_pages), candidates


def test_candidate(entry: BrandEntry, candidate: CandidateSource) -> CandidateTestResult:
    tested_at = datetime.now(UTC).replace(microsecond=0).isoformat()
    source = {
        "key": f"audit-{slugify(entry.name)}",
        "name": candidate.source_name,
        "kind": "rss" if candidate.driver == "rss_feed" else "api",
        "driver": candidate.driver,
        "platform": "rss" if candidate.driver == "rss_feed" else "wordpress",
        "enabled": True,
        "schedule": suggest_schedule(entry.tier, entry.category),
        "priority": suggest_priority(entry.tier, entry.category),
        "weight": 0.7,
        "auth": {},
        "url": candidate.url,
        "tags": suggest_tags(entry),
        "capabilities": ["pull", "dedupe", "score"],
        "origin_repo": "auto-news-studio",
        "origin_license": "MIT",
    }
    items, warning = collect_from_source(source)
    ok = bool(items) and not warning
    result = CandidateTestResult(
        brand=entry.name,
        source_name=candidate.source_name,
        url=candidate.url,
        driver=candidate.driver,
        ok=ok,
        item_count=len(items),
        warning=warning,
        tested_at=tested_at,
    )
    if ok:
        result.recommended_key = f"official-{slugify(entry.name)}-{slugify(candidate.driver.replace('_rest', ''))}"
        result.recommended_name = f"{entry.name} Official"
        result.recommended_schedule = suggest_schedule(entry.tier, entry.category)
        result.recommended_priority = suggest_priority(entry.tier, entry.category)
        result.recommended_tags = suggest_tags(entry)
    return result


def audit_brand(entry: BrandEntry) -> BrandAuditResult:
    searched_pages, candidates = discover_candidates(entry)
    tested_results = [test_candidate(entry, candidate) for candidate in candidates]
    usable_results = [item for item in tested_results if item.ok]

    if usable_results:
        status = "有"
        note = "找到当前可直连的官方源。"
    elif candidates:
        status = "没有"
        note = "找到官方候选页，但当前驱动均未验证通过。"
    else:
        status = "没有"
        note = "未发现可测试的官方 RSS/Atom 或 WordPress 候选。"

    return BrandAuditResult(
        brand=entry.name,
        category=entry.category,
        tier=entry.tier,
        aliases=list(entry.aliases),
        searched_pages=searched_pages,
        candidate_sources=[asdict(item) for item in candidates],
        tested_sources=[asdict(item) for item in tested_results],
        usable_sources=[asdict(item) for item in usable_results],
        status=status,
        note=note,
    )


def render_markdown(results: list[BrandAuditResult]) -> str:
    lines = [
        "# Brand Official Source Audit",
        "",
        f"- Generated at: {datetime.now(UTC).replace(microsecond=0).isoformat()}",
        f"- Total brands: {len(results)}",
        f"- Brands with usable official sources: {len([item for item in results if item.usable_sources])}",
        "",
    ]
    for result in results:
        lines.append(f"## {result.brand}")
        lines.append("")
        lines.append(f"- Status: {result.status}")
        lines.append(f"- Category: `{result.category}`")
        lines.append(f"- Tier: `{result.tier}`")
        lines.append(f"- Note: {result.note}")
        if result.usable_sources:
            lines.append("- Usable sources:")
            for source in result.usable_sources:
                lines.append(f"  `{source['driver']}` {source['url']} (items={source['item_count']}, key={source.get('recommended_key') or '-'})")
        elif result.tested_sources:
            lines.append("- Tested sources:")
            for source in result.tested_sources[:5]:
                warning = source.get("warning") or "no items"
                lines.append(f"  `{source['driver']}` {source['url']} -> {warning}")
        else:
            lines.append("- Tested sources: none")
        lines.append("")
    return "\n".join(lines)


def filter_brands(names: list[str] | None) -> list[BrandEntry]:
    if not names:
        return list(BRANDS)
    wanted = {name.strip().lower() for name in names if name.strip()}
    results: list[BrandEntry] = []
    for entry in BRANDS:
        variants = {entry.name.lower(), *(alias.lower() for alias in entry.aliases)}
        if variants & wanted:
            results.append(entry)
    return results


def write_outputs(results: list[BrandAuditResult], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "brand_sources_latest.json"
    md_path = output_dir / "brand_sources_latest.md"
    payload = {
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "total_brands": len(results),
        "brands_with_usable_sources": len([item for item in results if item.usable_sources]),
        "results": [asdict(item) for item in results],
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(results), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Discover and validate official brand sources for Auto News Studio.")
    parser.add_argument("--brand", action="append", help="Run only for a specific brand name or alias. Repeatable.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Directory for JSON and Markdown reports.")
    parser.add_argument("--workers", type=int, default=MAX_WORKERS, help="Parallel worker count.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    entries = filter_brands(args.brand)
    if not entries:
        print("No matching brands found.")
        return 1

    results_by_brand: dict[str, BrandAuditResult] = {}
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        futures = {executor.submit(audit_brand, entry): entry for entry in entries}
        for future in as_completed(futures):
            result = future.result()
            results_by_brand[result.brand] = result
            usable_count = len(result.usable_sources)
            status_label = "usable" if result.usable_sources else "none"
            print(f"[{status_label}] {result.brand}: usable={usable_count} tested={len(result.tested_sources)}")

    ordered_results = [results_by_brand[entry.name] for entry in entries if entry.name in results_by_brand]
    write_outputs(ordered_results, Path(args.output_dir))
    print(f"Saved report to {Path(args.output_dir).resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
