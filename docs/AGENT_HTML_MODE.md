# Agent HTML Mode

`agent-html` 是项目中的 HTML 结构化采集与维护链，用于补足传统 RSS 模式无法覆盖的品牌新闻页、博客页和更新页，并将合格结果并入主项目主链。

## 设计目标

- 获取与维护侧独立
- 入库后可并入主项目 `raw_items` 主链
- 支持长期运行后的新旧判断
- 支持同一页面内容更新后的 revision 历史
- 支持多篇相关页面形成独立事件与发展历程
- 页面结构变更时可排障、可重提取

## 数据流

`html_targets -> html_runs -> html_discovery_items -> html_events -> html_event_snapshots -> html_event_history`

内容侧：

`html_documents -> html_document_revisions`

缓存：

- `runtime/cache/agent_html/list_pages/`
- `runtime/cache/agent_html/detail_pages/`

## 接口

- `POST /api/admin/agent-html/targets`
- `GET /api/admin/agent-html/targets`
- `PATCH /api/admin/agent-html/targets/{target_id}`
- `POST /api/admin/agent-html/targets/{target_id}/run`
- `POST /api/admin/agent-html/runs/batch`
- `POST /api/admin/agent-html/mainline-sync`
- `GET /api/admin/agent-html/runs`
- `GET /api/admin/agent-html/discovery`
- `GET /api/admin/agent-html/events`
- `GET /api/admin/agent-html/events/{event_id}`
- `GET /api/admin/agent-html/documents`
- `GET /api/admin/agent-html/documents/{document_id}`
- `POST /api/admin/agent-html/documents/{document_id}/reextract`

## 主链融合

第一阶段采用：

- 先 RSS
- 后 HTML
- HTML 结果映射为 RSS 风格 `raw_items`
- 后续统一进入：
  `discovery_items -> intel_events -> intel_alerts -> deep-dive -> brief -> agent article`

`POST /api/admin/agent-html/mainline-sync` 的职责是：

1. 执行指定 HTML target 抓取
2. 保留 HTML 文档与 revision 历史
3. 将当前成功文档映射为主链 `raw_items`
4. 重建统一事件与预警主链

这意味着：

- `agent-html` 仍然保留文档 revision、缓存、重提取能力
- 但热点、预警、深挖、简报不再依赖独立 `agent_html_events` 作为最终交付池

## 发现策略

第一版采用：

- 规则优先
- AI 兜底

当目标页配置的 `discovery_rules` 足以发现文章链接时，不调用 AI。  
当规则解析为空或明显异常时，才尝试使用 LLM 输出结构化候选项。

## 判重与版本策略

同一文档优先按以下规则判断：

- `canonical_url` 相同且 `content_hash` 不变：旧文档
- `canonical_url` 相同但 `content_hash` 变化：同一文档新版本
- 不同 `canonical_url`：先视作不同发现项，再由事件聚合层判断是否同主题

同一文档发生变化时，不覆盖旧内容，而是新增一条 `html_document_revision`。

## 事件聚合

第一版使用保守聚合：

- 同品牌或同目标域
- 时间接近
- 标题关键词重叠度高

无法高置信归并时，宁可新建事件，也不误并。

## 运维建议

- 优先配置品牌官方新闻列表页、博客列表页
- 每个 target 都尽量提供 `link_allow_patterns`
- 页面结构变更时，先检查 `runtime/cache/agent_html/` 中的列表页和详情页缓存
- 抽取失败但页面可打开时，优先使用 `reextract` 验证是否只是正文提取失效
- 站点已确认存在稳定 RSS 时，优先走 RSS，不重复消耗 HTML 维护成本
