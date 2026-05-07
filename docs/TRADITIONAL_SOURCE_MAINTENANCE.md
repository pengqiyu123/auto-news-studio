# 传统模式信息源维护

本文档只针对 `传统模式` 的信息获取策略。

## 原则

传统模式以稳定、低维护的结构化源为主：

- 优先 `RSS/Atom`
- 可接受少量长期稳定的 `WordPress REST`
- 不把登录页、社媒时间线、纯 HTML 抓取页作为常规传统自动化来源

这样做的目标是让定时采集可预测、低成本、易排障。

## 当前维护方式

### 1. 现有内置源

项目默认内置一批来源，定义在：

- `backend/app/sources/rss/`
- `backend/app/sources/hotlists/`
- `backend/app/sources/monitors/`

这些适合长期保存在仓库默认配置里。

### 2. 运行时补源

对于后续新增的传统 RSS 源，优先通过运行时 API 写入：

- `POST /api/admin/sources`
- `PUT /api/admin/sources/{source_key}`
- `POST /api/admin/sources/{source_key}/sync`

这样可以先在真实环境里验证稳定性，再决定是否沉淀回默认源。

### 3. 品牌官方源审计

若要为品牌补传统 RSS 源，先运行：

```powershell
.venv\Scripts\python scripts\validate_brand_sources.py
```

输出：

- `runtime/brand-source-audit/brand_sources_latest.json`
- `runtime/brand-source-audit/brand_sources_latest.md`

只有报告中明确验证成功的源，才建议加入传统模式。

## 建议工作流

1. 先通过脚本或人工整理出候选站点
2. 验证是否存在 `RSS/Atom` 或 `WordPress REST`
3. 用项目当前采集逻辑测试是否能正常返回条目
4. 通过运行时 API 写入并做一次单源同步
5. 观察一段时间后，再决定是否沉淀为默认源

## 不建议直接纳入传统模式的来源

- 需要登录的后台页面
- 仅有 HTML 新闻列表、没有稳定 feed 的页面
- 依赖复杂 JS 渲染才能拿到正文的站点
- 高频超时、403、证书异常的站点

这些更适合后续放到 agent 模式处理。
