from __future__ import annotations

import json
from pathlib import Path
import subprocess
from typing import Any


PROJECT_ROOT = Path(r"D:\python\Auto-news2\projects")
REFERENCES_ROOT = Path(r"D:\python\Auto-news2\auto-news-studio\references")
REFERENCE_FILE = REFERENCES_ROOT / "reference_projects.json"
BORROW_MAP_FILE = REFERENCES_ROOT / "borrow_map.json"


REFERENCE_PROJECTS: list[dict[str, Any]] = [
    {
        "local_name": "TrendRadar-master",
        "upstream_repo": "sansan0/TrendRadar",
        "branch": "master",
        "commit_sha": "ddd3f4dcaf801b656a747e607b6ab9867c9e1ec0",
        "layer": "aggregation",
        "tags": ["monitoring", "scheduler", "hot-topics"],
        "license_name": "GPL-3.0",
        "borrow_mode": "reference_only",
        "borrow_targets": ["监控调度组织方式", "热点监测产品结构"],
    },
    {
        "local_name": "DataCube-AI-Space-main",
        "upstream_repo": "Rswcf/DataCube-AI-Space",
        "branch": "main",
        "commit_sha": "3be7e1d2880dd23b89134ed2d3e372147c917785",
        "layer": "aggregation",
        "tags": ["news-pipeline", "frontend", "classification"],
        "license_name": "unknown",
        "borrow_mode": "reference_only",
        "borrow_targets": ["新闻产品信息架构"],
    },
    {
        "local_name": "Folo-dev",
        "upstream_repo": "RSSNext/Folo",
        "branch": "dev",
        "commit_sha": "18e7f76d6109ee286bae1317b820db06ebfb37da",
        "layer": "discovery",
        "tags": ["rss", "reader", "feed-ux"],
        "license_name": "unknown",
        "borrow_mode": "reference_only",
        "borrow_targets": ["订阅体验"],
    },
    {
        "local_name": "gorse-master",
        "upstream_repo": "gorse-io/gorse",
        "branch": "master",
        "commit_sha": "6822196d7410fe7d6ba1743cb07c7ce4ad25b1bc",
        "layer": "ops",
        "tags": ["ranking", "recommendation", "serving"],
        "license_name": "Apache-2.0",
        "borrow_mode": "reference_only",
        "borrow_targets": ["后续推荐排序"],
    },
    {
        "local_name": "newshub-main",
        "upstream_repo": "Varshithvhegde/newshub",
        "branch": "main",
        "commit_sha": "594abfb9aff4b5987fd25bd7822ff58e12eed77f",
        "layer": "aggregation",
        "tags": ["dashboard", "news-aggregation"],
        "license_name": "MIT",
        "borrow_mode": "reference_only",
        "borrow_targets": ["前端新闻工作台"],
    },
    {
        "local_name": "ai_news_rss_summarizer-main",
        "upstream_repo": "gth-ai/ai_news_rss_summarizer",
        "branch": "main",
        "commit_sha": "211733dcecb16cf3da770f362a927fb3972b7419",
        "layer": "writing",
        "tags": ["summary", "rss", "prototype"],
        "license_name": "MIT",
        "borrow_mode": "reference_only",
        "borrow_targets": ["轻量摘要原型"],
    },
    {
        "local_name": "onefilellm-main",
        "upstream_repo": "jimmc414/onefilellm",
        "branch": "main",
        "commit_sha": "99c51a2cbe8cc01c0db037a9f800ca31fae9c2cd",
        "layer": "ops",
        "tags": ["context-packing", "ingestion"],
        "license_name": "MIT",
        "borrow_mode": "reference_only",
        "borrow_targets": ["上下文整理"],
    },
    {
        "local_name": "RSSHub-master",
        "upstream_repo": "DIYgod/RSSHub",
        "branch": "master",
        "layer": "discovery",
        "tags": ["routing", "rss-generator"],
        "license_name": "MIT",
        "borrow_mode": "reference_only",
        "borrow_targets": ["RSS 路由思路"],
    },
    {
        "local_name": "newsnow-main",
        "upstream_repo": "ourongxing/newsnow",
        "branch": "main",
        "layer": "aggregation",
        "tags": ["hot-pool", "real-time"],
        "license_name": "MIT",
        "borrow_mode": "ported",
        "borrow_targets": ["来源注册表", "热点连接器模式", "RSS 解析思路"],
    },
    {
        "local_name": "AIWriteX-main",
        "upstream_repo": "unknown/AIWriteX",
        "branch": "main",
        "layer": "writing",
        "tags": ["workflow", "writing"],
        "license_name": "Apache-2.0 + NOTICE",
        "borrow_mode": "reference_only",
        "borrow_targets": ["统一工作流编排"],
    },
    {
        "local_name": "md2wechat-skill",
        "upstream_repo": "local/md2wechat-skill",
        "branch": "main",
        "layer": "wechat",
        "tags": ["markdown", "wechat-draft"],
        "license_name": "local",
        "borrow_mode": "reference_only",
        "borrow_targets": ["草稿箱流程"],
    },
    {
        "local_name": "wechat-publisher-mcp",
        "upstream_repo": "local/wechat-publisher-mcp",
        "branch": "main",
        "layer": "wechat",
        "tags": ["mcp", "publisher"],
        "license_name": "MIT",
        "borrow_mode": "direct_copy",
        "borrow_targets": ["Markdown 转微信 HTML", "公众号草稿结构处理"],
    },
    {
        "local_name": "Wechatsync",
        "upstream_repo": "wechatsync/Wechatsync",
        "branch": "master",
        "layer": "wechat",
        "tags": ["sync", "multi-platform"],
        "license_name": "GPL-3.0",
        "borrow_mode": "reference_only",
        "borrow_targets": ["适配器抽象", "微信编辑页识别"],
    },
    {
        "local_name": "wiseflow-master",
        "upstream_repo": "unknown/wiseflow",
        "branch": "main",
        "layer": "ops",
        "tags": ["automation", "agents"],
        "license_name": "unknown",
        "borrow_mode": "reference_only",
        "borrow_targets": ["自动化运行模式"],
    },
    {
        "local_name": "auto-news",
        "upstream_repo": "local/auto-news",
        "branch": "main",
        "layer": "writing",
        "tags": ["legacy", "source-manager", "collab"],
        "license_name": "local",
        "borrow_mode": "direct_copy",
        "borrow_targets": ["异步抓取", "去重聚类", "四阶段写作链"],
    },
]


def _git_sha(path: Path) -> str | None:
    if not (path / ".git").exists():
        return None
    try:
        completed = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
        return completed.stdout.strip()
    except Exception:
        return None


def collect_reference_projects() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for item in REFERENCE_PROJECTS:
        local_name = item["local_name"]
        local_path = Path(r"D:\python\auto-news") if local_name == "auto-news" else PROJECT_ROOT / local_name
        local_exists = local_path.exists()
        local_sha = _git_sha(local_path)
        sha = local_sha or item.get("commit_sha")
        refresh_status = "ready" if local_exists else "missing"
        notes = None
        if local_exists and not local_sha and local_name in {
            "Folo-dev",
            "gorse-master",
            "newshub-main",
            "ai_news_rss_summarizer-main",
            "onefilellm-main",
        }:
            refresh_status = "updated"
            notes = "已通过源码压缩包刷新，本地目录不保留 git 历史。"
        items.append(
            {
                **item,
                "commit_sha": sha,
                "refreshed_at": None,
                "refresh_status": refresh_status,
                "notes": notes,
                "local_exists": local_exists,
            }
        )
    return items


def write_reference_baseline() -> list[dict[str, Any]]:
    items = collect_reference_projects()
    REFERENCES_ROOT.mkdir(parents=True, exist_ok=True)
    REFERENCE_FILE.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    borrow_map = [
        {
            "local_name": item["local_name"],
            "borrow_mode": item["borrow_mode"],
            "license_name": item["license_name"],
            "borrow_targets": item["borrow_targets"],
            "upstream_repo": item["upstream_repo"],
        }
        for item in items
    ]
    BORROW_MAP_FILE.write_text(json.dumps(borrow_map, ensure_ascii=False, indent=2), encoding="utf-8")
    return items
