# 0.2.13 更新说明

## 本次重点

- **传统模式重构为 2 模式**：原来的 3 个模式（radar_only / radar_and_draft / full_pipeline）简化为"手动模式"和"计划模式"，降低使用门槛。
- **每日科技速递合集**：传统模式现在生成"今日科技速递｜YYYY-MM-DD"多事件合集（3-5 条事件合 1 篇），不再为每个事件单独生成简报。
- **按热度自动选事件**：新增 `top_scored` 准入策略，按综合评分选事件，不再要求 alert_state 达到 rising/breakout，第一轮采集就能产出内容。
- **4 档交付设置**：不生成简报 / 仅生成本地简报 / 立即上传微信 / 定时批量上传，计划模式下自由组合。
- **Agent 会话可放弃**：前端简报页对 running/failed 的 Agent 会话新增"放弃"按钮。
- **动态速递模板**：每日速递的 `why_it_matters` 和正文开头根据入选事件的实体名、标签、alert_state 动态生成，不再是固定文案。
- **重复生成保护**：同一天重复生成今日速递时，复用已有 digest 并更新，不会创建重复简报。
- **Brief 详情页展示收录事件**：digest brief 详情中展示收录的事件列表（标题、状态、来源数、深挖状态）。

## 修复

- 修复传统模式启动时事件全部为 new 状态导致无法自动产出内容的问题
- 修复前端"生成今日速递"按钮在已有当日 digest 时未正确置灰的问题
- 修复 Agent 会话残留时阻塞传统模式启动的问题（新增放弃入口）
- 旧模式用户自动迁移：radar_only → 手动模式，radar_and_draft → 计划模式+本地简报，full_pipeline → 计划模式+立即上传

## 验证

- 后端：`pytest backend/tests/ -q` — 115 passed
- 前端：`npm test -- --run` — 23 passed
- 前端构建：`npm run build` — 通过
- 交付设置 4 档组合逻辑验证通过
- top_scored 策略：alert_state=new 的事件能入选
- 模式迁移：旧 state.json 自动升级到新模式

## 注意

- 微信自动上传策略未变更，现有手动上传入口保留
- Agent 模式不受影响，仍通过 AGENT.md 驱动
- 旧模式 key（radar_only 等）保留后端兼容，前端不展示
