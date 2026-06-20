from backend.app.publishers import (
    _apply_wechat_publish_settings,
    _build_ai_cover_prompt,
    _can_interact_with_page,
    _click_wechat_publish_until_qrcode,
    _clamp_author,
    _converge_context_to_target,
    _ensure_wechat_ai_cover,
    _enforce_single_tab,
    _fill_wechat_editor,
    _locate_editor_page_with_retry,
    _pick_selector,
    _pick_visible_locator,
    _run_publish_to_qrcode,
    _select_hidden_wechat_option_by_text,
    WechatBrowserManager,
    get_selector_profile,
    run_browser_action,
)


class _FakeNode:
    def __init__(self, visible: bool, *, fail_first_click: bool = False) -> None:
        self._visible = visible
        self.clicked = False
        self.value = ""
        self.text_content = ""
        self.click_count = 0
        self.fail_first_click = fail_first_click

    def wait_for(self, *, state=None, timeout=None):
        if state == "visible" and not self._visible:
            raise RuntimeError("not visible")
        return None

    def click(self, timeout=None):
        if self.fail_first_click and self.click_count == 0:
            self.click_count += 1
            raise RuntimeError("popover intercepts pointer events")
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
        self._page._click_history.append(self._selector)
        if "action=list_card" in self._selector or "草稿箱" in self._selector:
            self._page.url = "https://mp.weixin.qq.com/cgi-bin/appmsg?t=media/appmsg_edit&action=list_card"
        if "AI新闻" in self._selector:
            self._page._collection_selected_text = "AI新闻"
        if "个人观点" in self._selector or "value='4'" in self._selector:
            self._page._claim_source_selected_text = "个人观点，仅供参考"
        result = self._node.click(timeout=timeout)
        if "new-creation__menu" in self._selector:
            new_page = getattr(self._page, "_new_article_page", None)
            context = getattr(self._page, "_context", None)
            if new_page is not None and context is not None and new_page not in context.pages:
                context.pages.append(new_page)
        return result

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
        self._click_history: list[str] = []
        self._hidden_option_selected = False
        self._collection_selected_text = ""
        self._claim_source_selected_text = ""
        self._screenshots: list[str] = []
        self._close_fails = False
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
        if "appmsg" in url:
            editor_page = getattr(self, "_existing_editor_page", None)
            context = getattr(self, "_context", None)
            if editor_page is not None and context is not None and editor_page not in context.pages:
                context.pages.append(editor_page)
        return None

    def evaluate(self, script: str, payload=None):
        script_text = str(script)
        if "document.querySelectorAll(" in script_text and "publish_card_container" in script_text and "results.slice" in script_text:
            return list(getattr(self, "_remote_draft_items", []))
        if "clickable.dispatchEvent" in script_text:
            title = str((payload or {}).get("title") or "").strip().lower()
            for item in getattr(self, "_remote_draft_items", []):
                item_title = str(item.get("title") or "").strip().lower()
                if title and item_title and (title == item_title or title in item_title or item_title in title):
                    editor_page = getattr(self, "_existing_editor_page", None)
                    context = getattr(self, "_context", None)
                    if editor_page is not None and context is not None and editor_page not in context.pages:
                        context.pages.append(editor_page)
                    return True
            return False
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
        if "li.select-opt-li, .select-opt-li, li" in script_text:
            option_text = str(payload.get("optionText") or "")
            for selector, nodes in self._mapping.items():
                if "select-opt-li" not in selector:
                    continue
                for node in nodes:
                    node_text = node.text_content or node.value or option_text
                    if option_text in node_text:
                        node.clicked = True
                        node.click_count += 1
                        self._collection_selected_text = node_text
                        self._hidden_option_selected = True
                        return {"ok": True, "reason": "dispatched", "text": node_text}
            return {"ok": False, "reason": "not_found", "text": ""}
        if "openCollectionPickerDropdown" in script_text:
            option_texts = []
            for selector, nodes in self._mapping.items():
                if "select-opt-li" not in selector:
                    continue
                option_texts.extend(node.text_content or node.value or "AI新闻" for node in nodes)
            return {
                "marker": "openCollectionPickerDropdown",
                "inputFound": True,
                "wrapperFound": True,
                "dropdownFound": bool(option_texts),
                "beforeDisplay": "none",
                "afterDisplay": "block",
                "optionCount": len(option_texts),
                "optionTexts": option_texts,
                "inputValue": self._collection_selected_text,
            }
        if "readCollectionAiNewsSelection" in script_text:
            return {
                "marker": "readCollectionAiNewsSelection",
                "ok": self._collection_selected_text == "AI新闻",
                "selectedText": self._collection_selected_text,
                "inputValue": self._collection_selected_text,
                "checkboxChecked": bool(self._collection_selected_text),
                "dropdownDisplay": "none",
                "optionTexts": [self._collection_selected_text] if self._collection_selected_text else [],
            }
        if "readClaimSourcePersonalSelection" in script_text:
            return {
                "marker": "readClaimSourcePersonalSelection",
                "ok": self._claim_source_selected_text == "个人观点，仅供参考",
                "selectedText": self._claim_source_selected_text,
                "defaultText": "" if self._claim_source_selected_text else "未添加",
                "radioChecked": bool(self._claim_source_selected_text),
            }
        if "个人观点，仅供参考" in script_text and "reason: \"dispatched\"" in script_text:
            self._claim_source_selected_text = "个人观点，仅供参考"
            return {"ok": True, "reason": "dispatched", "text": "个人观点，仅供参考"}
        return None

    def close(self):
        if self._close_fails:
            raise RuntimeError("close blocked")
        self.closed = True

    def is_closed(self):
        return self.closed

    def screenshot(self, *args, **kwargs):
        path = kwargs.get("path") if kwargs else None
        if path is None and args:
            path = args[0]
        if path:
            self._screenshots.append(str(path))
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
    home._context = context
    home._new_article_page = editor
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


def test_locate_editor_page_with_retry_ignores_draft_box_search_input():
    profile = get_selector_profile("wechat-mp-v1")
    draft_box = _FakePage(
        {
            "input[placeholder*='标题']": [_FakeNode(visible=True)],
            ".publish_card_container": [_FakeNode(visible=True)],
        },
        url="https://mp.weixin.qq.com/cgi-bin/appmsg?begin=0&count=10&type=77&action=list_card",
    )
    editor_page = _FakePage(
        {
            "textarea.js_article_title": [_FakeNode(visible=True)],
            ".ProseMirror": [_FakeNode(visible=True)],
        },
        url="https://mp.weixin.qq.com/cgi-bin/appmsg?t=media/appmsg_edit&action=edit&type=77&appmsgid=100000286",
    )
    context = _FakeContext([draft_box, editor_page])

    selected = _locate_editor_page_with_retry(context, draft_box, profile, [])

    assert selected is editor_page


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


def test_apply_wechat_publish_settings_clicks_publish_options_and_confirms_in_order():
    profile = get_selector_profile("wechat-mp-v1")
    original_node = _FakeNode(visible=True)
    reward_node = _FakeNode(visible=True)
    collection_node = _FakeNode(visible=True)
    collection_picker_node = _FakeNode(visible=True)
    ai_news_node = _FakeNode(visible=True)
    claim_source_node = _FakeNode(visible=True)
    personal_source_node = _FakeNode(visible=True)
    confirm_done_node = _FakeNode(visible=True)
    confirm_ok_node = _FakeNode(visible=True)
    page = _FakePage(
        {
            "#js_original": [original_node],
            "#js_reward_setting_area": [reward_node],
            "div.js_article_tags_label": [collection_node],
            "input.weui-desktop-form__input[placeholder='请选择合集']": [collection_picker_node],
            "li.select-opt-li:has-text('AI新闻')": [ai_news_node],
            "div.js_claim_source_desc": [claim_source_node],
            "label.weui-desktop-form__check-label:has-text('个人观点，仅供参考')": [personal_source_node],
            "button.weui-desktop-btn.weui-desktop-btn_primary:has-text('确定')": [confirm_done_node],
            "button.weui-desktop-btn.weui-desktop-btn_primary:has-text('确认')": [confirm_ok_node],
        },
        url="https://mp.weixin.qq.com/cgi-bin/appmsg?t=media/appmsg_edit_v2&action=edit",
    )
    step_logs: list[str] = []

    _apply_wechat_publish_settings(page, profile, step_logs)

    assert original_node.click_count == 1
    assert reward_node.click_count == 1
    assert collection_node.click_count == 1
    assert collection_picker_node.click_count == 1
    assert ai_news_node.click_count == 1
    assert claim_source_node.click_count == 1
    assert personal_source_node.click_count == 1
    assert confirm_done_node.click_count == 2
    assert confirm_ok_node.click_count == 2
    assert page._click_history == [
        "#js_original",
        "button.weui-desktop-btn.weui-desktop-btn_primary:has-text('确定')",
        "#js_reward_setting_area",
        "button.weui-desktop-btn.weui-desktop-btn_primary:has-text('确定')",
        "div.js_article_tags_label",
        "input.weui-desktop-form__input[placeholder='请选择合集']",
        "li.select-opt-li:has-text('AI新闻')",
        "button.weui-desktop-btn.weui-desktop-btn_primary:has-text('确认')",
        "div.js_claim_source_desc",
        "label.weui-desktop-form__check-label:has-text('个人观点，仅供参考')",
        "button.weui-desktop-btn.weui-desktop-btn_primary:has-text('确认')",
    ]
    assert "open_original_setting 已点击 selector=#js_original" in step_logs
    assert "confirm_original_setting 已点击 selector=button.weui-desktop-btn.weui-desktop-btn_primary:has-text('确定')" in step_logs
    assert "open_reward_setting 已点击 selector=#js_reward_setting_area" in step_logs
    assert "confirm_reward_setting 已点击 selector=button.weui-desktop-btn.weui-desktop-btn_primary:has-text('确定')" in step_logs
    assert "open_collection_setting 已点击 selector=div.js_article_tags_label" in step_logs
    assert "open_collection_picker 已点击 selector=input.weui-desktop-form__input[placeholder='请选择合集']" in step_logs
    assert "select_collection_ai_news 已点击 selector=li.select-opt-li:has-text('AI新闻')" in step_logs
    assert "confirm_collection_setting 已点击 selector=button.weui-desktop-btn.weui-desktop-btn_primary:has-text('确认')" in step_logs
    assert "open_claim_source_setting 已点击 selector=div.js_claim_source_desc" in step_logs
    assert "select_claim_source_personal 已点击 selector=label.weui-desktop-form__check-label:has-text('个人观点，仅供参考')" in step_logs
    assert "confirm_claim_source_setting 已点击 selector=button.weui-desktop-btn.weui-desktop-btn_primary:has-text('确认')" in step_logs


def test_wechat_publish_settings_selector_profile_covers_collection_and_claim_source():
    profile = get_selector_profile("wechat-mp-v1")

    assert profile["collection_setting"][0] == "div.js_article_tags_label"
    assert profile["collection_picker_input"][0] == "span.weui-desktop-form__input-wrp:has(input.weui-desktop-form__input[placeholder='请选择合集'])"
    assert "input.weui-desktop-form__input[placeholder='请选择合集']" in profile["collection_picker_input"]
    assert profile["collection_ai_news_option"][0] == "li.select-opt-li:has-text('AI新闻')"
    assert profile["claim_source_setting"][0] == "div.js_claim_source_desc"
    assert profile["claim_source_personal_option"][0] == "label.weui-desktop-form__check-label:has-text('个人观点，仅供参考')"
    assert profile["option_confirm_button"][0] == "button.weui-desktop-btn.weui-desktop-btn_primary:has-text('确认')"


def test_build_ai_cover_prompt_uses_article_context_within_wechat_limit():
    prompt = _build_ai_cover_prompt(
        {
            "title": "AI芯片公司发布新一代推理加速卡",
            "summary": "面向数据中心低功耗部署，强调吞吐和成本。",
            "markdown": "# AI芯片公司发布新一代推理加速卡\n\n这是一篇关于芯片产业链和企业部署的新闻分析。",
        }
    )

    assert len(prompt) <= 50
    assert prompt.startswith("公众号封面，")
    assert "AI芯片公司" in prompt


def test_wechat_publish_selector_profile_covers_ai_cover_and_qrcode_stop():
    profile = get_selector_profile("wechat-mp-v1")

    assert profile["cover_button"][0] == "div.select-cover__btn.js_cover_btn_area.select-cover__mask"
    assert profile["ai_image_button"][0] == "a.pop-opr__button.js_aiImage:has-text('AI 配图')"
    assert profile["ai_image_prompt"][0] == "textarea#ai-image-prompt"
    assert profile["article_publish_button"][0] == "#js_send button.mass_send:has-text('发表')"
    assert profile["wechat_verify_qrcode"][0] == ".dialog:has-text('微信验证') img.js_qrcode"


def test_ensure_wechat_ai_cover_clicks_cover_generation_flow_in_order():
    profile = get_selector_profile("wechat-mp-v1")
    cover_node = _FakeNode(visible=True)
    ai_image_node = _FakeNode(visible=True)
    prompt_node = _FakeNode(visible=True)
    send_node = _FakeNode(visible=True)
    generated_tip_node = _FakeNode(visible=True)
    use_node = _FakeNode(visible=True)
    confirm_node = _FakeNode(visible=True)
    page = _FakePage(
        {
            "div.select-cover__btn.js_cover_btn_area.select-cover__mask": [cover_node],
            "a.pop-opr__button.js_aiImage:has-text('AI 配图')": [ai_image_node],
            "textarea#ai-image-prompt": [prompt_node],
            "button.send-btn": [send_node],
            "p.ai-image__tips:has-text('已为你生成图片')": [generated_tip_node],
            ".ai-image-operation-group .ai-image-op-btn:has-text('使用')": [use_node],
            ".weui-desktop-btn_wrp button.weui-desktop-btn_primary:has-text('确认')": [confirm_node],
        },
        url="https://mp.weixin.qq.com/cgi-bin/appmsg?t=media/appmsg_edit_v2&action=edit",
    )
    step_logs: list[str] = []

    prompt = _ensure_wechat_ai_cover(
        page,
        profile,
        {
            "title": "AI新闻测试",
            "summary": "数据中心推理成本下降。",
            "markdown": "# AI新闻测试\n\n企业正在部署新一代AI基础设施。",
        },
        step_logs,
        initial_wait_ms=0,
        retry_wait_ms=0,
        max_checks=1,
    )

    assert prompt_node.value == prompt
    assert len(prompt) <= 50
    assert page._click_history == [
        "div.select-cover__btn.js_cover_btn_area.select-cover__mask",
        "a.pop-opr__button.js_aiImage:has-text('AI 配图')",
        "button.send-btn",
        ".ai-image-operation-group .ai-image-op-btn:has-text('使用')",
        ".weui-desktop-btn_wrp button.weui-desktop-btn_primary:has-text('确认')",
    ]
    assert "AI 封面已生成 selector=p.ai-image__tips:has-text('已为你生成图片')" in step_logs


def test_click_wechat_publish_until_qrcode_stops_with_scan_required_status():
    profile = get_selector_profile("wechat-mp-v1")
    publish_node = _FakeNode(visible=True)
    modal_publish_node = _FakeNode(visible=True)
    continue_node = _FakeNode(visible=True)
    qrcode_node = _FakeNode(visible=True)
    page = _FakePage(
        {
            "#js_send button.mass_send:has-text('发表')": [publish_node],
            ".weui-desktop-btn_wrp[slot='target'] button.weui-desktop-btn_primary:has-text('发表')": [modal_publish_node],
            "button.weui-desktop-btn_primary:has-text('继续发表')": [continue_node],
            ".dialog:has-text('微信验证') img.js_qrcode": [qrcode_node],
        },
        url="https://mp.weixin.qq.com/cgi-bin/appmsg?t=media/appmsg_edit_v2&action=edit",
    )
    step_logs: list[str] = []
    screenshot_path = "runtime/test-artifacts/wechat-qrcode.png"

    delta, artifacts = _click_wechat_publish_until_qrcode(
        page,
        profile,
        step_logs,
        screenshot_path,
        max_continue_clicks=3,
        qrcode_retry_wait_ms=0,
        max_qrcode_checks=1,
    )

    assert delta["verification_status"] == "wechat_qrcode_required"
    assert delta["verification_message"] == "已到微信验证二维码，请扫码确认。"
    assert delta["is_session_level_error"] is False
    assert artifacts == [str(screenshot_path)]
    assert page._screenshots == [str(screenshot_path)]
    assert page._click_history == [
        "#js_send button.mass_send:has-text('发表')",
        ".weui-desktop-btn_wrp[slot='target'] button.weui-desktop-btn_primary:has-text('发表')",
        "button.weui-desktop-btn_primary:has-text('继续发表')",
        "button.weui-desktop-btn_primary:has-text('继续发表')",
        "button.weui-desktop-btn_primary:has-text('继续发表')",
    ]
    assert "已到微信验证二维码 selector=.dialog:has-text('微信验证') img.js_qrcode" in step_logs


def test_run_publish_to_qrcode_uses_existing_editor_path_without_saving_draft():
    profile = get_selector_profile("wechat-mp-v1")
    home = _FakePage(
        {
            ".new-creation__menu-item:has(.new-creation__menu-title:text-is('文章'))": [_FakeNode(visible=True)],
            ".weui-desktop-account__thumb": [_FakeNode(visible=True)],
            "a#menu_10125[href*='action=list_card']": [_FakeNode(visible=True)],
            ".publish_card_container": [_FakeNode(visible=True)],
        },
        url="https://mp.weixin.qq.com/",
    )
    save_draft_node = _FakeNode(visible=True)
    editor = _FakePage(
        {
            "textarea.js_article_title": [_FakeNode(visible=True)],
            "input.js_author": [_FakeNode(visible=True)],
            "textarea.js_desc": [_FakeNode(visible=True)],
            "#edui1_iframeholder .mock-iframe-body .rich_media_content > div.ProseMirror[contenteditable='true']": [_FakeNode(visible=True)],
            "#js_original": [_FakeNode(visible=True)],
            "#js_reward_setting_area": [_FakeNode(visible=True)],
            "div.js_article_tags_label": [_FakeNode(visible=True)],
            "input.weui-desktop-form__input[placeholder='请选择合集']": [_FakeNode(visible=True)],
            "li.select-opt-li:has-text('AI新闻')": [_FakeNode(visible=True)],
            "div.js_claim_source_desc": [_FakeNode(visible=True)],
            "label.weui-desktop-form__check-label:has-text('个人观点，仅供参考')": [_FakeNode(visible=True)],
            "button.weui-desktop-btn.weui-desktop-btn_primary:has-text('确定')": [_FakeNode(visible=True)],
            "button.weui-desktop-btn.weui-desktop-btn_primary:has-text('确认')": [
                _FakeNode(visible=True),
                _FakeNode(visible=True),
                _FakeNode(visible=True),
            ],
            ".weui-desktop-btn_wrp button.weui-desktop-btn_primary:has-text('确认')": [_FakeNode(visible=True)],
            "button:has-text('保存为草稿')": [save_draft_node],
            "div.select-cover__btn.js_cover_btn_area.select-cover__mask": [_FakeNode(visible=True)],
            "a.pop-opr__button.js_aiImage:has-text('AI 配图')": [_FakeNode(visible=True)],
            "textarea#ai-image-prompt": [_FakeNode(visible=True)],
            "button.send-btn": [_FakeNode(visible=True)],
            "p.ai-image__tips:has-text('已为你生成图片')": [_FakeNode(visible=True)],
            ".ai-image-operation-group .ai-image-op-btn:has-text('使用')": [_FakeNode(visible=True)],
            "#js_send button.mass_send:has-text('发表')": [_FakeNode(visible=True)],
            ".weui-desktop-btn_wrp[slot='target'] button.weui-desktop-btn_primary:has-text('发表')": [_FakeNode(visible=True)],
            "button.weui-desktop-btn_primary:has-text('继续发表')": [_FakeNode(visible=True)],
            ".dialog:has-text('微信验证') img.js_qrcode": [_FakeNode(visible=True)],
        },
        url="https://mp.weixin.qq.com/cgi-bin/appmsg?t=media/appmsg_edit_v2&action=edit",
    )
    context = _FakeContext([home])
    home._context = context
    home._existing_editor_page = editor
    home._close_fails = True
    home._remote_draft_items = [
            {
                "title": "AI新闻测试",
                "url": "",
                "appmsg_id": None,
                "updated_at": "2026-06-20",
                "remote_key": "card:ai新闻测试|updated:2026-06-20|0",
            }
        ]
    step_logs: list[str] = []

    delta, artifacts, _, final_page = _run_publish_to_qrcode(
        context,
        home,
        {
            "id": "brief-publish-test",
            "title": "AI新闻测试",
            "summary": "数据中心推理成本下降。",
            "markdown": "# AI新闻测试\n\n企业正在部署新一代AI基础设施，并形成新的产业分工。",
        },
        {"author": "AutoNews"},
        "https://mp.weixin.qq.com/",
        profile,
        {},
        step_logs,
        "runtime/test-artifacts/wechat-publish-qrcode.png",
    )

    assert final_page is editor
    assert delta["verification_status"] == "wechat_qrcode_required"
    assert artifacts == ["runtime/test-artifacts/wechat-publish-qrcode.png"]
    assert save_draft_node.click_count == 0
    assert ".new-creation__menu-item:has(.new-creation__menu-title:text-is('文章'))" not in home._click_history
    assert "a#menu_10125[href*='action=list_card']" in home._click_history
    assert "#js_send button.mass_send:has-text('发表')" in editor._click_history
    assert ".dialog:has-text('微信验证') img.js_qrcode" not in editor._click_history
    assert "已从公众号后台首页开始真实发表路径。" in step_logs
    assert any("已打开已有远端草稿" in log for log in step_logs)
    assert any("目标编辑页已确认，继续执行" in log for log in step_logs)


def test_run_browser_action_publish_wechat_article_returns_qrcode_required(monkeypatch):
    home = _FakePage(
        {
            ".new-creation__menu-item:has(.new-creation__menu-title:text-is('文章'))": [_FakeNode(visible=True)],
            ".weui-desktop-account__thumb": [_FakeNode(visible=True)],
            "a#menu_10125[href*='action=list_card']": [_FakeNode(visible=True)],
            ".publish_card_container": [_FakeNode(visible=True)],
        },
        url="https://mp.weixin.qq.com/",
    )
    editor = _FakePage(
        {
            "textarea.js_article_title": [_FakeNode(visible=True)],
            "input.js_author": [_FakeNode(visible=True)],
            "textarea.js_desc": [_FakeNode(visible=True)],
            "#edui1_iframeholder .mock-iframe-body .rich_media_content > div.ProseMirror[contenteditable='true']": [_FakeNode(visible=True)],
            "#js_original": [_FakeNode(visible=True)],
            "#js_reward_setting_area": [_FakeNode(visible=True)],
            "div.js_article_tags_label": [_FakeNode(visible=True)],
            "input.weui-desktop-form__input[placeholder='请选择合集']": [_FakeNode(visible=True)],
            "li.select-opt-li:has-text('AI新闻')": [_FakeNode(visible=True)],
            "div.js_claim_source_desc": [_FakeNode(visible=True)],
            "label.weui-desktop-form__check-label:has-text('个人观点，仅供参考')": [_FakeNode(visible=True)],
            "button.weui-desktop-btn.weui-desktop-btn_primary:has-text('确定')": [_FakeNode(visible=True)],
            "button.weui-desktop-btn.weui-desktop-btn_primary:has-text('确认')": [
                _FakeNode(visible=True),
                _FakeNode(visible=True),
                _FakeNode(visible=True),
            ],
            ".weui-desktop-btn_wrp button.weui-desktop-btn_primary:has-text('确认')": [_FakeNode(visible=True)],
            "div.select-cover__btn.js_cover_btn_area.select-cover__mask": [_FakeNode(visible=True)],
            "a.pop-opr__button.js_aiImage:has-text('AI 配图')": [_FakeNode(visible=True)],
            "textarea#ai-image-prompt": [_FakeNode(visible=True)],
            "button.send-btn": [_FakeNode(visible=True)],
            "p.ai-image__tips:has-text('已为你生成图片')": [_FakeNode(visible=True)],
            ".ai-image-operation-group .ai-image-op-btn:has-text('使用')": [_FakeNode(visible=True)],
            "#js_send button.mass_send:has-text('发表')": [_FakeNode(visible=True)],
            ".weui-desktop-btn_wrp[slot='target'] button.weui-desktop-btn_primary:has-text('发表')": [_FakeNode(visible=True)],
            "button.weui-desktop-btn_primary:has-text('继续发表')": [_FakeNode(visible=True)],
            ".dialog:has-text('微信验证') img.js_qrcode": [_FakeNode(visible=True)],
        },
        url="https://mp.weixin.qq.com/cgi-bin/appmsg?t=media/appmsg_edit_v2&action=edit",
    )
    context = _FakeContext([home])
    home._context = context
    home._existing_editor_page = editor
    home._remote_draft_items = [
            {
                "title": "AI新闻测试",
                "url": "",
                "appmsg_id": None,
                "updated_at": "2026-06-20",
                "remote_key": "card:ai新闻测试|updated:2026-06-20|0",
            }
        ]

    class _FakeManager:
        def with_session(self, _channel, restore_window, action_fn):
            action_fn(context, home)

        def manager_state(self):
            return {"manager_alive": True, "last_action": "publish_wechat_article"}

        def set_action_state(self, *_args, **_kwargs):
            return None

        def set_resident_page(self, *_args, **_kwargs):
            return None

        def capture_screenshot(self, _path):
            return False, ""

    monkeypatch.setattr("backend.app.publishers.wechat.editor.WECHAT_BROWSER_MANAGER", _FakeManager())

    browser_state, artifacts, step_logs = run_browser_action(
        "publish_wechat_article",
        {
            "id": "brief-action-test",
            "title": "AI新闻测试",
            "summary": "数据中心推理成本下降。",
            "markdown": "# AI新闻测试\n\n企业正在部署新一代AI基础设施，并形成新的产业分工。",
        },
        {
            "author": "AutoNews",
            "selectors_version": "wechat-mp-v1",
            "publish_entry_url": "https://mp.weixin.qq.com/",
        },
        {"logged_in": True},
    )

    assert browser_state["verification_status"] == "wechat_qrcode_required"
    assert browser_state["verification_message"] == "已到微信验证二维码，请扫码确认。"
    assert browser_state["last_error"] is None
    assert artifacts and artifacts[0].endswith(".png")
    assert "当前版本不会在无页面校准证据时自动点击最终发布按钮。" not in step_logs


def test_apply_wechat_publish_settings_recovers_from_hover_popover_intercept():
    profile = get_selector_profile("wechat-mp-v1")
    original_node = _FakeNode(visible=True)
    confirm_done_node = _FakeNode(visible=True)
    reward_node = _FakeNode(visible=True)
    collection_node = _FakeNode(visible=True, fail_first_click=True)
    collection_picker_node = _FakeNode(visible=True)
    ai_news_node = _FakeNode(visible=True)
    claim_source_node = _FakeNode(visible=True)
    personal_source_node = _FakeNode(visible=True)
    confirm_ok_node = _FakeNode(visible=True)
    page = _FakePage(
        {
            "#js_original": [original_node],
            "#js_reward_setting_area": [reward_node],
            "div.js_article_tags_label": [collection_node],
            "input.weui-desktop-form__input[placeholder='请选择合集']": [collection_picker_node],
            "li.select-opt-li:has-text('AI新闻')": [ai_news_node],
            "div.js_claim_source_desc": [claim_source_node],
            "label.weui-desktop-form__check-label:has-text('个人观点，仅供参考')": [personal_source_node],
            "button.weui-desktop-btn.weui-desktop-btn_primary:has-text('确定')": [confirm_done_node],
            "button.weui-desktop-btn.weui-desktop-btn_primary:has-text('确认')": [confirm_ok_node],
        },
        url="https://mp.weixin.qq.com/cgi-bin/appmsg?t=media/appmsg_edit_v2&action=edit",
    )
    step_logs: list[str] = []

    _apply_wechat_publish_settings(page, profile, step_logs)

    assert collection_node.clicked is True
    assert collection_node.click_count == 2
    assert "open_collection_setting 首次点击失败：popover intercepts pointer events" in step_logs
    assert "open_collection_setting 已尝试关闭悬浮提示" in step_logs


def test_select_hidden_wechat_option_by_text_dispatches_hidden_select_option():
    hidden_node = _FakeNode(visible=False)
    hidden_node.text_content = "AI新闻"
    page = _FakePage({"li.select-opt-li": [hidden_node]})
    step_logs: list[str] = []

    selected = _select_hidden_wechat_option_by_text(
        page,
        "AI新闻",
        step_logs,
        step_name="select_collection_ai_news",
    )

    assert selected is True
    assert page._hidden_option_selected is True
    assert hidden_node.clicked is True
    assert "select_collection_ai_news 已通过隐藏选项事件选择 text=AI新闻" in step_logs


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
