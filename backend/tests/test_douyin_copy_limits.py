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


def test_build_douyin_article_markdown_frontloads_conclusion_and_judgment() -> None:
    markdown = """# 高通逼近5GHz，小米18把旗舰芯片竞争重新拉满

5 月 21 日晚间，关于高通下一代旗舰平台的消息开始集中发酵。按照驱动之家披露的说法，骁龙 8 Elite Gen6 系列不仅会切到台积电 2nm，最高主频还将逼近 5GHz。

## 2nm 和接近 5GHz，说明高通这次不是常规迭代

从现有披露信息看，骁龙 8 Elite Gen6 系列最抓眼球的两个点，就是 2nm 工艺和接近 5GHz 的主频。

## 来源链接

- https://example.com/a
"""

    result = build_douyin_article_markdown(
        title="高通逼近5GHz，小米18把旗舰芯片竞争重新拉满",
        summary="2nm、接近 5GHz、Pro 版分层",
        article_markdown=markdown,
        one_line="高通下一代旗舰平台最值得盯的，不是某一个夸张参数，而是手机 SoC 正在再次进入性能极限优先的周期。",
        why_it_matters="如果 2nm 和接近 5GHz 真落地，接下来两年的安卓旗舰竞争会重新围着芯片展开。",
    )

    assert result.startswith("# 高通逼近5GHz，小米18把旗舰芯片竞争重新拉满")
    assert "高通下一代旗舰平台最值得盯的" in result
    assert "接下来两年的安卓旗舰竞争会重新围着芯片展开" in result
    assert "来源链接" not in result


def test_build_douyin_article_markdown_stays_under_1000_chars() -> None:
    markdown = "# 标题\n\n" + "这是一段很长的正文。" * 400
    result = build_douyin_article_markdown(
        title="高通逼近5GHz，小米18把旗舰芯片竞争重新拉满",
        summary="2nm、接近 5GHz、Pro 版分层",
        article_markdown=markdown,
        one_line="高通下一代旗舰平台最值得盯的，不是某一个夸张参数，而是手机 SoC 正在再次进入性能极限优先的周期。",
        why_it_matters="如果 2nm 和接近 5GHz 真落地，接下来两年的安卓旗舰竞争会重新围着芯片展开。",
    )
    body = result.split("\n", 1)[1].replace("\n", "")

    assert len(body) <= 1000
