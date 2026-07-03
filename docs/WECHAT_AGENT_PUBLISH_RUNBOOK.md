# 微信 Agent 发表前确认 Runbook

本文件给 Codex、Trae、Claude Code 等 AI Agent 使用。目标是让另一个 AI 能按真实链路打开已有微信公众号草稿，补齐发表前设置，并点击到微信验证二维码处停止。

最后验证时间：2026-06-21

## 核心结论

- 使用真实项目 API、真实浏览器状态、真实微信公众号草稿。
- 每一步成功后再进入下一步，不要一次性全链路乱点。
- 草稿箱到编辑页的可靠路径是：`草稿箱 -> 目标草稿 -> 操作区“编辑”按钮 -> action=edit 编辑页`。
- 文章标题、封面、第一个链接或普通 `/s/` 链接通常是预览入口，不是编辑入口。
- 到达微信验证二维码只代表 `pending_confirmation`，不代表已发布。
- 不要输出 token、二维码链接、账号敏感 URL 或浏览器 profile 私密信息。

## 启动与健康检查

在项目目录执行：

```powershell
cd D:\python\Auto-news2\auto-news-studio
.\stop.bat
.\start.bat
Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/health' -TimeoutSec 10
```

成功标准：

```text
status = ok
```

## 打开指定草稿

先打开远端草稿，不要直接触发发表。

```powershell
$body = @{ title = '<目标草稿标题>' } | ConvertTo-Json -Compress
Invoke-RestMethod `
  -Method Post `
  -Uri 'http://127.0.0.1:8000/api/admin/browser/wechat/open-remote-draft' `
  -ContentType 'application/json' `
  -Body $body `
  -TimeoutSec 180
```

成功标准：

```text
message = 已打开指定远端草稿编辑页。
url 包含 action=edit
step_logs 包含 已点击目标草稿编辑按钮
step_logs 包含 单标签页收敛
```

失败判断：

- URL 包含 `action=list_card`：仍在草稿箱。
- URL 是普通 `/s/` 链接：进入了预览页。
- 截图还是草稿箱：保留 `action=edit` 标签页，关闭或忽略草稿箱标签页。

## 发表前设置

已有草稿发表前确认不走“保存草稿”作为最后一步。正确路径是在编辑页补齐设置后直接进入发表链路。

需要确认：

1. 封面存在。如果已经有 `.js_cover_preview_new`、`.select-cover__preview`、`.first_appmsg_cover` 等封面预览并带图片，应跳过 AI 封面生成。
2. 原创声明开启。
3. 赞赏开启。
4. 合集选择 `AI新闻`。
5. 创作来源选择 `个人观点，仅供参考`。

合集注意点：

- 点击“合集 / 未添加”后，还要点击输入框才会展开选项。
- 输入框常见 DOM：

```html
<input type="text" placeholder="请选择合集" class="weui-desktop-form__input">
```

- 展开后选择：

```html
<li class="select-opt-li">AI新闻</li>
```

创作来源注意点：

- 点击“创作来源 / 未添加”后，选择：

```html
<span class="weui-desktop-form__check-content">个人观点，仅供参考</span>
```

作者注意点：

- 真实页面的 `input.js_author` 可能是 `readonly="readonly"`。
- 如果作者字段只读且已有值，例如公众号已有作者名，应沿用现有作者，不要强写后用前缀回读判失败。

## 发表按钮链路

### 1. 第一层“发表”

编辑页底部按钮：

```html
<span id="js_send" class="btn btn_input btn_default r">
  <button class="mass_send" type="button">
    <span class="send_wording">发表</span>
  </button>
</span>
```

推荐选择器：

```text
#js_send button.mass_send:has-text('发表')
#js_send .send_wording:has-text('发表')
#js_send button.mass_send
button.mass_send:has-text('发表')
```

### 2. 二次确认“发表”

第一层发表后，微信会弹出确认层。必须点击确认层里的绿色“发表”，不能再点页面底部原始发表按钮。

真实 DOM：

```html
<div class="weui-desktop-popover__wrp">
  <div class="weui-desktop-btn_wrp" slot="target">
    <button type="button" class="weui-desktop-btn weui-desktop-btn_primary">发表</button>
  </div>
  <div class="weui-desktop-btn_wrp">
    <button type="button" class="weui-desktop-btn weui-desktop-btn_default">取消</button>
  </div>
</div>
```

推荐选择器：

```text
.weui-desktop-popover__wrp .weui-desktop-btn_wrp[slot='target'] button.weui-desktop-btn_primary:has-text('发表')
.weui-desktop-popover__wrp button.weui-desktop-btn_primary:has-text('发表')
.weui-desktop-dialog__wrp button.weui-desktop-btn_primary:has-text('发表')
[role='dialog'] button.weui-desktop-btn_primary:has-text('发表')
```

不要把这些宽泛选择器作为二次确认：

```text
button.weui-desktop-btn_primary:has-text('发表')
button:has-text('发表')
```

它们可能误命中编辑页底部原始发表按钮，导致确认弹窗仍留在页面上。

### 3. “继续发表”

如果微信继续弹出确认层，点击：

```html
<button type="button" class="weui-desktop-btn weui-desktop-btn_primary">继续发表</button>
```

推荐选择器：

```text
button.weui-desktop-btn_primary:has-text('继续发表')
.weui-desktop-btn_wrp button:has-text('继续发表')
button:has-text('继续发表')
```

最多尝试 3 次，每次点击后等待 1-2 秒。

### 4. 微信验证二维码

出现二维码后必须停止。

常见 DOM：

```html
<div class="dialog">
  <div class="dialog_hd">
    <h3>微信验证</h3>
  </div>
  <div class="safe_check js_wxcheck0 js_wxchecks">
    <img class="qrcode js_qrcode" alt="微信二维码" title="微信二维码" src="/safe/safeqrcode?...">
  </div>
</div>
```

推荐选择器：

```text
.dialog:has-text('微信验证') img.js_qrcode
.safe_check img.js_qrcode
img.js_qrcode[alt='微信二维码']
img.js_qrcode
```

成功状态：

```text
delivery_status = pending_confirmation
verification_status = wechat_qrcode_required
last_error = 已到微信验证二维码，请扫码确认。
```

## 触发真实发表前确认

在打开草稿并确认 `action=edit` 后执行：

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri 'http://127.0.0.1:8000/api/admin/briefs/<brief_id>/wechat-publish?triggered_by=agent' `
  -TimeoutSec 420
```

成功标准：

```text
delivery_status = pending_confirmation
last_error = 已到微信验证二维码，请扫码确认。
last_screenshot 指向二维码截图
```

不要把这个状态写成已发布。

## 失败时证据收集

失败后立刻收集证据，不要继续盲点。

```powershell
Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/admin/browser/wechat/session' -TimeoutSec 60

Get-ChildItem `
  -LiteralPath 'runtime\temp\publish_artifacts\<brief_id>' `
  -Recurse -File |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 20 FullName,LastWriteTime,Length

Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/admin/logs?page=1&page_size=30' -TimeoutSec 60
```

报告失败时至少包含：

- 当前 URL 类型：`action=edit` / `action=list_card` / `/s/preview`
- 当前阶段：打开草稿、发布设置、封面、第一层发表、二次确认、继续发表、二维码等待
- 最新截图路径
- 关键日志中的失败 selector 或错误文本

## 回归测试

修改微信自动化后至少运行：

```powershell
python -m pytest backend\tests\test_wechat_selector_visibility.py -q
```

2026-06-21 闭环修复后的参考结果：

```text
34 passed
```
