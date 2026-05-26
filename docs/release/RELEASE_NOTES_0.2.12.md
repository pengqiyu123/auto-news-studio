# 0.2.12 更新说明

本次版本聚焦两件事：

- 将 `maomu.com/news` 这条聚合入口纳入系统可用来源
- 完成 `0.2.12` 的版本同步与发布收口

## 本次重点

### 1. 补入 `maomu.com/news` 覆盖的上游中文科技源

- 新增并固化以下 RSS 源：
  - `智东西`
  - `钛媒体`
  - `量子位`
- 这些来源用于补强 `maomu.com/news` 里已经出现、但系统原本覆盖不完整的中文科技与 AI 内容面。

### 2. 将 `maomu.com/news` 挂入默认 Agent HTML 目标

- `maomu.com/news` 作为默认可用的 Agent HTML 聚合入口加入系统状态
- 目标默认带有页面发现规则、允许域名和排除规则，便于后续直接抓取聚合页里的上游文章链接

### 3. 版本号与发布流程同步升级到 `0.2.12`

- 所有版本引用已经同步到 `0.2.12`
- 发布工作流文档已更新到新的版本号与 tag 名称

## 修复

- 修复 `version.json`、后端默认版本和前端版本展示不一致的问题
- 修复默认状态中未预置 `maomu.com/news` 的问题
- 补齐定向测试，确保新增来源与默认 Agent HTML 目标可被稳定识别

## 验证

- 后端定向测试：
  - `backend/tests/test_source_registry.py`
  - `backend/tests/test_store_core_state.py`
- 前端定向测试：
  - `frontend/src/hooks/shared/useRuntimeState.test.tsx`
- 前端构建：
  - `npm run build`
- 后端语法检查：
  - `python -m compileall backend/app`

## 发布说明

- 版本号已更新为 `0.2.12`
- GitHub Releases 需要同步发布 `v0.2.12`
- Windows 分发包应重新构建并上传 `dist/windows/auto-news-studio-windows.zip`
