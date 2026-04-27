# Auto News Studio `intel-first-rebuild` Phase 1（定稿版）

## Summary

Phase 1 在现有 `auto-news-studio` 内把主线正式切成：

**人来控节奏的热点情报雷达**

核心目标只有一条：  
**先把“信息获取 -> 事件聚合 -> 速度预警 -> 首页可用”打透，再谈写稿。**

这版方案同时满足两类要求：

- **人怎么用**
  - 打开首页先看最重要情报
  - 在首页直接设“什么时候工作”
  - 需要时再去来源健康和任务页排障
- **系统怎么做到**
  - 来源注册
  - 去重
  - 跨平台聚合
  - 速度/覆盖/新鲜度评分
  - 预警状态机
  - Webhook 通知

固定产品路径：

1. 首页 `总览` 看预警和重点事件
2. `工作计划` 统一控制什么时候跑
3. `实时流` 看刚抓到什么
4. `热点簇` 看哪些是同一事件
5. `预警台` 看哪些正在起势
6. `来源健康` 看哪里坏了

---

## 使用逻辑

### 首次使用
用户首次进入系统只做 3 步：

1. 打开 `总览`
2. 在 `工作计划` 里设置：
   - 工作内容：`只采集 / 采集并生成事件 / 采集并生成事件与预警`
   - 启动方式：`立即一次 / 指定时间一次 / 立即循环 / 指定时间开始循环`
   - 频率：`10 / 15 / 20 / 30 / 60 分钟`
3. 点击 `开始工作`

不要求先去设置页，不要求先理解稿件，不要求先理解来源配置。

### 日常使用
你属于“**我来控节奏**”型用户，所以首页必须先服务这三件事：

- 现在最该看什么
- 系统现在有没有在工作
- 我要不要立刻补抓或改计划

首页固定四块：

1. **顶部主控条**
2. **爆发预警**
3. **当前最重要情报**
4. **系统摘要**

### 调度原则
Phase 1 只支持 **全局统一计划**：

- 首页改计划
- 来源页不改全局计划
- 任务页不负责调度配置
- 手动 `立即补抓一次` 不覆盖已保存计划

---

## Key Changes

### 1. 导航与页面职责

主导航重排为三组：

- **信息**
  - `总览`
  - `实时流`
  - `热点簇`
  - `预警台`
  - `来源健康`
- **稿件**
  - `重点观察`
  - `稿件`
- **系统与排障**
  - `任务`
  - `设置`
  - `日志`

固定职责：

- `总览`：先看预警和最重要情报
- `实时流`：回答“刚抓到了什么”
- `热点簇`：回答“哪些是同一件事”
- `预警台`：回答“哪些正在变热”
- `来源健康`：回答“哪里坏了”
- `重点观察`：人工标记“值得继续跟”的事件，不再叫候选池

---

### 2. 源系统与扩展机制

来源系统改成“注册表 + 自动发现”，不再继续在单文件里堆 collector。

结构固定为：

- `backend/app/sources/registry.py`
- `backend/app/sources/hotlists/*.py`
- `backend/app/sources/rss/*.py`
- `backend/app/sources/monitors/*.py`

每个来源模块必须暴露 `register()`，返回标准来源定义。

自动发现机制固定：

- `registry.py` 用 `pkgutil.iter_modules()` 扫描三个目录
- 自动导入有 `register()` 的模块
- 合并为统一来源注册表

来源定义固定字段：

- `key`
- `name`
- `platform`
- `kind` (`hotlist | rss | api | monitor`)
- `driver`
- `enabled`
- `interval_minutes`
- `priority`
- `weight`
- `tags`
- `url?`
- `auth?`

来源权重固定分层：

- 官方博客 / 官方发布页：`0.9`
- 权威科技媒体：`0.85`
- 技术社区 / GitHub / HN / Reddit：`0.8`
- 普通 RSS：`0.7`
- 社交热榜 / 聚合榜：`0.6`

---

### 3. 单主线数据模型

Phase 1 主数据模型固定为：

- `discovery_items`
  - 一条抓取素材对应一条发现项
- `intel_events`
  - 多条发现项聚类成一个事件
- `event_snapshots`
  - 每轮为每个事件记一次快照
- `intel_alerts`
  - 从快照推导出的预警对象

兼容策略固定：

- `raw_items` 保留为底层采集输入
- `normalized_items` 改成 `intel_events` 的兼容投影，不再是主事实
- `candidates` 从 `intel_events.watchlisted = true` 派生
- `drafts` 只允许从 `watchlisted` 事件生成

也就是：  
**只有一条主情报事实链，旧写稿链路只做派生，不再并行维护两套核心模型。**

---

### 4. 去重与跨平台聚合

Phase 1 固定三层去重：

#### 第一层：链接去重
对链接做 `canonical_link` 归一化：

- 去 fragment
- 去常见追踪参数
- 保留关键路径

相同 `canonical_link` 直接同素材。

#### 第二层：标题键去重
对标题做：

- 小写化
- 去标点
- 去空格
- 英文 token 化
- 中文 2-6 字短词切片

生成 `dedupe_key`。  
相同 `dedupe_key` 直接视为同事件候选。

#### 第三层：相似度聚类
先提取 `anchor tokens`：

- 英文产品名、版本号、模型名
- 中文核心名词
- 大写缩写
- 数字版本串

聚类规则固定：

- `Jaccard >= 0.45`：直接同事件
- `0.28 <= Jaccard < 0.45` 且满足以下全部条件时同事件：
  - 至少 1 个 anchor token 重合
  - 发布时间差不超过 24 小时
  - 主题类别一致或来源标签高度接近
- 否则不同事件

这样既保留现有 `0.32` 级别的中文/跨平台适应性，又避免误并过多。

代表项选择固定：

1. 发布时间最新
2. 若发布时间缺失，则 `engagement_score` 更高
3. 若仍接近，则来源权重更高
4. 最后按采集时间最新

跨平台覆盖计算规则固定：

- 同平台重复条目主要增加 `member_count`
- 不显著抬高 `coverage_score`
- 平台数增长才吃覆盖加成

---

### 5. 评分公式与速度检测

#### 总分公式
`CompositeScore = VelocityScore * 0.4 + CoverageScore * 0.35 + FreshnessScore * 0.25`

#### VelocityScore
窗口固定：

- `30 分钟`
- `2 小时`

定义：

- `delta_mentions_30m`
- `delta_mentions_2h`
- `speed_30m = delta_mentions_30m / 0.5h`
- `speed_2h = delta_mentions_2h / 2h`

边界规则：

- 若 `first_seen_at < 2h`
  - 不计算加速度
  - 只使用 `speed_30m + 新鲜加成`
- 若快照不足 2 个窗口
  - 只使用可得窗口，不阻断评分

加速度近似固定为：
`acceleration = speed_30m - speed_2h`

速度分：

- `speed_30m >= 100/h` -> `BaseVelocity = 80`
- `30/h <= speed_30m < 100/h` -> `60 ~ 79`
- `10/h <= speed_30m < 30/h` -> `40 ~ 59`
- `3/h <= speed_30m < 10/h` -> `20 ~ 39`
- `< 3/h` -> `0 ~ 19`

加速度加成：

- `acceleration >= 40` -> `+20`
- `20 <= acceleration < 40` -> `+12`
- `8 <= acceleration < 20` -> `+6`
- 否则 `+0`

新鲜出现加成：

- `first_seen_at <= 2h` -> `+10`

最终：
`VelocityScore = min(100, BaseVelocity + AccelerationBonus + FreshEntryBonus)`

#### CoverageScore
固定公式：

- `weighted_source_base = avg(source_weight) * 45`
- `platform_bonus`
  - 1 平台 `+0`
  - 2 平台 `+10`
  - 3 平台 `+18`
  - 4 平台 `+24`
  - 5+ 平台 `+30`
- `source_bonus = min(source_count * 3, 15)`

最终：
`CoverageScore = min(100, weighted_source_base + platform_bonus + source_bonus)`

#### FreshnessScore
固定为两段组成：

- `PublishedRecencyScore`，满分 `70`
- `LagScore`，满分 `30`

`PublishedRecencyScore`：

- `<= 1h` -> `70`
- `1h ~ 6h` -> `70 -> 50` 线性下降
- `6h ~ 24h` -> `50 -> 20` 线性下降
- `24h ~ 72h` -> `20 -> 0` 线性下降
- `> 72h` -> `0`

`LagScore` 根据 `collected_at - published_at`：

- `<= 10m` -> `30`
- `10m ~ 30m` -> `24`
- `30m ~ 120m` -> `14`
- `120m ~ 360m` -> `6`
- `> 360m` -> `0`

若 `published_at` 缺失：

- 用 `collected_at` 年龄估算
- `FreshnessScore` 上限固定为 `45`
- 不参与 `LagScore`

---

### 6. 预警状态机

事件状态固定为：

- `new`
- `watch`
- `rising`
- `breakout`
- `cooling`

进入条件：

- `watch`
  - `member_count >= 3`
  - 且 `first_seen_at <= 2h`

- `rising`
  - `VelocityScore >= 55`
  - 或 `platform_count` 最近 30 分钟从 `1 -> 2`
  - 或 `delta_mentions_30m >= 12`

- `breakout`
  - `VelocityScore >= 75`
  - 且 `platform_count >= 2`
  - 且若事件年龄 `>= 2h`，需满足 `acceleration >= 20`
  - 且最近两轮都在增长

- `cooling`
  - 连续两轮 `delta_mentions_30m <= 0`
  - 或 `last_seen_at > 6h`

首页总览只突出：
- `breakout`
- `rising`

`watch` 只在预警台里显示。

---

### 7. 快照保留与清理策略

`event_snapshots` 不无限保留。

Phase 1 固定清理规则：

- 仅保留最近 **48 小时** 快照
- 每轮同步结束后执行一次轻量清理
- 被 `cooling` 且 `last_seen_at > 48h` 的事件可进入归档，不再参与首页排序
- 清理只删快照，不删原始 `discovery_items`

这样可控制体量，同时保留短期趋势判断能力。

---

### 8. LLM 辅助层与降级链

LLM 不参与首页主排序，但固定承担 3 个任务：

- `event_title_refine`
- `substance_check`
- `alert_reasoning`

Phase 1 默认链路固定为：

1. `NVIDIA / qwen/qwen3.5-122b-a10b`
2. `NVIDIA / z-ai/glm4.7`
3. `SiliconFlow / THUDM/GLM-4-9B-0414`
4. `SiliconFlow / THUDM/GLM-Z1-9B-0414`
5. 规则拼接降级

切换条件固定：

- `429`：立即切到下一个 provider
- `timeout`
  - `title / alert_reasoning`: `8 秒`
  - `substance_check`: `12 秒`
- JSON 解析失败：
  - 同 provider 重试 1 次，强制 `return JSON only`
  - 再失败则切下一个 provider
- 最多尝试 2 个 provider；都失败则规则降级

LLM 输出失败不得阻断：
- 抓取
- 去重
- 聚类
- 评分
- 预警生成

---

### 9. 首页工作计划与手动操作

首页折叠面板统一叫：

**工作计划**

分三段：

- `工作内容`
  - 只采集
  - 采集并生成事件
  - 采集并生成事件与预警
- `工作时间`
  - 立即一次
  - 指定时间一次
  - 立即循环
  - 指定时间开始循环
  - 频率
- `当前执行情况`
  - 当前状态
  - 当前阶段
  - 已运行时长
  - 上轮开始
  - 上轮耗时
  - 下一轮时间

首页固定动作：

- `开始工作`
- `停止工作`
- `立即补抓一次`
- `刷新状态`

规则固定：

- `立即补抓一次` 只补跑，不覆盖计划
- 计划只在首页改
- 任务页只保留补跑与排障
- 来源页不再承载全局调度概念

---

### 10. 通知系统

Phase 1 只做最小可用通知：

- `Webhook`

触发对象：

- `breakout`：立即推送
- `hourly_digest`：可选

配置项：

- `enabled`
- `url`
- `secret?`
- `events`

通知内容固定：

- 事件标题
- 预警等级
- 触发原因
- `VelocityScore / CoverageScore / FreshnessScore`
- 平台数 / 来源数
- 代表链接
- 触发时间

去重规则固定：

- 同一事件、同一等级，60 分钟内不重复推送
- 若等级升级，例如 `rising -> breakout`，可立即再次推送

---

## Test Plan

### 1. 使用流程
- 用户首次进入只需在首页设置计划并启动
- 不进入设置页也能理解主流程
- 首页第一屏先看到情报，而不是后台状态块

### 2. 去重与聚类
- 相同链接不重复
- 跨平台同事件可正确合并
- 中英文标题差异较大但 anchor 重合的事件仍能合并
- 不同事件不会被大面积误并

### 3. 速度与预警
- 新事件 `<2h` 只用 `speed_30m`，不会因缺少 `2h` 历史报错
- `rising` 和 `breakout` 的触发条件可稳定复现
- 老热点会进入 `cooling`
- 首页不会长期被旧热点占满

### 4. 快照与清理
- 每轮同步会写快照
- 48 小时外快照会被清理
- 清理后仍能正确计算近 2 小时速度

### 5. LLM 辅助层
- 标题优化、实质度判断、预警原因都可单独失败而不影响主链路
- `429`、超时、JSON 失败都会按链路切换
- 最终总能落到规则降级结果

### 6. 通知
- `breakout` 可触发 Webhook
- 同一事件不会短时间狂推
- 通知失败只写日志，不阻断主流程

### 7. 兼容
- `重点观察 -> 稿件` 仍可用
- 旧稿件页不崩
- 旧 `normalized_items / candidates` 只做派生投影，不再形成第二套核心事实

---

## Assumptions

- Phase 1 只打透情报链，不重做写稿和微信发布链
- Phase 1 使用规则聚类，不上向量库
- Phase 1 只有 Webhook 通知，其他渠道后续再接
- LLM 只做辅助，不控制首页热度排序
- `event_snapshots` 保留 48 小时，满足短周期趋势检测即可
