# 0.2.8 更新说明

## 本次重点
- 新增抖音创作者中心基础链路：支持独立浏览器 session、打开创作者中心、进入文章发布页、探测发布页结构，并可自动填充标题、摘要、正文与触发 `AI 配图`。
- 重构“简报”状态模型：简报页不再以 `prepared / synced / failed` 作为主视图，而是切换为本地总账三态 `仅本地 / 已同步草稿箱 / 已同步发表记录`，并叠加 `待确认 / 草稿箱检查失败 / 发表记录检查失败 / 草稿已丢失` 异常标记。
- 重构微信草稿箱工作台：页面职责改为“微信端 + 本地记录 + 待确认”三视图，本地记录直接复用同一份 `briefs` 总账，不再创建第二份本地库。
- 后端新增统一的微信对账投影：`/api/admin/briefs` 与 `/api/admin/briefs/{brief_id}` 现会基于最近一次微信草稿箱和发表记录快照，实时返回 `record_status`、`record_exception`、`record_counts` 等派生字段。

## 对业务使用的影响
- Agent 长文、传统简报、增强简报会继续共用同一份本地总账，便于统一查看“仅本地 / 已进草稿箱 / 已发表”的真实状态。
- 发表记录页仍保持只读，不承担本地管理职责。
- 微信草稿箱页中的“本地记录”只是总账视图，不会额外持久化第二份本地数据。

## 验证
- 后端：`python -m pytest backend/tests/test_admin_pagination.py backend/tests/test_agent_upload_guard.py -q`
- 前端：`cd frontend && npm test -- --run src/components/BriefTable.test.tsx`
- 构建：`cd frontend && npm run build`

## 兼容性
- 版本号已更新为 `0.2.8`。
- GitHub Releases 需要同步发布 `v0.2.8`，旧版本才会识别到本次更新。

## 备注
- 当前自动微信检查逻辑仍保留现状；本次主要修正的是“状态模型与界面展示”，未一并关闭后台自动检查。
- 分发包继续包含项目 `.venv`，保持 Windows 离线可安装。
