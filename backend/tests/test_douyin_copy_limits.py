from backend.app.briefing import build_douyin_article_markdown, build_douyin_summary, build_douyin_title


def test_build_douyin_title_prefers_readable_prefix_before_cutting() -> None:
    title = "谷歌、微软、xAI 向美国政府开放早期 AI 模型：科技巨头与监管的新博弈"
    result = build_douyin_title(title)

    assert result == "谷歌、微软、xAI 向美国政府开放早期 AI 模型"
    assert len(result) <= 30


def test_build_douyin_summary_keeps_complete_sentence_under_limit() -> None:
    title = "谷歌、微软、xAI 向美国政府开放早期 AI 模型：科技巨头与监管的新博弈"
    summary = "谷歌、微软和 xAI 同意向美国开放早期 AI 模型访问，AI 监管从事后约束转向事前介入"
    result = build_douyin_summary(summary, title)

    assert result == "谷歌、微软和 xAI 同意向美国开放早期 AI 模型访问"
    assert len(result) <= 30


def test_build_douyin_summary_falls_back_to_title_suffix_when_needed() -> None:
    title = "苹果为 Siri AI 失约付出2.5亿美元学费"
    result = build_douyin_summary("", title)

    assert result == "苹果为 Siri AI 失约付出2.5亿美元学费"
    assert len(result) <= 30


def test_build_douyin_summary_compresses_long_official_phrases() -> None:
    title = "国行Switch今晚22点关服"
    summary = "2026年5月15日22时，国行 Nintendo Switch 的网络相关运营服务正式停止。真正被关掉的不是主机本身。"
    result = build_douyin_summary(summary, title)

    assert result == "国行Switch的网络服务停止"
    assert len(result) <= 30


def test_build_douyin_title_trims_cleanly_when_no_good_boundary_exists() -> None:
    title = "ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890"
    result = build_douyin_title(title)

    assert result == "ABCDEFGHIJKLMNOPQRSTUVWXYZ1234"
    assert len(result) == 30


def test_build_douyin_article_markdown_removes_source_tail_and_shortens_paragraphs() -> None:
    markdown = """# 国行Switch今晚22点关服：不是主机报废，而是数字能力正式收尾

今晚 22:00，国行 Nintendo Switch 的网络相关运营服务正式停止。很多人看到“关服”两个字，第一反应是机器是不是不能用了，但这次真正被关掉的，不是你手里的主机，而是围绕它搭起来的数字购买、兑换、下载和部分联网能力。

## 今晚被关掉的，到底是什么

腾讯 Nintendo Switch 官网的正式通知把时间点写得很清楚。第一段变化发生在 2026 年 3 月 31 日 22 时，Nintendo e 商店停止销售游戏和工具软件。第二段变化发生在 2026 年 5 月 15 日 22 时，e 商店下载服务、兑换码兑换服务，以及其他网络相关运营服务一起停止。

## 来源链接

- https://example.com/a
- https://example.com/b
"""

    result = build_douyin_article_markdown(
        title="国行Switch今晚22点关服：不是主机报废，而是数字能力正式收尾",
        summary="2026年5月15日22时，国行 Nintendo Switch 网络相关运营服务正式停止。",
        article_markdown=markdown,
        one_line="2026年5月15日22时，国行 Nintendo Switch 网络相关运营服务正式停止。",
        why_it_matters="机器还能玩，但数字购买、兑换、下载和部分联网能力正式收尾。",
    )

    assert result.startswith("# 国行Switch今晚22点关服")
    assert "来源链接" not in result
    assert "https://example.com/a" not in result
    assert "机器还能玩，但数字购买、兑换、下载和部分联网能力正式收尾" in result
