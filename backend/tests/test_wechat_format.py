from backend.app.briefing import optimize_wechat_article_title, rewrite_markdown_title
from backend.app.wechat_format import markdown_to_plain_text, markdown_to_wechat_html, strip_markdown_title


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
