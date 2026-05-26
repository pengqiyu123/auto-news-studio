# 0.2.11 更新说明

本次版本聚焦两件事：

- 让 PostgreSQL 真正成为传统模式上传前链路里的稳定总账
- 补齐微信草稿箱与本地 brief 总账之间的前端显示闭环

## 本次重点

### 1. PostgreSQL 读链补齐 deep-dive / brief 关联

- `STATE_BACKEND=postgres` 下，事件列表读链会稳定带回：
  - `deep_dive_id`
  - `deep_dive_status`
  - `brief_id`
  - `brief_status`
  - `deep_dive_summary`
- 深挖池前端继续读取 `/api/admin/intel/events`，但现在不再依赖旧投影恰好被刷新。

### 2. 微信草稿箱“本地记录详情”改为按需读取单条 brief 详情

- 草稿箱页继续使用 briefs 轻量列表做列表渲染
- 展开“文章详情”时，前端会按需调用 `GET /api/admin/briefs/{id}`
- 后端单条详情返回完整正文相关字段，包括：
  - `prompt_package_markdown`
  - `facts`
  - `quotes`
  - `timeline`
  - `wechat_markdown`
  - `wechat_html`

### 3. 修复微信草稿箱“本地记录数据没了”的加载时机问题

- 进入“微信草稿箱”页时，现在会同步刷新 briefs 总账
- 不再要求用户先打开“简报”页，本地记录就能正常显示

## 修复

- 修复 PostgreSQL 模式下深挖池因事件读链缺少内容域关联而看起来“没数据”的问题
- 修复草稿箱本地记录详情误把轻量列表字段当详情字段的问题
- 修复草稿箱页首次进入时 briefs 未加载导致“本地记录为空”的问题
- 补齐数据库读模型在 SQLite / PostgreSQL 下的兼容读取与 JSON 字段反序列化

## 验证

- 后端定向测试通过：
  - `backend/tests/test_db_ingest_projection.py`
  - `backend/tests/test_briefs_mixin.py`
- 前端定向测试通过：
  - `src/hooks/content/useBriefsState.test.tsx`
  - `src/hooks/wechat/useWechatState.test.tsx`
- 前端构建通过：
  - `npm run build`

## 发布说明

- 版本号已更新为 `0.2.11`
- GitHub Releases 需要同步发布 `v0.2.11`
- Windows 分发包应重新构建并上传 `dist/windows/auto-news-studio-windows.zip`
