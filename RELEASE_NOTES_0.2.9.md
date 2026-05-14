# 0.2.9 更新说明

本次版本聚焦两件事：

1. 强化 AI 写作主链路，让摘要、写作规范、事实约束和复审要求真正进入实际生成流程。
2. 修复传统模式前端重复启动时不断堆新标签页的问题，改为受管仪表盘页优先复用已有页面。

## 主要更新

### 1. 写作链路 P0 强化

- 升级默认写作规范，补齐标题策略、摘要写法、导语要求、结构节奏、结尾方式、反 AI 味约束、事实与引文底线。
- `deep_dive.article_writing_guide` 与 `prompt_package_markdown` 现在共用同一套写作规范，不再一处更新、一处滞后。
- 简报与 Agent 长文记录新增稳定 `summary` 字段，可直接复用到公众号摘要位。
- 摘要生成支持固定兜底顺序：传入 `summary` → `one_line` → 首条高信息量事实 → 事件原始摘要。
- 微信草稿同步时优先使用记录上的 `summary`，历史旧记录缺失时会自动按同样顺序兜底。

### 2. Agent 写作流程要求升级

- `AGENT.md` 明确要求 Agent 采用 `write -> critique -> revise -> save` 流程。
- Critique 必查四类问题：
  - 事实、数字、日期、引文是否可溯源
  - 标题、摘要、导语、小标题、结尾是否符合规范
  - 是否存在明显 AI 味和重复段式
  - 结构与段落节奏是否松散单一
- 若 Critique 后仍不达标，Agent 应停止保存，而不是把低质量稿件写入共享总账。

### 3. 传统模式前端启动体验修复

- `start.bat` / `scripts/start_backend.ps1` 现在打开受管仪表盘页，不再每次重复启动都无脑新开一个 `127.0.0.1:8000` 标签页。
- 前端新增受管仪表盘页逻辑：重复启动时会优先唤醒已有仪表盘页，并让新页自行退出。
- 当后端停止后，受管仪表盘页会做健康检查并尽量自我关闭；若浏览器限制 `window.close()`，会退回空白页，避免越积越多。

## 兼容性说明

- 本次未新增业务路由，现有传统模式与 Agent 模式接口路径保持不变。
- 历史无 `summary` 的旧记录无需一次性迁移，读取和发布时都会自动兜底。

## 验证情况

- 后端相关测试通过：
  - `backend/tests/test_wechat_format.py`
  - `backend/tests/test_briefs_mixin.py`
  - `backend/tests/test_wechat_mixin.py`
  - `backend/tests/test_admin_pagination.py`
  - `backend/tests/test_wechat_selector_visibility.py`
- 前端已完成生产构建验证：`cd frontend && npm run build`

## 发布说明

- 版本号已更新为 `0.2.9`。
- GitHub Releases 需要同步发布 `v0.2.9`，旧版本客户端才会识别到本次更新。
