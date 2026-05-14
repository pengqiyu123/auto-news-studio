from backend.app.publishers import (
    _apply_wechat_publish_settings,
    _can_interact_with_page,
    _clamp_author,
    _converge_context_to_target,
    _enforce_single_tab,
    _fill_wechat_editor,
    _locate_editor_page_with_retry,
    _pick_selector,
    _pick_visible_locator,
    WechatBrowserManager,
    get_selector_profile,
)


class _FakeNode:
    def __init__(self, visible: bool) -> None:
        self._visible = visible
        self.clicked = False
        self.value = ""
        self.text_content = ""
        self.click_count = 0

    def wait_for(self, *, state=None, timeout=None):
        if state == "visible" and not self._visible:
            raise RuntimeError("not visible")
        return None

    def click(self, timeout=None):
        self.clicked = True
        self.click_count += 1

    def count(self):
        return 1

    def fill(self, value: str):
        self.value = value
        self.text_content = value

    def type(self, value: str, delay: int = 0):
        self.value = value
        self.text_content = value

    def press(self, _keys: str):
        return None


class _MissingNode:
    def wait_for(self, *, state=None, timeout=None):
        raise RuntimeError("missing")

    def click(self, timeout=None):
        raise RuntimeError("missing")

    def count(self):
        return 0

    def fill(self, value: str):
        raise RuntimeError("missing")

    def type(self, value: str, delay: int = 0):
        raise RuntimeError("missing")

    def press(self, _keys: str):
        raise RuntimeError("missing")


class _BoundNode:
    def __init__(self, page, selector: str, node) -> None:
        self._page = page
        self._selector = selector
        self._node = node

    def wait_for(self, *, state=None, timeout=None):
        return self._node.wait_for(state=state, timeout=timeout)

    def click(self, timeout=None):
        self._page._active_selector = self._selector
        return self._node.click(timeout=timeout)

    def count(self):
        return self._node.count()

    def fill(self, value: str):
        self._page._active_selector = self._selector
        return self._node.fill(value)

    def type(self, value: str, delay: int = 0):
        self._page._active_selector = self._selector
        return self._node.type(value, delay=delay)

    def press(self, keys: str):
        self._page._active_selector = self._selector
        return self._node.press(keys)


class _FakeLocator:
    def __init__(self, nodes, page, selector: str):
        self._nodes = list(nodes)
        self._page = page
        self._selector = selector

    def count(self):
        return len(self._nodes)

    def nth(self, index: int):
        return _BoundNode(self._page, self._selector, self._nodes[index])

    @property
    def first(self):
        if not self._nodes:
            return _MissingNode()
        return _BoundNode(self._page, self._selector, self._nodes[0])

    def click(self, timeout=None):
        node = self.first
        self._page._active_selector = self._selector
        return node.click(timeout=timeout)

    def fill(self, value: str):
        node = self.first
        self._page._active_selector = self._selector
        return node.fill(value)

    def type(self, value: str, delay: int = 0):
        node = self.first
        self._page._active_selector = self._selector
        return node.type(value, delay=delay)

    def press(self, keys: str):
        node = self.first
        self._page._active_selector = self._selector
        return node.press(keys)


class _FakePage:
    def __init__(self, mapping, *, url: str = "https://mp.weixin.qq.com/") -> None:
        self._mapping = mapping
        self.url = url
        self.wait_calls = 0
        self.closed = False
        self._active_selector: str | None = None
        self.keyboard = _FakeKeyboard(self)

    def locator(self, selector: str):
        nodes = self._mapping.get(selector, [])
        return _FakeLocator(nodes, self, selector)

    def wait_for_load_state(self, *_args, **_kwargs):
        return None

    def wait_for_timeout(self, _timeout: int):
        self.wait_calls += 1

    def goto(self, url: str, wait_until: str | None = None, timeout: int | None = None):
        self.url = url
        return None

    def evaluate(self, script: str, payload=None):
        script_text = str(script)
        if "document.querySelector(selector)" in script_text and "richText" in script_text:
            selector = payload["selector"]
            node = self._mapping.get(selector, [None])[0]
            if node is None:
                return ""
            if payload.get("richText"):
                return node.text_content
            return node.value or node.text_content
        if "node.innerHTML = html" in script_text:
            selector = payload["selector"]
            node = self._mapping.get(selector, [None])[0]
            if node is not None:
                node.text_content = str(payload.get("html") or "")
            return None
        if "node.innerHTML = ''" in script_text and "document.createElement('section')" in script_text:
            selector = payload["selector"]
            node = self._mapping.get(selector, [None])[0]
            if node is not None:
                value = str(payload.get("value") or "")
                blocks = [item.strip() for item in value.splitlines() if item.strip()]
                node.text_content = "<section>" + "".join(f"<p>{item}</p>" for item in blocks) + "</section>"
            return None
        if "document.execCommand('insertText'" in script_text:
            selector = payload["selector"]
            node = self._mapping.get(selector, [None])[0]
            if node is not None:
                node.text_content = str(payload.get("value") or "")
            return None
        if "document.execCommand('copy')" in script_text:
            self._clipboard = str(payload or "")
            return None
        return None

    def close(self):
        self.closed = True

    def is_closed(self):
        return self.closed

    def screenshot(self, *args, **kwargs):
        return None


class _FakeKeyboard:
    def __init__(self, page: _FakePage) -> None:
        self._page = page

    def press(self, keys: str):
        if keys.lower() == "control+a":
            return None
        if keys.lower() == "control+v":
            selector = self._page._active_selector
            if selector:
                node = self._page._mapping.get(selector, [None])[0]
                if node is not None:
                    pasted = str(getattr(self._page, "_clipboard", "") or "")
                    node.value = pasted
                    node.text_content = pasted


class _FakeContext:
    def __init__(self, pages):
        self.pages = list(pages)


def test_pick_selector_prefers_visible_node_when_first_match_is_hidden():
    page = _FakePage(
        {
            ".target": [
                _FakeNode(visible=False),
                _FakeNode(visible=True),
            ]
        }
    )

    selected = _pick_selector(page, [".target"], timeout=10)

    assert selected == ".target"


def test_pick_visible_locator_returns_visible_node_instead_of_first_hidden():
    hidden = _FakeNode(visible=False)
    visible = _FakeNode(visible=True)
    page = _FakePage({".target": [hidden, visible]})

    selected = _pick_visible_locator(page, ".target", timeout=10)
    selected.click()

    assert visible.clicked is True
    assert hidden.clicked is False


def test_wechat_new_article_selectors_prioritize_home_tile_structure():
    selectors = get_selector_profile("wechat-mp-v1")["new_article"]

    assert selectors == [
        ".new-creation__menu-item:has(.new-creation__menu-title:text-is('文章'))",
        ".new-creation__menu-content:has(.new-creation__menu-title:text-is('文章'))",
        ".new-creation__menu-title:text-is('文章')",
    ]


def test_enforce_single_tab_recovers_by_closing_extra_tabs():
    home = _FakePage({}, url="https://mp.weixin.qq.com/")
    editor = _FakePage({}, url="https://mp.weixin.qq.com/cgi-bin/appmsg?t=media/appmsg_edit_v2")
    context = _FakeContext([home, editor])
    step_logs: list[str] = []

    _enforce_single_tab(context, home, step_logs, phase="before_upload", allow_recover=True)

    assert editor.closed is True
    assert "单标签页恢复 phase=before_upload closed_tabs=1" in step_logs


def test_enforce_single_tab_raises_when_extra_tabs_not_allowed():
    home = _FakePage({}, url="https://mp.weixin.qq.com/")
    editor = _FakePage({}, url="https://mp.weixin.qq.com/cgi-bin/appmsg?t=media/appmsg_edit_v2")
    context = _FakeContext([home, editor])

    try:
        _enforce_single_tab(context, home, [], phase="after_click_article", allow_recover=False)
    except RuntimeError as exc:
        assert "违反单标签页约束" in str(exc)
    else:
        raise AssertionError("expected single-tab enforcement to raise")


def test_converge_context_to_target_closes_all_non_target_tabs():
    home = _FakePage({}, url="https://mp.weixin.qq.com/")
    helper = _FakePage({}, url="about:blank")
    editor = _FakePage({}, url="https://mp.weixin.qq.com/cgi-bin/appmsg?t=media/appmsg_edit_v2")
    context = _FakeContext([home, helper, editor])
    step_logs: list[str] = []

    _converge_context_to_target(context, editor, step_logs, phase="debug")

    assert home.closed is True
    assert helper.closed is True
    assert editor.closed is False
    assert "单标签页收敛 phase=debug closed_tabs=2 remaining=1" in step_logs


def test_locate_editor_page_with_retry_finds_new_editor_tab():
    profile = get_selector_profile("wechat-mp-v1")
    home_page = _FakePage({}, url="https://mp.weixin.qq.com/")
    editor_page = _FakePage(
        {
            "textarea.js_article_title": [_FakeNode(visible=True)],
            ".ProseMirror": [_FakeNode(visible=True)],
        },
        url="https://mp.weixin.qq.com/cgi-bin/appmsg?t=media/appmsg_edit_v2&action=edit",
    )
    context = _FakeContext([home_page, editor_page])
    step_logs: list[str] = []

    selected = _locate_editor_page_with_retry(context, home_page, profile, step_logs)

    assert selected is editor_page
    assert step_logs == []


def test_locate_editor_page_with_retry_raises_when_editor_tab_never_appears():
    profile = get_selector_profile("wechat-mp-v1")
    current_page = _FakePage({}, url="https://mp.weixin.qq.com/")
    context = _FakeContext([current_page])

    try:
        _locate_editor_page_with_retry(context, current_page, profile, [])
    except RuntimeError as exc:
        assert "未找到新开的编辑页" in str(exc)
    else:
        raise AssertionError("expected locate_editor_page_with_retry to fail")


def test_fill_wechat_editor_validates_written_values():
    profile = get_selector_profile("wechat-mp-v1")
    title_node = _FakeNode(visible=True)
    digest_node = _FakeNode(visible=True)
    editor_node = _FakeNode(visible=True)
    page = _FakePage(
        {
            "textarea.js_article_title": [title_node],
            "textarea.js_desc": [digest_node],
            "#edui1_iframeholder .mock-iframe-body .rich_media_content > div.ProseMirror[contenteditable='true']": [editor_node],
        },
        url="https://mp.weixin.qq.com/cgi-bin/appmsg?t=media/appmsg_edit_v2&action=edit",
    )
    step_logs: list[str] = []

    _fill_wechat_editor(
        page,
        {"title": "测试标题", "summary": "测试摘要", "markdown": "# 测试标题\n\n这里是足够长的正文内容，用于通过正文长度校验。"},
        {"author": ""},
        profile,
        step_logs,
    )

    assert title_node.value == "测试标题"
    assert digest_node.value == "测试摘要"
    assert "正文回读长度=" in "\n".join(step_logs)


def test_fill_wechat_editor_falls_back_to_html_strategy_before_short_clipboard_path():
    profile = get_selector_profile("wechat-mp-v1")
    title_node = _FakeNode(visible=True)
    editor_node = _FakeNode(visible=True)
    page = _FakePage(
        {
            "textarea.js_article_title": [title_node],
            "#edui1_iframeholder .mock-iframe-body .rich_media_content > div.ProseMirror[contenteditable='true']": [editor_node],
        },
        url="https://mp.weixin.qq.com/cgi-bin/appmsg?t=media/appmsg_edit_v2&action=edit",
    )
    page._clipboard = ""
    step_logs: list[str] = []

    original_press = page.keyboard.press

    def fake_press(keys: str):
        if keys.lower() == "control+v":
            editor_node.text_content = "短"
            return None
        return original_press(keys)

    page.keyboard.press = fake_press

    _fill_wechat_editor(
        page,
        {"title": "测试标题", "summary": "", "markdown": "# 测试标题\n\n这里是足够长的正文内容，用于触发长度校验失败。"},
        {"author": ""},
        profile,
        step_logs,
    )

    assert "<p>这里是足够长的正文内容，用于触发长度校验失败。</p>" in editor_node.text_content
    assert "正文回读长度=" in "\n".join(step_logs)


def test_fill_wechat_editor_supports_new_prosemirror_title_and_body_selectors():
    profile = get_selector_profile("wechat-mp-v1")
    title_node = _FakeNode(visible=True)
    author_node = _FakeNode(visible=True)
    body_node = _FakeNode(visible=True)
    page = _FakePage(
        {
            "div.ProseMirror[data-placeholder*='请在这里输入标题']": [title_node],
            "input.js_author": [author_node],
            "#edui1_iframeholder .mock-iframe-body .rich_media_content > div.ProseMirror[contenteditable='true']": [body_node],
        },
        url="https://mp.weixin.qq.com/cgi-bin/appmsg?t=media/appmsg_edit_v2&action=edit",
    )
    step_logs: list[str] = []

    _fill_wechat_editor(
        page,
        {"title": "新版标题", "summary": "", "markdown": "# 新版标题\n\n这里是新版编辑器里的正文内容，而且长度足够通过校验。"},
        {"author": "作者名"},
        profile,
        step_logs,
    )

    assert title_node.value == "新版标题"
    assert author_node.value == "作者名"
    assert body_node.text_content
    assert "标题最终长度=" in "\n".join(step_logs)
    assert "正文最终长度=" in "\n".join(step_logs)


def test_fill_wechat_editor_prefers_appmsg_editor_body_and_strips_markdown_heading():
    profile = get_selector_profile("wechat-mp-v1")
    title_node = _FakeNode(visible=True)
    body_node = _FakeNode(visible=True)
    fallback_body_node = _FakeNode(visible=True)
    page = _FakePage(
        {
            "div.ProseMirror[data-placeholder*='请在这里输入标题']": [title_node],
            "#edui1_iframeholder .mock-iframe-body .rich_media_content > div.ProseMirror[contenteditable='true']": [body_node],
            ".rich_media_content [contenteditable='true']": [fallback_body_node],
        },
        url="https://mp.weixin.qq.com/cgi-bin/appmsg?t=media/appmsg_edit_v2&action=edit",
    )
    step_logs: list[str] = []

    _fill_wechat_editor(
        page,
        {"title": "测试标题", "summary": "", "markdown": "# 测试标题\n\n这里是正文第一段。\n\n这里是正文第二段。"},
        {"author": ""},
        profile,
        step_logs,
    )

    assert title_node.value == "测试标题"
    assert "测试标题" not in body_node.text_content
    assert "这里是正文第一段。" in body_node.text_content
    assert fallback_body_node.text_content == ""
    assert "#edui1_iframeholder .mock-iframe-body .rich_media_content > div.ProseMirror[contenteditable='true']" in "\n".join(step_logs)


def test_wechat_editor_selector_prefers_real_editor_dom_path():
    selectors = get_selector_profile("wechat-mp-v1")["editor"]

    assert selectors[0] == "#edui1_iframeholder .mock-iframe-body .rich_media_content > div.ProseMirror[contenteditable='true']"
    assert ".ProseMirror" not in selectors
    assert "[contenteditable='true']" not in selectors


def test_fill_wechat_editor_restores_markdown_structure_in_body():
    profile = get_selector_profile("wechat-mp-v1")
    title_node = _FakeNode(visible=True)
    body_node = _FakeNode(visible=True)
    page = _FakePage(
        {
            "div.ProseMirror[data-placeholder*='请在这里输入标题']": [title_node],
            "#edui1_iframeholder .mock-iframe-body .rich_media_content > div.ProseMirror[contenteditable='true']": [body_node],
        },
        url="https://mp.weixin.qq.com/cgi-bin/appmsg?t=media/appmsg_edit_v2&action=edit",
    )
    step_logs: list[str] = []

    _fill_wechat_editor(
        page,
        {
            "title": "结构化标题",
            "summary": "",
            "markdown": "# 结构化标题\n\n第一段有 **加粗** 和 `代码`。\n\n- 列表一\n- 列表二\n\n> 引用一行",
        },
        {"author": ""},
        profile,
        step_logs,
    )

    assert title_node.value == "结构化标题"
    assert "<strong>加粗</strong>" in body_node.text_content
    assert "<code>代码</code>" in body_node.text_content
    assert "<ul><li>列表一</li><li>列表二</li></ul>" in body_node.text_content
    assert "<blockquote><p>引用一行</p></blockquote>" in body_node.text_content


def test_apply_wechat_publish_settings_clicks_original_reward_and_confirms_in_order():
    profile = get_selector_profile("wechat-mp-v1")
    original_node = _FakeNode(visible=True)
    reward_node = _FakeNode(visible=True)
    confirm_node = _FakeNode(visible=True)
    page = _FakePage(
        {
            "#js_original": [original_node],
            "#js_reward_setting_area": [reward_node],
            "button.weui-desktop-btn.weui-desktop-btn_primary:has-text('确定')": [confirm_node],
        },
        url="https://mp.weixin.qq.com/cgi-bin/appmsg?t=media/appmsg_edit_v2&action=edit",
    )
    step_logs: list[str] = []

    _apply_wechat_publish_settings(page, profile, step_logs)

    assert original_node.click_count == 1
    assert reward_node.click_count == 1
    assert confirm_node.click_count == 2
    assert "open_original_setting 已点击 selector=#js_original" in step_logs
    assert "confirm_original_setting 已点击 selector=button.weui-desktop-btn.weui-desktop-btn_primary:has-text('确定')" in step_logs
    assert "open_reward_setting 已点击 selector=#js_reward_setting_area" in step_logs
    assert "confirm_reward_setting 已点击 selector=button.weui-desktop-btn.weui-desktop-btn_primary:has-text('确定')" in step_logs


def test_can_interact_with_page_returns_false_for_closed_page():
    page = _FakePage({}, url="https://mp.weixin.qq.com/")
    page.close()

    assert _can_interact_with_page(page) is False


def test_clamp_author_preserves_single_spaces_before_truncation():
    assert _clamp_author("Auto News Studio") == "Auto New"


def test_browser_manager_reuses_live_page_when_cached_page_is_stale():
    manager = WechatBrowserManager()
    stale_page = _FakePage({}, url="https://mp.weixin.qq.com/old")
    stale_page.close()
    live_page = _FakePage({}, url="https://mp.weixin.qq.com/home")
    context = _FakeContext([live_page])

    manager._page = stale_page
    manager.ensure_context = lambda _channel: context  # type: ignore[assignment]

    selected = manager.ensure_page({}, "https://mp.weixin.qq.com/")

    assert selected is live_page
    assert manager._page is live_page
    assert manager._last_action_phase == "page_recovered"
