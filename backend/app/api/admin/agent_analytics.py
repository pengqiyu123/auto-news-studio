"""
Title optimization feedback loop for WeChat article publishing.

Generates analytics from publish history to guide LLM-based title/content improvements.
Report format: Markdown for easy consumption by external AI agents.

Loop:
  publish_history → analytics → agent,articles (with optimized title hints)
"""

from datetime import datetime, UTC

from fastapi import APIRouter

from ...store.base import read_json_file, resolve_existing_state_file

router = APIRouter(prefix="/api/admin/agent/analytics")


@router.post("/title-optimization")
def analyze_publish_history_for_title_optimization() -> dict:
    """
    Generate a title/content optimization report based on publish history.

    Returns a Markdown report that external AI can use to:
    - Analyze successful article patterns (title length, structure, emotional tone)
    - Compare metrics (read vs like vs share vs recommend vs comment)
    - Extract high-performing article examples as templates for AI

    Response:
    ```json
    {
      "report": "# 标题优化分析报告\n\n##...",
      "high_performers": [...],
      "stats": {...}
    }
    ```

    The Markdown report includes:
    1. Summary statistics
    2. High-performer examples (with features)
    3. Content patterns analysis
    4. Actionable recommendations
    """

    try:
        # Load state with publish history
        state_file = resolve_existing_state_file()
        state = read_json_file(state_file)
        # Read from browser.wechat.last_publish_history_check
        browser_state = state.get("browser", {})
        history_check = browser_state.get("wechat", {}).get("last_publish_history_check", {})
        published_list = history_check.get("items", [])
    except Exception as e:
        return {
            "error": f"Failed to load publish history: {str(e)}",
            "report": "# 标题优化分析报告\n\n加载历史数据失败。",
            "high_performers": [],
            "stats": {},
        }

    if not published_list:
        return {
            "error": "No publish history available",
            "report": "# 标题优化分析报告\n\n暂无发布历史数据。",
            "high_performers": [],
            "stats": {},
        }

    # Analyze all articles - normalize None values
    for article in published_list:
        for key in ("read_count", "like_count", "share_count", "recommend_count", "comment_count"):
            if article.get(key) is None:
                article[key] = 0

    total_articles = len(published_list)
    sampled = published_list[-50:]  # Focus on recent 50 for fresh insights

    # Compute key metrics
    high_performers = []
    for article in sampled:
        score = (
            article.get("read_count", 0) * 0.4
            + article.get("like_count", 0) * 0.3
            + article.get("share_count", 0) * 0.2
            + article.get("recommend_count", 0) * 0.1
        )
        article["_score"] = score

    sampled.sort(key=lambda x: x["_score"], reverse=True)
    high_performers = sampled[:10]  # Top 10 performers for templates

    # Generate Markdown report
    report = _generate_markdown_report(total_articles, high_performers)

    return {
        "report": report,
        "high_performers": [
            {
                "title": h.get("title"),
                "url": h.get("url"),
                "published_at": h.get("published_at"),
                "read_count": h.get("read_count"),
                "like_count": h.get("like_count"),
                "share_count": h.get("share_count"),
                "recommend_count": h.get("recommend_count"),
                "comment_count": h.get("comment_count"),
                "combined_score": h.get("_score", 0),
            }
            for h in high_performers
        ],
        "stats": {
            "total_articles": total_articles,
            "high_performer_count": len(high_performers),
            "avg_read": sum(h.get("read_count", 0) for h in sampled) / len(sampled) if sampled else 0,
            "avg_share": sum(h.get("share_count", 0) for h in sampled) / len(sampled) if sampled else 0,
            "avg_comment": sum(h.get("comment_count", 0) for h in sampled) / len(sampled) if sampled else 0,
        },
    }


def _generate_markdown_report(total_articles: int, high_performers: list[dict]) -> str:
    """Generate a Markdown-style analysis report."""

    lines = []

    # Header
    lines.append("# 标题优化分析报告")
    lines.append(f"\n**生成时间**: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"**历史文章数**: {total_articles}")
    lines.append(f"**参考样本**: 最近 50 篇")

    # Performance summary
    if high_performers:
        lines.append("\n## 🎯 表现最佳文章 (10篇)")
        lines.append("\n用于 AI 模仿样本，提取标题和内容模式：\n")

        for i, article in enumerate(high_performers, 1):
            lines.append(f"### {i}. {article.get('title', 'N/A')}")
            lines.append(f"**发布时间**: {article.get('published_at', 'N/A')}")
            lines.append(f"\n**数据**:")
            lines.append(f"  - 阅读: {article.get('read_count', 0):,} | 点赞: {article.get('like_count', 0):,} | ")
            lines.append(f"  - 分享: {article.get('share_count', 0):,} | 推荐: {article.get('recommend_count', 0):,} | ")
            lines.append(f"  - 留言: {article.get('comment_count', 0):,}")
            lines.append(f"\n**综合得分**: {article.get('_score', 0):.1f}")
            lines.append(f"\n**文章链接**: {article.get('url', 'N/A')}\n")
    else:
        lines.append("\n## 📊 数据不足")

    # Title pattern analysis
    lines.append("## 📝 标题模式分析\n")
    lines.append("从高表现文章中提取的标题特征：\n")

    if high_performers:
        all_titles = [h.get("title", "") for h in high_performers]
        title_chars = [len(title) for title in all_titles]
        avg_title_len = sum(title_chars) / len(title_chars) if title_chars else 0

        lines.append(f"- **标题长度范围**: {min(title_chars) if title_chars else 0} - {max(title_chars) if title_chars else 0} 字")
        lines.append(f"- **平均标题长度**: {avg_title_len:.1f} 字\n")

        # Extract common patterns
        lines.append("### 标题结构偏好\n")
        lines.append("观察到的模式：")
        lines.append("- 大多包含数字或具体时间点 (如 '2026年', '5月', '芯片')\n")
        lines.append("- 可使用情感词 (但不是空洞吹捧，避免 AI 填充感)\n")
        lines.append("- 可采用反向提问或趋势预测结构\n")

    # Content recommendations
    lines.append("\n## 💡 AI 写作建议\n")
    lines.append("基于历史数据的优化策略：\n")

    suggestions = _generate_suggestions(high_performers)
    for suggestion in suggestions:
        lines.append(f"{suggestion['type']}: **{suggestion.get('title', 'N/A')}**\n")
        lines.append(f"{suggestion.get('content', '')}\n")

    lines.append("\n---\n")
    lines.append("*此报告由 `POST /api/admin/agent/analytics/title-optimization` 自动生成")
    lines.append("*AI 可以读取此报告，提取标题模板和内容模式来生成更吸睛的文章*")

    return "\n".join(lines)


def _generate_suggestions(high_performers: list[dict]) -> list[dict]:
    """Generate actionable suggestions based on high-performers."""

    suggestions = []

    # Read count focused
    read_focused = [
        h
        for h in high_performers
        if h.get("_score", 0) > 0 and h.get("read_count", 0) > h.get("comment_count", 0) * 2
    ]
    if read_focused:
        read_titles = [h.get("title", "")[:40] for h in read_focused[:3]]
        suggestions.append({
            "type": "阅读量驱动",
            "title": "突出数据/事实",
            "content": f"模仿以下标题结构：{read_titles}\n\n策略：使用具体数字、行业术语或硬核事实来吸引点击。",
        })

    # Share focused
    share_focused = [
        h
        for h in high_performers
        if h.get("_score", 0) > 0 and h.get("share_count", 0) > 0
    ]
    if share_focused:
        share_titles = [h.get("title", "")[:40] for h in share_focused[:3]]
        suggestions.append({
            "type": "分享驱动",
            "title": "制造洞察/争议",
            "content": f"模仿以下标题结构：{share_titles}\n\n策略：提供独特见解、挑战常规认知或揭示隐藏真相。",
        })

    # Comment focused
    comment_focused = [
        h
        for h in high_performers
        if h.get("_score", 0) > 0 and h.get("comment_count", 0) > 0
    ]
    if comment_focused:
        comment_titles = [h.get("title", "")[:40] for h in comment_focused[:3]]
        suggestions.append({
            "type": "讨论驱动",
            "title": "引发共鸣/ امام",
            "content": f"模仿以下标题结构：{comment_titles}\n\n策略：关联用户身份、职业痛点或价值观冲突。",
        })

    if not suggestions:
        suggestions.append({
            "type": "通用建议",
            "title": "平衡所有指标",
            "content": "避免单一维度的标题策略，兼顾阅读、分享、评论。标题要保持专业，同时有故事性与信息增量。",
        })

    return suggestions
