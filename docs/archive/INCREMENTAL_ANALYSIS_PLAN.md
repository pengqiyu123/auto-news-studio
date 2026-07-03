# 增量分析能力升级计划

> 四角色团队（探索者、数据科学家、架构师、产品经理）并行分析后综合产出。
> 目标：从"简单汇总"进阶到"规律总结、关联挖掘、趋势判断、问题研判"。

---

## 团队结论汇总

| 角色 | 核心发现 |
|------|---------|
| **探索者** | 聚类 O(n²) Union-Find + Jaccard（24h窗口），评分四维加权，实体关键词+spaCy NER。48h 快照窗口是最大瓶颈——无法做长周期趋势分析 |
| **数据科学家** | 3 阶段路线：Phase 1（jieba+NMF+快照扩展+趋势信号），Phase 2（NetworkX共现图+周期检测+LLM研判），Phase 3（语义增强+预测+闭环）。新增依赖仅 scikit-learn + networkx + jieba |
| **架构师** | 当前数据天花板 ~2000 条。JSON state.json 全量读写和 _replace_rows 是瓶颈。需 GIN 索引 + 增量 upsert。pgvector 是未来向量搜索路径，不需要独立向量库 |
| **产品经理** | 4 个 MVP：事件关联图(B) + 主题趋势追踪(C) + 周度摘要(A) + 事件研判(D)。推荐顺序 B+C → A → D。MVP 不新增 Tab，嵌入现有页面 |

---

## 团队共识

1. **快照窗口扩展是前置条件** — 48h → 30天，所有时序分析的基础
2. **Phase 1 先做事件关联 + 趋势追踪** — 技术风险最低，纯规则实现，用户价值最高
3. **新增依赖克制** — scikit-learn + networkx + jieba，零编译依赖
4. **pgvector 足够** — 不引入独立向量数据库，单用户本地应用不需要
5. **MVP 不新增 Tab** — 分析结果嵌入现有事件详情页和监控名单区域

---

## Phase 1：基础能力建设

### 预估工期：2-3 周 | 4 个交付物

---

### 交付物 1：快照窗口扩展（前置条件）

**问题**：当前 `event_snapshots` 保留 48h，无法做长周期趋势分析。

**改动**：

| 文件 | 操作 | 内容 |
|------|------|------|
| `backend/app/intel/pipeline.py` ~L974-978 | 修改 | 48h 硬编码改为 `SNAPSHOT_RETENTION_HOURS` 环境变量（默认 720=30天） |
| `auto-news-studio/.env.example` | 修改 | 新增 `SNAPSHOT_RETENTION_HOURS=720` |

**约束**：
- 不改 `event_snapshots` 表结构
- 保留窗口由数据清理逻辑控制，不是物理删除
- 48h 以内的快照保持不变（评分管道依赖）

---

### 交付物 2：中文分词增强

**问题**：当前 `tokenize_title()` 用正则 `[a-z0-9]{2,}` + `[一-鿿]{2,6}` 做字符 n-gram，粒度粗。

**改动**：

| 文件 | 操作 | 内容 |
|------|------|------|
| `backend/app/intel/tokenizer.py` | 新建 | jieba 分词 + 停用词过滤 + 中英文统一接口 |
| `backend/app/intel/topics.py` | 新建 | TF-IDF + NMF 主题建模，消费 jieba tokens |
| `pyproject.toml` | 修改 | 新增 `jieba`, `scikit-learn`, `networkx` 依赖 |

**设计**：
- `tokenizer.py` 提供 `tokenize_for_analysis(title: str) -> list[str]`，内部用 jieba
- 原有 `tokenize_title()` 不改（聚类管道继续用）
- jieba tokens 仅供下游主题建模和关联分析使用
- 停用词表：中英文通用 + 新闻领域

**约束**：
- 不改变现有聚类管道的 tokenization
- jieba 初始化放在模块级（懒加载），不影响启动速度

---

### 交付物 3：主题建模 + 事件关联图（MVP-B）

**问题**：事件之间没有关联关系，用户看不到事件全貌。

**改动**：

| 文件 | 操作 | 内容 |
|------|------|------|
| `backend/app/intel/topics.py` | 新建 | TF-IDF + NMF（K=30 主题），每日批处理 |
| `backend/app/intel/correlation.py` | 新建 | 事件关联计算：实体共享 + anchor_tokens 重叠 + 时间窗口 + 主题共享 |
| `backend/app/db/models.py` | 修改 | 新增 ORM 模型：`TopicModel`, `EventTopic`, `EventRelation` |
| `backend/app/models/` | 新建 | Pydantic 模型：`TopicInfo`, `EventRelationInfo` |
| `alembic/versions/` | 新建 | 迁移：创建 `topic_models`, `event_topics`, `event_relations` 表 |
| `backend/app/routes/analysis.py` | 新建 | API：`GET /api/admin/topics`, `GET /api/admin/events/{id}/related` |
| `backend/app/main.py` | 修改 | 注册新路由 |

**关联算法设计**（多维融合）：
1. **实体共享**：两个事件共享 >= 2 个 entity_id → weight += 0.35
2. **主题共享**：两个事件属于同一 NMF 主题 → weight += 0.25
3. **时间接近**：first_seen_at 间隔 <= 72h → weight += 0.20
4. **anchor_tokens 重叠**：Jaccard >= 0.3 → weight += 0.20
5. 关联类型标签：`entity_shared` / `topic_shared` / `temporal_proximity` / `anchor_overlap`
6. 总 weight >= 0.4 才建立关联

**API 设计**：
```
GET /api/admin/topics
  → { "items": [{ topic_id, label, keywords, event_count }] }

GET /api/admin/events/{id}/related
  → { "items": [{ event_id, title, relation_type, weight, evidence }] }
```

**批处理**：
- 主题建模：每日一次（APScheduler 注册）
- 关联计算：每日一次（主题建模完成后）

**约束**：
- 不改现有 API 端点签名
- 新增的表独立于现有表
- 前端暂不改（API 先就位，前端后续迭代）

---

### 交付物 4：趋势信号检测（MVP-C）

**问题**：无法判断主题/实体是升温还是降温。

**改动**：

| 文件 | 操作 | 内容 |
|------|------|------|
| `backend/app/intel/trends.py` | 新建 | CUSUM 变化点 + SMA-5 趋势方向 |
| `backend/app/db/models.py` | 修改 | 新增 ORM 模型：`TrendSignal` |
| `backend/app/models/` | 新建 | Pydantic 模型：`TrendSignalInfo` |
| `alembic/versions/` | 新建 | 迁移：创建 `trend_signals` 表 + `daily_event_metrics` 表 |
| `backend/app/routes/analysis.py` | 修改 | 新增 API：`GET /api/admin/trends` |

**趋势算法**（纯统计，无 LLM）：
1. 按实体+天聚合事件数、平均评分、最大速度
2. 对每个实体计算 7 天 SMA，判断趋势方向：
   - `hot`: 7d SMA > 14d SMA 且加速度 > 0
   - `warm`: 趋势平稳（加速度 ≈ 0）
   - `cool`: 7d SMA < 14d SMA
   - `cold`: 7d 内无事件
   - `emerging`: 近 3d 事件数 > 前 7d 的 2 倍
3. CUSUM 检测突变点

**API 设计**：
```
GET /api/admin/trends
  → { "items": [{ entity_id, entity_name, trend, sma_7d, sma_14d, signals: [...] }] }
```

**日终聚合任务**：
- APScheduler 注册每日凌晨任务
- 预计算 `daily_event_metrics` 表（避免实时全表扫描）

**约束**：
- 数据不足（< 14 天）时标记 `insufficient_data`
- 纯规则计算，不依赖 LLM
- 趋势标签使用描述性语言（"近7天持续上升"），不用预测性语言（"即将爆发"）

---

## Phase 2：深度分析（Phase 1 完成后）

| 交付物 | 周期 | 依赖 |
|--------|------|------|
| 周度情报摘要（MVP-A） | 5 天 | 趋势数据 + 主题数据 |
| LLM 事件研判（MVP-D） | 7 天 | 关联图 + 趋势信号 + LLM 可用 |
| 周期性检测（ACF/FFT） | 3 天 | 主题时间序列 |
| 时序关联规则 | 3 天 | 事件关系表 |

---

## Phase 3：智能化（Phase 2 完成后）

| 交付物 | 周期 | 依赖 |
|--------|------|------|
| 语义相似度增强（sentence-transformers） | 7 天 | Phase 1 的 jieba tokenizer |
| 热度预测（Holt-Winters/Prophet） | 5 天 | 3+ 个月数据积累 |
| 人工反馈闭环 | 5 天 | Phase 2 研判报告 |
| 自动周报/月报 | 5 天 | Phase 2 所有能力 |

---

## 数据库迁移（Phase 1）

### 新增表

```sql
-- 主题建模
CREATE TABLE topic_models (
    topic_id       VARCHAR(64) PRIMARY KEY,
    keywords_json  JSONB NOT NULL DEFAULT '[]',
    label          VARCHAR(255) NOT NULL DEFAULT '',
    event_count    INTEGER NOT NULL DEFAULT 0,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE event_topics (
    event_id       VARCHAR(64) NOT NULL,
    topic_id       VARCHAR(64) NOT NULL REFERENCES topic_models(topic_id),
    weight         NUMERIC(6,4) NOT NULL DEFAULT 0,
    PRIMARY KEY (event_id, topic_id)
);
CREATE INDEX ix_event_topics_topic_id ON event_topics(topic_id);

-- 事件关联
CREATE TABLE event_relations (
    id                 VARCHAR(64) PRIMARY KEY,
    source_event_id    VARCHAR(64) NOT NULL,
    target_event_id    VARCHAR(64) NOT NULL,
    relation_type      VARCHAR(32) NOT NULL,
    weight             NUMERIC(6,4) NOT NULL DEFAULT 0,
    evidence_json      JSONB NOT NULL DEFAULT '{}',
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX ix_event_relations_source ON event_relations(source_event_id);
CREATE INDEX ix_event_relations_target ON event_relations(target_event_id);

-- 趋势信号
CREATE TABLE trend_signals (
    id             VARCHAR(64) PRIMARY KEY,
    entity_id      VARCHAR(64) NOT NULL,
    signal_type    VARCHAR(32) NOT NULL,
    signal_value   NUMERIC(10,4) NOT NULL DEFAULT 0,
    confidence     NUMERIC(6,4) NOT NULL DEFAULT 0,
    detected_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX ix_trend_signals_entity ON trend_signals(entity_id);

-- 日度聚合
CREATE TABLE daily_event_metrics (
    metric_date        DATE NOT NULL,
    entity_id          VARCHAR(64) NOT NULL DEFAULT '',
    event_count        INTEGER NOT NULL DEFAULT 0,
    avg_composite_score NUMERIC(10,4) NOT NULL DEFAULT 0,
    max_velocity_score  NUMERIC(10,4) NOT NULL DEFAULT 0,
    breakout_count     INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (metric_date, entity_id)
);
CREATE INDEX ix_daily_metrics_date ON daily_event_metrics(metric_date DESC);
```

### 新增索引（现有表）

```sql
CREATE INDEX CONCURRENTLY ix_events_entity_ids_gin
    ON intel_events_current USING GIN (entity_ids_json jsonb_path_ops);
```

---

## Codex 实施约束（Phase 1）

### 可以修改/新增

| 范围 | 说明 |
|------|------|
| `backend/app/intel/tokenizer.py` | 新建 |
| `backend/app/intel/topics.py` | 新建 |
| `backend/app/intel/correlation.py` | 新建 |
| `backend/app/intel/trends.py` | 新建 |
| `backend/app/db/models.py` | 仅新增 ORM 类 |
| `backend/app/models/` | 新增 Pydantic 模型 |
| `backend/app/routes/analysis.py` | 新建路由 |
| `backend/app/main.py` | 注册新路由 |
| `alembic/versions/` | 新增迁移 |
| `pyproject.toml` | 新增 3 个依赖 |

### 不可修改

- 现有 API 端点签名（任何 `/api/admin/` 下的现有路由）
- `pipeline.py` 的 `build_intel_state()` 输入输出签名
- `StoreCore._read()` / `_write()` 原子写入协议
- 现有 Pydantic 模型（IntelEvent, IntelAlert, DiscoveryItem 等）的字段
- `state.json` 的结构
- `ingest_projection.py` 的投影逻辑

### 仅可添加可选内容

- `pipeline.py` 的快照保留参数（默认值保持 48h 不变，环境变量覆盖）
- 现有模型类新增字段（仅可选，带默认值）

---

## 验收标准（Phase 1）

1. `cd auto-news-studio && pytest` 通过
2. `cd auto-news-studio/frontend && npm run build` 通过
3. `GET /api/admin/topics` 返回主题列表
4. `GET /api/admin/events/{id}/related` 返回关联事件
5. `GET /api/admin/trends` 返回实体趋势数据
6. 快照保留窗口可通过环境变量配置
7. jieba 分词不影响现有聚类管道
8. 所有新依赖（jieba, scikit-learn, networkx）在 pyproject.toml 中声明
