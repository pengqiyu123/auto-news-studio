# Auto News Studio 第三阶段设计文档：实体标签层

更新时间：2026-04-28

## 定位

**实体标签层 = 辅助浏览层，不是主事实层。**

```
主事实层（不动）：
discovery_items → intel_events → intel_alerts → drafts

辅助层（新增）：
                        ↓
               IntelEvent.entities[]（多标签）
                        ↓
            EntityRegistry（实体注册表）
                        ↓
           前端：按实体筛选 / 重点监控实体
```

核心原则：
- 一个事件可以有多个实体标签（many-to-many），不撕裂事件
- 实体标签不参与聚类，不改变主事实链
- 前端先加筛选能力，不改首页主逻辑

---

## 1. 实体提取方案

### 方案对比

| 方案 | 成本 | 中文支持 | 准确性 | 延迟 | 推荐 |
|------|------|---------|--------|------|------|
| spaCy zh_core_web_lg | 免费（自托管） | ✅ | 高 | 中 | **推荐** |
| spaCy zh_core_web_md | 免费（自托管） | ✅ | 中 | 低 | lg 不可用时降级 |
| 关键词匹配 | 免费 | ✅ | 低 | 低 | 始终兜底 |
| Google Cloud NLU API | $0.0010/1K 字符 | ✅ | 高 | 低 | 需要 GCP 账号 |
| LLM 提取 | Token 费用 | ✅ | 中高 | 高 | 有现成 LLM 时可用 |

### 推荐：spaCy 三档降级 + 关键词全程兜底

**降级链**：

```
优先：spacy.load("zh_core_web_lg")
  ↓ 失败则降级
次优：spacy.load("zh_core_web_md")
  ↓ 失败则降级
兜底：只跑关键词表（无 NER）
```

**理由**：部署环境如果没装 spaCy 大模型，整个实体层不能直接空掉。

---

## 2. 别名归一设计（显式两层）

### 为什么不能只靠 hash

如果直接用 `hashlib.md5(name.encode())` 做 entity_id，会出现：
- "苹果" 和 "Apple" 是两个不同的 ID
- "OpenAI" 和 "Open AI" 是两个不同的 ID
- 中文英文完全裂开

### 设计：alias → canonical_name → entity_id

```
"苹果" → "Apple" → "abc123"
"Apple" → "Apple" → "abc123"  （同一个 ID）
"Apple Inc." → "Apple" → "abc123"  （别名归一）
```

**别名映射表**（开箱即用）：

```python
# entity_aliases.py
# alias（小写） → canonical_name
ALIAS_MAP = {
    # 科技公司
    "apple": "Apple",
    "apple inc": "Apple",
    "苹果": "Apple",
    "apple公司": "Apple",
    "huawei": "Huawei",
    "华为": "Huawei",
    "huawei公司": "Huawei",
    "华为公司": "Huawei",
    "tencent": "Tencent",
    "腾讯": "Tencent",
    "alibaba": "Alibaba",
    "阿里巴巴": "Alibaba",
    "bytedance": "ByteDance",
    "字节跳动": "ByteDance",
    "xiaomi": "Xiaomi",
    "小米": "Xiaomi",
    "google": "Google",
    "谷歌": "Google",
    "微软": "Microsoft",
    "openai": "OpenAI",
    "open ai": "OpenAI",
    "nvidia": "NVIDIA",
    "英伟达": "NVIDIA",
    "qualcomm": "Qualcomm",
    "高通": "Qualcomm",
    # AI / 模型
    "chatgpt": "ChatGPT",
    "gpt4": "GPT-4",
    "gpt-4": "GPT-4",
    "gpt5": "GPT-5",
    "gpt-5": "GPT-5",
    "claude": "Claude",
    "gemini": "Gemini",
    "llama": "Llama",
    "stable diffusion": "Stable Diffusion",
    "midjourney": "Midjourney",
    # 操作系统
    "ios": "iOS",
    "android": "Android",
    "安卓": "Android",
    "harmonyos": "HarmonyOS",
    "鸿蒙": "HarmonyOS",
    "macos": "macOS",
    "windows": "Windows",
    # 人物
    "tim cook": "Tim Cook",
    "库克": "Tim Cook",
    "elon musk": "Elon Musk",
    "马斯克": "Elon Musk",
    "sam altman": "Sam Altman",
    "jensen huang": "Jensen Huang",
    "黄仁勋": "Jensen Huang",
}
```

**提取时先用别名表归一，再查 canonical_name**，保证中英文混排场景能正确合并。

### 预置实体表（canonical_name → entity_type）

```python
CANONICAL_ENTITIES = {
    # 科技公司（ORG）
    "Apple": "ORG",
    "Huawei": "ORG",
    "Tencent": "ORG",
    "Alibaba": "ORG",
    "ByteDance": "ORG",
    "Xiaomi": "ORG",
    "Samsung": "ORG",
    "Google": "ORG",
    "Microsoft": "ORG",
    "Meta": "ORG",
    "Amazon": "ORG",
    "OpenAI": "ORG",
    "Anthropic": "ORG",
    "NVIDIA": "ORG",
    "Qualcomm": "ORG",
    "TSMC": "ORG",
    "SpaceX": "ORG",
    "Tesla": "ORG",
    # AI / 模型（PRODUCT）
    "ChatGPT": "PRODUCT",
    "GPT-4": "PRODUCT",
    "GPT-5": "PRODUCT",
    "Claude": "PRODUCT",
    "Gemini": "PRODUCT",
    "Llama": "PRODUCT",
    "Stable Diffusion": "PRODUCT",
    "Midjourney": "PRODUCT",
    # 操作系统（PRODUCT）
    "iOS": "PRODUCT",
    "Android": "PRODUCT",
    "HarmonyOS": "PRODUCT",
    "Windows": "PRODUCT",
    "macOS": "PRODUCT",
    # 人物（PERSON）
    "Tim Cook": "PERSON",
    "Elon Musk": "PERSON",
    "Sam Altman": "PERSON",
    "Jensen Huang": "PERSON",
    "Satya Nadella": "PERSON",
}
```

**关键词表必须带 entity_type**，不能全记成 ORG：
```

---

## 3. 提取逻辑设计

### 提取时机

**在事件聚合之后**，对每个 IntelEvent 的 summary 和 title 做 NER：

```
discovery_items → 聚类 → intel_events → [实体提取] → 前端展示
```

理由：
1. 事件级别的 summary 包含多篇文章的信息，实体更丰富
2. 不增加聚类复杂度
3. 一个事件对应一个实体标签集合，关系简单

### 提取函数

```python
# entity_extractor.py
import spacy
import re
import hashlib

# =============================================
# 别名归一表（小写 alias → canonical_name）
# =============================================
from .entity_aliases import ALIAS_MAP

# =============================================
# 预置实体表（canonical_name → entity_type）
# =============================================
from .entity_types import CANONICAL_ENTITIES

# =============================================
# spaCy 降级链
# =============================================
_nlp = None
_nlp_level = None  # "lg" | "md" | None

def _get_nlp():
    global _nlp, _nlp_level
    if _nlp is not None:
        return _nlp

    for model_name in ("zh_core_web_lg", "zh_core_web_md"):
        try:
            _nlp = spacy.load(model_name)
            _nlp_level = model_name.split("_")[-1]  # "lg" or "md"
            return _nlp
        except OSError:
            continue

    # 全部失败：降级到纯关键词模式
    _nlp = None
    _nlp_level = None
    return None

# =============================================
# 提取核心逻辑
# =============================================
def extract_entities(text: str) -> list[dict]:
    """
    从文本中提取实体，返回 list[dict]:
      [{"canonical": "Apple", "type": "ORG"}, ...]
    """
    results: dict[str, dict] = {}  # canonical_name → {canonical, type}

    # ---- 1. spaCy NER（降级链）----
    nlp = _get_nlp()
    if nlp is not None:
        doc = nlp(text[:3000])
        for ent in doc.ents:
            if ent.label_ in {"ORG", "PERSON", "GPE", "PRODUCT", "EVENT"}:
                # 别名归一
                canonical = _normalize(ent.text)
                if canonical not in results:
                    results[canonical] = {
                        "canonical": CANONICAL_ENTITIES.get(canonical, canonical),
                        "type": ent.label_,
                    }
                # 若别名表有更精确的 type，覆盖
                if canonical in CANONICAL_ENTITIES:
                    results[canonical]["type"] = CANONICAL_ENTITIES[canonical]

    # ---- 2. 关键词正则匹配（始终运行）----
    patterns = [
        # 英文关键词
        r"(?i)(OpenAI|Anthropic|NVIDIA|Qualcomm|GPT-\d|ChatGPT|Claude|Gemini|Llama|Stable\s*Diffusion|Midjourney|Apple|Huawei|Tencent|Alibaba|ByteDance|Xiaomi|Samsung|Google|Microsoft|Meta|Amazon|SpaceX|Tesla|iOS|Android|HarmonyOS|Windows|macOS|Linux|Tim\s*Cook|Elon\s*Musk|Sam\s*Altman|Jensen\s*Huang)",
        # 中文关键词
        r"(?:苹果|华为|腾讯|阿里|字节|小米|高通|英伟达|鸿蒙|安卓|谷歌|微软|Meta|亚马逊|OpenAI|Anthropic|NVIDIA|骁龙|特斯拉|马斯克|黄仁勋|库克|奥特曼)",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            raw = match.group().strip()
            canonical = _normalize(raw)
            canonical_fixed = CANONICAL_ENTITIES.get(canonical, canonical)
            entity_type = CANONICAL_ENTITIES.get(canonical, "ORG")
            if canonical not in results:
                results[canonical] = {"canonical": canonical_fixed, "type": entity_type}

    # 限制单事件最大实体数（防膨胀）
    return list(results.values())[:10]


def _normalize(name: str) -> str:
    """别名归一：小写去空格，查别名表"""
    key = name.strip().lower()
    return ALIAS_MAP.get(key, name.strip())


def entity_id(canonical_name: str) -> str:
    """生成稳定的 entity ID"""
    return hashlib.md5(canonical_name.encode("utf-8")).hexdigest()[:12]
```

### 集成到 intel_pipeline

```python
# intel_pipeline.py 新增
def build_intel_state(...):
    # ... 现有逻辑 ...

    for cluster in clusters:
        event = _build_event_from_cluster(cluster, ...)
        # 新增：提取实体标签（只注入，不改聚类）
        event_text = f"{event['title']} {event['summary']}"
        extracted = extract_entities(event_text)
        event["entity_ids"] = [entity_id(e["canonical"]) for e in extracted]
        event["entity_names"] = [e["canonical"] for e in extracted]
        events.append(event)

    return {
        "discovery_items": discovery_items,
        "intel_events": events,
        "event_snapshots": snapshots,
        "intel_alerts": alerts,
    }
```

---

## 4. 数据模型

### IntelEvent 新增字段

```python
class IntelEvent(BaseModel):
    # ... 现有字段 ...
    entity_ids: list[str] = Field(default_factory=list)   # canonical entity ID 列表
    entity_names: list[str] = Field(default_factory=list)  # canonical 名称列表（前端展示用）

**Phase 1 只用 `entity_names` 即可**，不需要维护完整的 EntityRegistry CRUD。

---

## 5. 实施路径

### 阶段一：最小落地——事件打标签（本次实施）

**改动范围（最小）**：

| 文件 | 改动 |
|------|------|
| `backend/app/entity_aliases.py`（新增） | 别名归一表 |
| `backend/app/entity_types.py`（新增） | 预置实体 canonical → type |
| `backend/app/entity_extractor.py`（新增） | 提取函数， spaCy 降级链 |
| `backend/app/intel_pipeline.py` | 事件生成后调用提取，注入 `entity_ids` + `entity_names` |
| `backend/app/models.py` | IntelEvent 加 `entity_ids` + `entity_names` |
| `frontend/src/types.ts` | 前端类型对齐 |
| `frontend/src/components/IntelEventsPage.tsx` | 卡片显示实体标签 chips |

**不做的**：
- 实体注册表 CRUD 界面
- 全局 EntityRegistry 持久化
- 重点监控面板
- 实体统计看板

**验收**：
- 跑一轮 radar_only，intel_events 有 `entity_names` 字段
- 热点簇卡片底部显示实体标签（如 `[ORG] Apple  [PRODUCT] GPT-5`）
- 编译通过

### 阶段二：前端筛选与监控面板

改动范围：
- `IntelEventsPage.tsx`：实体筛选下拉
- `IntelAlertsPage.tsx`：实体筛选下拉
- 新增 `EntityWatchlistPanel.tsx`：重点监控实体（简单列表，无统计）

### 阶段三：实体统计与看板

改动范围：
- `store.py`：新增实体统计接口
- 前端看板展示 Top N 实体热度

---

## 6. 前端设计（阶段二+三）

### 热点簇页面：实体筛选

在排序切换旁边加实体筛选下拉：

```
┌──────────────────────────────────────────────┐
│  热点簇           20 个事件                    │
├──────────────────────────────────────────────┤
│  排序：[总分▼]  筛选：[全部实体▾]  [+重点监控] │
└──────────────────────────────────────────────┘
```

下拉内容：
- 全部实体
- 分隔线
- 👁 重点监控（勾选框）
- 公司 A（5）
- 公司 B（3）
- ...

### 6.1 事件卡片：实体标签

在事件卡片底部加实体标签行：

```
┌──────────────────────────────────────────────┐
│ [ORG] Apple  [ORG] OpenAI  [PRODUCT] GPT-5 │
└──────────────────────────────────────────────┘
```

### 6.2 重点监控实体面板

入口：侧边栏或设置页

```
┌──────────────────────────────────────────────┐
│ 重点监控实体                                  │
├──────────────────────────────────────────────┤
│ [+ 添加实体]                                  │
├──────────────────────────────────────────────┤
│ 👁 Apple      事件 8  预警 2  升温中        │
│ 👁 华为       事件 5  预警 1  平稳          │
│ 👁 OpenAI     事件 6  预警 1  升温中        │
│ 👁 Anthropic  事件 3  预警 0  平稳          │
└──────────────────────────────────────────────┘
```

点击某行 → 跳转热点簇页面，自动筛选该实体。

### 6.3 预警台：按实体过滤

在等级 chips 旁边加实体下拉，与热点簇一致。

---

## 7. 不做的事

| 常见需求 | 为什么不现在做 |
|---------|-------------|
| 首页主视图改成品牌桶 | 主事实层还不稳，先做辅助层 |
| 自动发现新品牌/新公司 | 先用预置列表 + 关键词，够用 |
| 实体级别的趋势预测 | 需要多轮数据积累，现在数据还不够 |
| 竞品对比分析 | 需要阶段二先稳定 |
| 全局 EntityRegistry CRUD | Phase 1 只做事件打标签，不需要 |

---

## 8. 风险与兜底

| 风险 | 缓解方案 |
|------|---------|
| spaCy 模型加载失败 | 降级链：lg → md → 纯关键词 |
| 关键词表全记成 ORG | 关键词表显式带 entity_type，不依赖 NER label |
| 中英文别名分裂 | 显式别名归一表（小写 alias → canonical_name）|
| 实体数量膨胀 | 限制单事件最大 10 个实体 |
| spaCy 模型加载慢 | 全局单例 `_nlp`，进程只加载一次 |

---

*文档创建：2026-04-28，最后更新：2026-04-28*
*基于 Feedly Clustering / Brandwatch Topics / spaCy NER 调研*
*采纳：spaCy 降级链 / 关键词显式 entity_type / 别名归一两层设计 / Phase 1 最小落地*
