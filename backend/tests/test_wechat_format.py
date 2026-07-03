from backend.app.content.briefing import (
    build_agent_article_writing_guide,
    build_brief_summary,
    build_prompt_package_markdown,
    optimize_wechat_article_title,
    rewrite_markdown_title,
)
from backend.app.content.wechat_format import markdown_to_plain_text, markdown_to_wechat_html, strip_markdown_title


def test_strip_markdown_title_removes_leading_heading() -> None:
    result = strip_markdown_title("# 标题\n\n正文第一段", "标题")

    assert result == "正文第一段"


def test_markdown_to_wechat_html_restores_common_blocks_and_inline_marks() -> None:
    html = markdown_to_wechat_html(
        "# 标题\n\n第一段有 **加粗**、*强调* 和 `代码`。\n\n- 列表一\n- 列表二\n\n> 引用内容"
    )

    assert "<h1>标题</h1>" in html
    assert "<strong>加粗</strong>" in html
    assert "<em>强调</em>" in html
    assert "<code>代码</code>" in html
    assert "<ul><li>列表一</li><li>列表二</li></ul>" in html
    assert "<blockquote><p>引用内容</p></blockquote>" in html


def test_markdown_to_plain_text_removes_markdown_symbols() -> None:
    text = markdown_to_plain_text("## 小标题\n\n- 列表项\n\n正文里有 **加粗** 和 `代码`。")

    assert "**" not in text
    assert "`" not in text
    assert "列表项" in text
    assert "加粗" in text
    assert "代码" in text


def test_optimize_wechat_article_title_adds_hook_for_plain_title() -> None:
    title = optimize_wechat_article_title(
        "英伟达财报",
        one_line="数据中心收入再创新高，市场预期继续上修。",
        facts=["数据中心收入再创新高", "毛利率维持高位"],
        article_markdown="# 英伟达财报\n\n数据中心收入再创新高，市场预期继续上修。",
    )

    assert title == "英伟达财报：数据中心收入再创新高"


def test_rewrite_markdown_title_updates_first_heading_only() -> None:
    rewritten = rewrite_markdown_title(
        "# 原标题\n\n第一段正文\n\n## 小标题\n\n更多内容",
        "原标题",
        "原标题：新高",
    )

    assert rewritten.startswith("# 原标题：新高")
    assert "## 小标题" in rewritten


def test_build_agent_article_writing_guide_contains_new_required_sections() -> None:
    guide = build_agent_article_writing_guide()

    assert "### 标题策略" in guide
    assert "### 摘要" in guide
    assert "### 引文与事实底线" in guide
    assert "### 自检清单" in guide
    assert "禁止出现这些高频 AI 味词" in guide


def test_build_agent_article_writing_guide_requires_polished_platform_digest() -> None:
    guide = build_agent_article_writing_guide()

    assert "本地审阅稿可以使用下面这种结构" in guide
    assert "发到微信、抖音或其他平台前，必须再润色成自然连贯的发布稿" in guide
    assert "不要保留 `## 1.`、`## 来源链接`、裸 URL 列表" in guide
    assert "首先 / 然后 / 接下来 / 再说 / 最后" in guide


def test_build_agent_article_writing_guide_pushes_strong_expression_without_false_certainty() -> None:
    guide = build_agent_article_writing_guide()

    assert "有事实纪律的强表达" in guide
    assert "标题必须优先制造点击理由" in guide
    assert "和普通人、开发者、消费者、公司账单或未来设备有什么关系" in guide
    assert "允许有冲突感、利益关系、悬念和口语表达" in guide
    assert "不能把推测写成确定事实" in guide
    assert "不能把个体案例写成普遍结论" in guide
    assert "不能承诺素材没有证明的未来结果" in guide


def test_build_prompt_package_markdown_includes_writing_guide_before_material_sections() -> None:
    markdown = build_prompt_package_markdown(
        title="测试标题",
        one_line="一句话结论",
        why_it_matters="为什么值得关注",
        facts=["事实 1"],
        full_text_sources=[],
        source_quotes=[],
        timeline=[],
        risk_notes=[],
        source_links=[],
        article_writing_guide="## 公众号文章写作规范\n\n### 标题策略\n说明",
    )

    assert "## 写作要求" in markdown
    assert markdown.index("## 写作要求") < markdown.index("## 事件标题")


def test_build_prompt_package_markdown_prioritizes_clickable_publish_copy() -> None:
    markdown = build_prompt_package_markdown(
        title="测试标题",
        one_line="一句话结论",
        why_it_matters="为什么值得关注",
        facts=["事实 1"],
        full_text_sources=[],
        source_quotes=[],
        timeline=[],
        risk_notes=[],
        source_links=[],
    )

    assert "目标不是新闻简报，而是让普通读者愿意点开、读完、转发给朋友" in markdown
    assert "标题要有冲突感、利益关系或悬念" in markdown
    assert "不要输出后台素材稿或结构化审阅稿" in markdown


def test_build_brief_summary_falls_back_in_expected_order() -> None:
    assert build_brief_summary(summary="显式摘要", one_line="一句话", facts=["事实"], event_summary="事件摘要") == "显式摘要"
    assert build_brief_summary(summary="", one_line="一句话", facts=["事实"], event_summary="事件摘要") == "一句话"
    assert build_brief_summary(summary="", one_line="", facts=["事实"], event_summary="事件摘要") == "事实"
    assert build_brief_summary(summary="", one_line="", facts=[], event_summary="事件摘要") == "事件摘要"
