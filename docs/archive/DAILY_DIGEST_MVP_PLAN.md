# 传统模式每日短讯合集 MVP 计划

## Summary
把传统自动链路改成固定产出 1 篇“今日短讯合集”：`Top 3-5 个事件 -> 1 条本地 brief`。不做多对多建模、不做数据库迁移、不改前端、不处理微信上传策略。

传统模式只有这一种产物；Agent 模式继续负责短讯/长文/混合的多格式判断。

## Key Changes
- `briefing.py`：新增 `build_daily_digest_brief_payload(events, deep_dives)`，纯规则拼装，不调用 LLM。
- `briefs_mixin.py`：新增 `create_daily_digest_brief_from_events(event_ids, triggered_by)`，生成 1 条 `BriefItem`。
- `delivery_mixin.py`：briefing 阶段不再逐个 `create_brief_from_event()`，改为对合格事件一次性生成 digest brief。
- 不改 `BriefLevel`，合集仍是 `brief_level="rule"`。
- 不新增 `brief_kind/event_ids/deep_dive_ids` 字段，不做 Alembic 迁移。
- 保留 `create_brief_from_event()`，它仍是手动/Agent 素材用的单事件 brief 入口。

## Digest Rules
- 默认从现有 delivery 选题结果中取 3-5 条，硬上限 5。
- 最低 2 条；少于 2 条合格事件时跳过生成并写日志，不降级成单事件短讯。
- 合格条件：未忽略、未已有 brief、deep dive 为 `ready` 或 `partial`、有来源链接、有 facts 或可用摘要。
- 生成后只创建 1 条 brief，`event_id/deep_dive_id` 使用排序第一的主事件作为兼容锚点。
- 同时把所有成员事件的 `brief_id` 和 `brief_status="prepared"` 回写为这条 digest brief，用现有字段防止下一轮重复入选。
- `wechat_markdown` 格式为：

```markdown
# 今日科技速递｜YYYY-MM-DD

今天值得关注的科技动态有 N 条。

## 1. 事件标题
发生了什么。为什么值得看。还不确定什么。

## 2. 事件标题
...

## 来源链接
- 事件标题：URL
```

## Upload Boundary
- 本阶段不自动上传微信。
- `radar_and_draft` 和 `full_pipeline` 在本 MVP 中都只验证“生成本地合集 brief”。
- 现有手动 `/api/admin/briefs/{brief_id}/wechat-draft` 不删除、不改语义，后续单独设计上传策略。

## Test Plan
- `test_briefs_mixin.py`：多事件生成 1 条 digest brief；正文包含多个编号事件；`brief_level=="rule"`；主事件锚点存在；所有成员事件回写同一个 `brief_id`。
- `test_briefs_mixin.py`：只有 1 条合格事件时不生成 digest brief，并记录跳过原因。
- `test_runtime_mixin.py` 或 delivery 测试：传统 delivery deep dive 多个事件后 `brief_count==1`，不再生成 N 条 brief。
- 回归：旧 `create_brief_from_event()` 单事件 brief 测试继续通过。
- 回归：`pytest auto-news-studio\backend\tests\test_briefs_mixin.py -q`、`pytest auto-news-studio\backend\tests\test_runtime_mixin.py -q`。
