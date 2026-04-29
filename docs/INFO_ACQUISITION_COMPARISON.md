# 信息获取功能对比分析

更新时间：2026-04-28

## 概述

对比 Auto News Studio 与高星参考项目（TrendRadar、newsnow、wiseflow）的信息获取能力，找出可借鉴点。

---

## 当前项目现状

### 信息来源（connectors.py）

| 来源类型 | 实现方式 | 数据量 |
|---------|---------|--------|
| RSS | feedparser | 约 10 个配置源 |
| Reddit | r/{subreddit}/hot.json | 1 个子版块 |
| HackerNews | Algolia API | 1 个来源 |
| GitHub Trending | HTML 解析 + API | 1 个来源 |
| VVhan 热榜 | api.vvhan.com | 1 个来源 |

**总计：约 14 个来源，当前 state.json 仅 259 条数据**

### 聚类与评分

- **聚类**：Union-Find + Jaccard ≥ 0.45
- **评分**：Velocity × 0.4 + Coverage × 0.35 + Freshness × 0.25
- **去重**：本轮内去重，无跨轮历史基准

### 过滤机制

- 无关键词订阅功能
- 无 AI 智能筛选
- 无增量/每日/当前模式区分

---

## 高星项目对比

### TrendRadar (⭐1.4k+, v6.6.1)

**信息来源（11+ 平台）：**
- 知乎、抖音、微博、百度热搜、华尔街见闻
- 贴吧、财联社、澎湃新闻、凤凰网、今日头条、bilibili
- RSS 订阅源（可自定义添加）

**热点算法：**
```
综合热度 = 排名权重 × 0.6 + 频次权重 × 0.3 + 热度权重 × 0.1
```

**三种推送模式：**
| 模式 | 说明 | 适用场景 |
|------|------|---------|
| daily | 当日汇总 | 企业管理者/普通用户 |
| current | 当前榜单 | 自媒体人/内容创作者 |
| incremental | 增量监控 | 投资者/交易员 |

**关键词过滤：**
- 普通词、必须词（+）、过滤词（!）
- 正则表达式支持
- 全局过滤（[GLOBAL_FILTER]）

**AI 智能筛选：**
- 自然语言描述兴趣 → AI 自动分类
- 两阶段处理：兴趣提取 → 新闻打分

**多渠道推送：**
- 企业微信、飞书、钉钉、Telegram
- 邮件、ntfy、Bark、Slack、Webhook

**自适应抓取：**
- 根据来源更新频率调整抓取间隔
- 最低 2 分钟，最高 30 分钟

---

### newsnow (⭐2.8k+)

**信息来源（40+ 平台）：**
- 微博、知乎、百度、抖音、bilibili
- 36kr、少数派、SSPai、异次域
- HackerNews、ProductHunt、GitHub
- 等等...

**技术特点：**
- 30 分钟缓存策略
- 自适应抓取间隔（根据来源更新频率）
- GitHub OAuth 登录 + 数据同步
- 支持 MCP Server

**抓取策略：**
```javascript
// 自适应间隔示例
const interval = source.updateFrequency > 60 ? 2 : 30  // 分钟
```

---

### wiseflow (⭐800+)

**Crew 概念：**
- 多智能体编排
- 自媒体运营 Crew：自动发帖、回帖
- 销售型客服 Crew：促进成交

**反检测浏览器：**
- Patchright（Playwright 的反检测 fork）
- 无需安装浏览器插件

**智能搜索：**
- 无需 API Key
- 驱动浏览器前往目标页面搜索
- 支持自定义信源

---

## 差距分析

### 信息来源层面

| 维度 | 我们 | TrendRadar | newsnow | 差距 |
|------|------|-----------|---------|------|
| 平台数量 | ~14 | 11+ | 40+ | **-27~26** |
| 中文热点 | 0 | 11 | 多数 | **-11** |
| RSS 支持 | 有 | 有 | 有 | 持平 |
| 自适应间隔 | 无 | 有 | 有 | **-2** |

### 过滤机制层面

| 维度 | 我们 | TrendRadar | 差距 |
|------|------|-----------|------|
| 关键词订阅 | 无 | 有（正则+必须+过滤） | **-1** |
| AI 智能筛选 | 无 | 有 | **-1** |
| 推送模式 | 无 | 3种 | **-3** |
| 热点算法 | 自研 | rank×0.6+... | 可借鉴 |

### 技术实现层面

| 维度 | 我们 | newsnow/wiseflow | 差距 |
|------|------|-----------------|------|
| 缓存策略 | 无 | 30分钟 | **-1** |
| 自适应抓取 | 固定 | 动态调整 | **-1** |
| MCP 支持 | 无 | 有（newsnow） | **-1** |
| 反检测 | Playwright | Patchright | 可升级 |

---

## 现成可用接口资源

### Python 库（直接 pip 安装，开箱即用）

| 项目 | Stars | 覆盖平台 | 链接 |
|------|-------|---------|------|
| **hot-search-scraper** | - | 知乎、微博、抖音、百度 | [GitHub](https://github.com/chang-zy/hot-search-scraper) |
| **hot_searches_for_apps** | ⭐19k | **32个平台** | [GitHub](https://github.com/iiecho1/hot_searches_for_apps) |
| **weibo-trending-hot-search** | - | 微博热搜 | [GitHub](https://github.com/v5tech/weibo-trending-hot-search) |
| **bilibili-api** | - | 哔哩哔哩全接口 | [GitHub](https://github.com/Syugen/bilibili-api) |

#### hot-search-scraper（推荐，最简单）

```bash
pip install hot-search-scraper
```

```python
from hot_search_scraper import WeiboHotSearch, ZhihuHotSearch, BaiduHotSearch, DouyinHotSearch

# 获取微博热搜
scraper = WeiboHotSearch()
results = scraper.get_hot_list()
# [
#   {'rank': 1, 'title': 'xxx', 'hot_value': 1234567},
#   {'rank': 2, 'title': 'yyy', 'hot_value': 987654},
#   ...
# ]
```

#### hot_searches_for_apps（最全，32平台）

**支持的 32 个平台：**

| 分类 | 平台 |
|------|------|
| 搜索/门户 | 百度、搜狗、360搜索、搜狐、夸克 |
| 社交/社区 | **微博**、**知乎**、V2EX、虎扑、豆瓣、AcFun、贴吧 |
| 新闻资讯 | 今日头条、澎湃新闻、新京报、网易新闻、腾讯新闻、人民网、南方周末、CCTV |
| 科技 | CSDN、GitHub、IT之家、36氪 |
| 视频/娱乐 | **哔哩哔哩**、**抖音**、梨视频 |
| 其他 | 少数派、懂球帝、国家地理等 |

**在线查看：** [hotsearch-web.vercel.app](https://hotsearch-web.vercel.app)

---

### 在线 API 服务

| 服务 | 说明 | 链接 |
|------|------|------|
| **TikHub API** | 付费 API，抖音/小红书/微博/知乎/B站 | [api.tikhub.io](https://api.tikhub.io/) |
| **hot-search API** | 32平台热搜聚合 | [hotsearch-web.vercel.app](https://hotsearch-web.vercel.app) |

#### TikHub API（商业级）

| 平台 | 接口路径 | 说明 |
|------|---------|------|
| 抖音 | `/api/v1/douyin/web/fetch_hot_search` | 网页版热搜 |
| 微博 | `/api/v1/weibo/web/fetch_hot_search` | 网页版热搜 |
| 知乎 | `/api/v1/zhihu/web/fetch_hot_search` | 网页版热搜 |
| 哔哩哔哩 | `/api/v1/bilibili/web/fetch_hot_search` | 网页版热搜 |
| 小红书 | `/api/v1/xiaohongshu/web/fetch_hot_search` | 网页版热搜 |

**定价：** 有免费额度，高级功能付费

---

### MCP 服务（AI Agent 集成）

| 项目 | 说明 | 链接 |
|------|------|------|
| **hot-search MCP** | 微博、知乎、澎湃新闻热搜 | [GitHub](https://github.com/aiyogg/hot-search) |
| **Bilibili MCP** | 哔哩哔哩 MCP Server | [MCP Market](https://mcpmarket.com/server/bilibili) |

---

### 对接我们项目示例

```python
# connectors.py 新增 hotlist connector
from hot_search_scraper import WeiboHotSearch, ZhihuHotSearch, BaiduHotSearch

async def _collect_weibo_hotlist():
    """微博热搜"""
    scraper = WeiboHotSearch()
    items = scraper.get_hot_list()
    return [DiscoveryItem(
        id=f"weibo-hot-{r['rank']}",
        source_key="weibo_hotlist",
        source_name="微博热搜",
        source_kind="hotlist",
        title=r['title'],
        link=f"https://s.weibo.com/weibo?q={quote(r['title'])}",
        published_at=datetime.utcnow().isoformat(),
        metadata={
            "platform": "weibo",
            "rank": r['rank'],
            "hot_value": r.get('hot_value')
        }
    ) for r in items]

async def _collect_zhihu_hotlist():
    """知乎热榜"""
    scraper = ZhihuHotSearch()
    items = scraper.get_hot_list()
    return [DiscoveryItem(
        id=f"zhihu-hot-{r['rank']}",
        source_key="zhihu_hotlist",
        source_name="知乎热榜",
        source_kind="hotlist",
        title=r['title'],
        link=f"https://www.zhihu.com/question/{r.get('target_id')}",
        published_at=datetime.utcnow().isoformat(),
        metadata={
            "platform": "zhihu",
            "rank": r['rank'],
            "hot_value": r.get('hot_value')
        }
    ) for r in items]
```

---

### 风险提示

| 风险 | 说明 | 应对 |
|------|------|------|
| 接口不稳定 | 非官方 API，可能随时失效 | 多个源冗余 |
| 反爬限制 | 可能需要 Cookie/UA | 加代理池 |
| 数据延迟 | 热榜有几分钟延迟 | 接受即可 |

---

## 可借鉴功能（按优先级）

### P0：立即可做（高价值，低成本）

#### 1. 增加中文热点源（使用现成库）

**最快实现方式（使用 hot-search-scraper）：**

```python
# connectors.py 新增
from hot_search_scraper import (
    WeiboHotSearch,
    ZhihuHotSearch,
    BaiduHotSearch,
    DouyinHotSearch
)

# 新增 4 个热榜源，一行代码搞定
hotlist_sources = [
    {"key": "weibo_hotlist", "name": "微博热搜", "collector": WeiboHotSearch},
    {"key": "zhihu_hotlist", "name": "知乎热榜", "collector": ZhihuHotSearch},
    {"key": "baidu_hotlist", "name": "百度热搜", "collector": BaiduHotSearch},
    {"key": "douyin_hotlist", "name": "抖音热榜", "collector": DouyinHotSearch},
]
```

**数据格式（统一到 DiscoveryItem）：**
```python
{
    "id": "weibo-hot-xxx",
    "source_key": "weibo_hot",
    "source_name": "微博热搜",
    "source_kind": "hotlist",
    "title": "热搜标题",
    "link": "https://m.weibo.cn/search?containerid=...",
    "published_at": "2026-04-28T10:00:00Z",
    "metadata": {
        "platform": "weibo",
        "rank": 1,
        "hot_value": 1234567  # 热度值
    }
}
```

#### 2. 增量视图展示

**已有基础（P1 已实现 seen_item/updated_item）：**
- `item_state: new_item | seen_item | updated_item`
- `change_state: new_item | updated_item | seen_item`

**可增加前端展示：**
- 实时流页面增加 filter：只看新增 / 更新 / 全部
- 首页摘要增加增量指标：
  - `本轮新增 N 条`
  - `本轮更新 M 条`
  - `历史累计 K 条`

---

### P1：短期可做（中等价值，需要规划）

#### 3. 关键词订阅功能

**参考 TrendRadar 的语法：**
```python
# frequency_words.txt 格式
[AI]
人工智能
AI
ChatGPT
+技术  # 必须词

[过滤]
!广告
!推广

[/AI]
特斯拉
马斯克
```

**实现思路：**
```python
def match_keywords(title: str, keywords: list[dict]) -> bool:
    """匹配关键词配置"""
    for group in split_by_empty_line(keywords):
        must_keywords = [k for k in group if k.startswith('+')]
        exclude_keywords = [k for k in group if k.startswith('!')]
        normal_keywords = [k for k in group if not k.startswith(('+', '!'))]

        has_normal = any(k in title for k in normal_keywords)
        has_all_must = all(k[1:] in title for k in must_keywords)
        has_exclude = any(k[1:] in title for k in exclude_keywords)

        if has_normal and has_all_must and not has_exclude:
            return True
    return False
```

#### 4. 热点排序算法优化

**参考 TrendRadar：**
```python
def calculate_hot_score(
    rank: int,       # 排名，1 为最热
    frequency: int,  # 出现频次
    hot_value: int   # 平台热度值
) -> float:
    """
    综合热度 = 排名权重 × 0.6 + 频次权重 × 0.3 + 热度权重 × 0.1
    """
    # 排名归一化（排名越小越好，1 为满分）
    rank_score = 1.0 / (rank ** 0.5) if rank > 0 else 0

    # 频次归一化（取对数平滑）
    freq_score = min(math.log(frequency + 1, 10) / 3, 1.0)

    # 热度归一化
    hot_score = min(math.log(hot_value + 1, 10) / 7, 1.0)

    return rank_score * 0.6 + freq_score * 0.3 + hot_score * 0.1
```

#### 5. 自适应抓取间隔

**参考 newsnow：**
```python
class SourceConfig:
    """来源配置增加动态间隔字段"""
    base_interval_minutes: int = 30  # 基础间隔
    update_frequency: int = 60  # 来源更新频率（分钟）

    @property
    def effective_interval(self) -> int:
        """根据更新频率动态调整"""
        if self.update_frequency <= 15:
            return 5   # 高频源：5分钟
        elif self.update_frequency <= 30:
            return 15  # 中频源：15分钟
        elif self.update_frequency <= 60:
            return 30  # 低频源：30分钟
        else:
            return 60  # 极低频：60分钟
```

---

### P2：中期可做（高价值，需要设计）

#### 6. AI 智能筛选

**参考 TrendRadar v6.5.0：**
```python
async def ai_filter_news(
    items: list[DiscoveryItem],
    interests: str  # "我想看 AI 和新能源相关新闻"
) -> list[tuple[DiscoveryItem, float]]:
    """自然语言兴趣 → 新闻打分"""

    # 阶段1：提取兴趣标签
    tags = await llm.extract_tags(interests)
    # 阶段2：对每条新闻打分
    scored = []
    for item in items:
        score = await llm.score_relevance(item.title, tags)
        scored.append((item, score))

    return [(i, s) for i, s in scored if s >= threshold]
```

#### 7. 三种工作模式

**参考 TrendRadar：**
```python
class WorkMode(Enum):
    """工作模式"""
    DAILY = "daily"        # 当日汇总
    CURRENT = "current"      # 当前榜单
    INCREMENTAL = "incremental"  # 增量监控

# DAILY: 展示所有匹配项，包括之前已推送的
# CURRENT: 只展示当前在榜的（按排名排序）
# INCREMENTAL: 只展示新增的（seen_item=False）
```

---

### P3：长期可做（高价值，成本高）

#### 8. 多渠道推送

**参考 TrendRadar：**
- 企业微信机器人
- 飞书机器人
- 钉钉机器人
- Telegram Bot
- 邮件 SMTP

**实现复杂度：** 中
**产品价值：** 高（适合不想开浏览器的用户）

#### 9. MCP Server

**参考 newsnow：**
```python
# 提供标准化 MCP 接口
class TrendRadarMCP:
    @tool
    def search_news(self, query: str, include_url: bool) -> list[dict]:
        ...

    @tool
    def get_trending_topics(self, date: str) -> list[dict]:
        ...

    @tool
    def analyze_topic_trend(self, topic: str, days: int) -> dict:
        ...
```

#### 10. 反检测浏览器

**参考 wiseflow：**
- Playwright → Patchright
- 无需额外安装插件
- 适合更激进的自动化场景

---

## 实施建议

### 近期（1-2个月）

```
1. 增加中文热点源（P0）
   ├── 微博热搜
   ├── 知乎热榜
   ├── 百度热搜
   └── 抖音/bilibili 热榜

2. 增量视图优化（P0）
   ├── 实时流 filter
   └── 首页增量指标

3. 关键词订阅（P1）
   └── 基础语法支持
```

### 中期（3-6个月）

```
4. 热点算法优化（P1）
   └── rank × 0.6 + freq × 0.3 + hot × 0.1

5. 自适应抓取间隔（P1）
   └── 根据来源更新频率动态调整

6. 三种工作模式（P2）
   └── daily / current / incremental
```

### 远期（6个月+）

```
7. AI 智能筛选（P2）
8. 多渠道推送（P3）
9. MCP Server（P3）
```

---

## 技术债务清理

### connectors.py 当前问题

1. **并发方式**：使用 ThreadPoolExecutor，可以考虑 asyncio
2. **错误处理**：部分异常被静默忽略
3. **Cookie/UA**：硬编码在代码中，应抽取到配置

### 建议的重构

```python
# 重构后的 connectors.py 结构
connectors/
├── __init__.py          # 统一导出
├── base.py              # 基类和工具函数
├── rss.py              # RSS 采集
├── hotlist/
│   ├── __init__.py
│   ├── weibo.py         # 微博热搜
│   ├── zhihu.py         # 知乎热榜
│   ├── baidu.py         # 百度热搜
│   └── ...
├── social/
│   ├── reddit.py
│   ├── hackernews.py
│   └── ...
└── github.py            # GitHub Trending
```

---

## 参考项目链接

### 高星参考项目
- [TrendRadar](https://github.com/sansan0/TrendRadar) - ⭐1.4k+
- [newsnow](https://github.com/ourongxing/newsnow) - ⭐2.8k+
- [wiseflow](https://github.com/TeamWiseFlow/wiseflow) - ⭐800+

### 现成接口资源
- [hot-search-scraper](https://github.com/chang-zy/hot-search-scraper) - Python 热搜库（微博/知乎/抖音/百度）
- [hot_searches_for_apps](https://github.com/iiecho1/hot_searches_for_apps) - ⭐19k，32平台热搜
- [hotsearch-web](https://hotsearch-web.vercel.app) - 在线查看 32 平台热搜
- [TikHub API](https://api.tikhub.io/) - 商业 API（抖音/小红书/微博/知乎/B站）
- [hot-search MCP](https://github.com/aiyogg/hot-search) - 热搜 MCP 服务
- [bilibili-api](https://github.com/Syugen/bilibili-api) - 哔哩哔哩全接口库

---

*文档创建：2026-04-28*
*最后更新：2026-04-28（增加现成接口资源章节）*
