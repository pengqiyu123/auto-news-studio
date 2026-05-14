from backend.app.publishers import _build_douyin_summary, _build_douyin_title


def test_build_douyin_title_prefers_readable_prefix_before_cutting() -> None:
    title = "谷歌、微软、xAI 向美国政府开放早期 AI 模型：科技巨头与监管的新博弈"
    result = _build_douyin_title(title)

    assert result == "谷歌、微软、xAI 向美国政府开放早期 AI 模型"
    assert len(result) <= 30


def test_build_douyin_summary_keeps_complete_sentence_under_limit() -> None:
    title = "谷歌、微软、xAI 向美国政府开放早期 AI 模型：科技巨头与监管的新博弈"
    summary = "谷歌、微软和 xAI 同意向美国开放早期 AI 模型访问，AI 监管从事后约束转向事前介入"
    result = _build_douyin_summary(summary, title)

    assert result == "谷歌、微软和 xAI 同意向美国开放早期 AI 模型访问"
    assert len(result) <= 30


def test_build_douyin_summary_falls_back_to_title_suffix_when_needed() -> None:
    title = "苹果为 Siri AI 失约付出2.5亿美元学费"
    result = _build_douyin_summary("", title)

    assert result == "苹果为 Siri AI 失约付出2.5亿美元学费"
    assert len(result) <= 30


def test_build_douyin_title_trims_cleanly_when_no_good_boundary_exists() -> None:
    title = "ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890"
    result = _build_douyin_title(title)

    assert result == "ABCDEFGHIJKLMNOPQRSTUVWXYZ1234"
    assert len(result) == 30
