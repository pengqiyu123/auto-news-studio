# Auto News Studio 增量数据链路增强方案

## Summary

本文档记录"存量数据联动新采集"方向的需求分析，不作为立即执行的开发计划。

核心目标：将沉淀的旧数据从"静态归档"转变为"动态基准库"，让新数据抓取依托旧数据做重复甄别与聚合归一，形成连贯的数据链路。

---

## 背景与动机

当前系统的数据流是"抓 → 存 → 聚类 → 预警"，历史数据仅作为聚类素材，未参与：
1. **过滤决策** — 新抓取时无历史基准，重复内容无法在抓取阶段被拦截
2. **聚合归一** — 横向（同事件多平台）聚合已有（IntelEvent），纵向（同事件跨时间）聚合未建立
3. **趋势研判** — 存量数据未形成时间序列，预警依赖单轮 velocity score，缺少显式 delta 视图

参考验证：
- Google News 用 MinHash + LSH 做新闻去重聚类，跨来源归一
- Google Incremental Crawler 用 `If-Modified-Since` + 已知 URL 集合避免重复抓取
- 业界增量爬取用 `known_uids` + `last_scraped_time` 标记历史，只取新增
- Feedly 用 "cluster propagation" 把聚类延迟从 15-20 分钟降到即时

---

## ⚠️ 调研结论（基于联网验证）

### 现状评估

| 维度 | 业界做法 | 我们现状 | 差距 |
|------|---------|---------|------|
| 数据规模 | Feedly: ~20/秒 (数十万/天) | ~259 条总数据 | **1000x+** |
| 去重策略 | Redis BloomFilter / MinHash | Jaccard ≥ 0.45 (本轮) | 需增加预过滤 |
| URL去重 | 亿级 URL 需 BloomFilter | 259 条用 SQLite SET 足够 | 当前规模不需要 |
| 聚类延迟 | 目标 <1 分钟 | 当前批量处理 | 可优化 |

### 关键发现

1. **MinHash 在小规模下不划算**
   - MinHash + LSH 是为"数十万/天"规模设计的
   - 我们当前 259 条数据，O(n²) Jaccard 比较只有 ~33,000 次
   - 增加 MinHash 依赖 + 签名存储 + 分桶逻辑，成本 > 收益
   - **建议：P3 改为"规模触发"，数据 >10,000 条时再考虑**

2. **BloomFilter 对我们过度设计**
   - 亿级 URL 才需要 BloomFilter 节省内存（~1.67GB → BloomFilter）
   - 我们 259 条数据用 SQLite SET 或 Python `set()` 足够
   - **建议：P0 改用 SQLite 持久化 `seen_links` SET，无需 Redis**

3. **Jaccard 阈值偏低**
   - 业界实践：字符级 Jaccard 通常用 0.7-0.8
   - 我们当前用 0.45，可能导致过度聚类（假阳性）
   - **建议：P1 聚类优化时考虑提高到 0.5-0.6**

4. **增量视图价值被低估**
   - OpenClaw 观点：新闻聚合器本质是"注意力管理系统"
   - Feedly cluster propagation 正是"让重复文章短路传统聚类"
   - **建议：P1 增量视图优先实现，产品价值高**

---

## 需求分层

### 需求 A：全量历史去重（历史基准库）

**目标**：新抓取前，先查历史基准，已存在则跳过，不发起网络请求。

**现状**：
- 条目级去重已存在（`canonical_link` / `dedupe_key`），但仅限本轮
- `seen_item` / `updated_item` 状态在 P1 已落地

**待建设**：
- ~~建立持久化的 `seen_links` 集合（Redis SET 或 SQLite BloomFilter）~~
- ✅ **修订**：建立 SQLite 持久化 `seen_links` 表（无需 Redis）
- 抓取前先查，已存在 → 标记 `seen_item` 并跳过写入
- 已存在但内容变化 → 标记 `updated_item` 并更新字段

**技术选型**：
| 方案 | 适用规模 | 我们是否需要 |
|------|---------|------------|
| Python `set()` | < 10,000 | ❌ 内存丢失 |
| SQLite SET | < 100,000 | ✅ 推荐 |
| Redis SET | < 1,000,000 | ❌ 过度复杂 |
| Redis BloomFilter | > 10,000,000 | ❌ 规模不够 |

**约束**：
- 只做过滤，不删除历史
- `canonical_link` 为首选键，无 `link` 时用 `source_key + normalized_title`

**优先级**：高。直接减少无效网络开销，实现成本低。

---

### 需求 B：纵向事件聚合（时间序列快照）

**目标**：同一事件跨轮次的演变形成可追踪的时间序列，支撑趋势可视化与波动分析。

**现状**：
- `event_snapshots` 字段已存在（P1/P2 后），记录每轮快照（member_count、platform_count、score）
- 但快照仅作为预警判定依据，未对外展示

**待建设**：
- 事件详情页增加"历史轨迹"视图
  - 横轴：时间（最近 N 轮）
  - 纵轴：member_count / platform_count / composite_score
  - 数据来源：`event_snapshots` 数组
- 新增事件维度：
  - `member_delta`：本轮 vs 上轮的成员净增数
  - `platform_delta`：本轮新增平台列表
  - `first_seen_at`：首次出现时间（已有）
  - `last_growth_at`：最近一次增长时间

**约束**：
- 只读 `event_snapshots`，不新增写入字段
- 前端展示优先，后端逻辑暂不调整

**优先级**：高。数据基础已存在，展示层工作量不大。**产品价值被 Feedly 验证**。

---

### 需求 C：显式增量视图（趋势 delta 面板）

**目标**：让用户看到"这轮相比上轮发生了什么变化"，而非仅看原始数据。

**待建设**：
- 首页摘要增加增量指标：
  - `本轮新增素材`：new_item 数量
  - `本轮新增成员`：本轮 intel_events 中 member_delta > 0 的事件数
  - `本轮新平台扩散`：本轮新增 platform 的事件数
  - `本轮升温事件`：growing_event 数量
- 热点簇列表增加排序维度：
  - 按 member_delta 排序（最大增量优先）
  - 按 platform_delta 排序（新扩散优先）
- 预警台增加触发原因说明：
  - "X 来源新报道了此事件"（成员扩散）
  - "新平台 Y 加入"（平台扩散）
  - "速度超过阈值"（velocity 触发）

**优先级**：高。主要是前端展示逻辑，后端数据已部分具备。**符合"注意力管理"理念**。

---

### 需求 D：采集策略自适应（来源级刷新频率）

**目标**：根据来源的历史变更频率，动态调整刷新间隔。

**现状**：
- 每个来源有 `interval_minutes`，但为固定值
- 健康状态（avg_duration_ms、consecutive_failures）已记录

**待建设**：
- 为每个来源增加 `avg_change_interval_minutes` 字段
- 根据历史数据估算：若某来源平均 4 小时才更新一次新内容，刷新间隔可延长
- 配合缓存（P3）使用：到刷新时间但缓存未过期时，优先使用缓存

**⚠️ 前置条件**：
- 需要积累足够的来源历史数据（建议 > 100 轮采集记录）
- 当前来源数量（14个）偏少，统计数据置信度低

**优先级**：中。依赖来源历史数据积累，不适合早期实施。

---

### 需求 E：MinHash 高效去重（规模化优化）

**目标**：解决 Jaccard 聚类 O(n²) 性能问题，支持更大规模条目集合。

**现状**：
- `intel_pipeline.py` 用 Union-Find + Jaccard ≥ 0.45 聚类
- 对 500 条 item 做全量比较，约 125,000 次

**⚠️ 调研结论 - 当前规模不需要**：
- MinHash + LSH 是为"每秒数十条"级别设计的（Feedly: ~20/秒）
- 我们当前 259 条总数据，O(n²) = ~33,000 次比较，毫秒级完成
- 增加 datasketch 依赖 + 签名存储 + 分桶逻辑，实现成本高

**修订建议**：
- **立即可做**：只对最近 24 小时 item 做聚类比较（O(n²) → O(n)）
- **规模触发**：数据 > 10,000 条时再考虑 MinHash
- 签名可逐步生成，历史数据不需要重新计算

**约束**：
- 不改变现有聚类结果语义
- 优先确保 `canonical_link` 精确匹配，MinHash 只用于 title/summary 模糊匹配

**优先级**：低（当前）→ 中（规模触发后）。

---

## 数据模型变更

### DiscoveryItem 新增字段

```typescript
interface DiscoveryItem {
  // 现有字段保持不变
  id: string;
  canonical_link: string;
  dedupe_key: string;
  // ...

  // 新增：
  seen_at?: string | null;       // 首次在历史中被识别为 seen_item 的时间
  updated_from?: string | null;  // 从哪个已有 item 更新而来（item_id）
}
```

### IntelEvent 新增字段

```typescript
interface IntelEvent {
  // 现有字段保持不变
  id: string;
  member_count: number;
  platform_count: number;
  // ...

  // 新增：
  member_delta: number;           // 本轮 vs 上轮成员净增数
  member_added: string[];         // 本轮新增成员 item_id 列表
  platform_added: string[];      // 本轮新增平台列表
  last_growth_at?: string | null; // 最近一次增长时间
  snapshots: IntelEventSnapshot[]; // 历史快照（已有，增加 derived 字段）
}
```

---

## 不做的事项

以下事项经评估暂不纳入：

| 事项 | 原因 |
|------|------|
| GraphQL 迁移 | 当前 REST + JSON-File 模式已够用 |
| 全文向量嵌入（embedding）去重 | 对新闻类短文本效果有限，计算成本高 |
| 用户行为反馈（点击/收藏） | 非当前产品定位范围 |
| 跨语言新闻归一 | 当前来源以中文为主，优先级低 |
| 实时推送（WebSocket） | 轮询模式已满足当前需求 |
| Redis BloomFilter | 当前 259 条数据规模，SQLite SET 足够 |

---

## 实施优先级（修订版）

```
P0（立即可做，成本低，收益高）
└── 需求 A：全量历史去重（SQLite 实现）
    ├── 建立 seen_links 表
    ├── 采集前查询，已存在则跳过
    └── 更新 seen_item / updated_item 状态

P1（数据基础已存在，补充展示层）
├── 需求 B：纵向事件聚合（时间序列）
└── 需求 C：显式增量视图

P1.5（简单优化，无需额外依赖）
└── 需求 E 前置：只对最近 24h item 做聚类比较
    └── O(n²) → O(n)，无外部依赖

P2（依赖数据积累，渐进实施）
└── 需求 D：采集策略自适应

P3（性能优化，规模触发后）
└── 需求 E：MinHash 高效去重
    └── 数据 > 10,000 条时再考虑
```

---

## 参考资料

- [Feedly: Optimizing News Aggregation](https://feedly.com/engineering/posts/reducing-clustering-latency) — cluster propagation 技巧
- [Google Incremental Crawler](https://research.google.com/pubs/archive/34403.pdf) — 增量爬取基础论文
- [Google News Personalization](https://archives.iw3c2.org/www2007/papers/paper570.pdf) — MinHash + 协同过滤架构
- [CSE 291: Algorithms of Google News](https://eecs.ceas.uc.edu/~annexsfs/Courses/cs728-2008/files/Algorithms_ofgoogle_news.pdf) — MinHash 实现细节
- [MinHash + LSH for Document Deduplication](https://www.linkedin.com/posts/arpitbhayani_say-you-are-building-a-news-aggregator-like-activity-7431545884686942208-Rb5A) — 工程实践说明
- [Incremental Web Scraping Best Practices](https://stabler.tech/blog/how-to-perform-incremental-web-scraping) — 增量爬取代码示例
- [Redis Bloom Filters for Crawlers](https://oneuptime.com/blog/post/2026-03-31-redis-bloom-filter-url-deduplication/view) — BloomFilter 适用规模分析
- [datasketch library](https://datasketch.readthedocs.io/) — MinHash Python 实现
- [NEWS-COPY Dataset](https://github.com/dell-research-harvard/NEWS-COPY) — 噪声鲁棒新闻去重数据集
- [Finding near-duplicates with Jaccard and MinHash (Hacker News)](https://news.ycombinator.com/item?id=40872438) — 工程社区实践讨论
- [OpenClaw News Aggregator](https://www.tencentcloud.com/techpedia/140819) — "注意力管理系统"理念
- [Deduplication: Jaccard threshold guide](https://mbrenndoerfer.com/writing/deduplication-exact-near-duplicate-jaccard-similarity-suffix-arrays) — Jaccard 阈值选择

---

*文档创建：2026-04-28*
*基于业界调研与项目现状分析，不作为立即执行的开发承诺。*
*2026-04-28 更新：增加联网调研结论，修订技术选型和优先级*
