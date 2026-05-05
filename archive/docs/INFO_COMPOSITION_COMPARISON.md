# Auto News Studio 第二阶段调研文档

## 稿件阶段：信息到文章的自动化

更新时间：2026-04-28

## 概述

本文档分析 Auto News Studio 第二阶段"稿件阶段"的技术方案，涵盖：
- AI 写作生成
- 去 AI 味处理
- 公众号草稿创建
- 多平台同步发布

---

## 当前项目现状

### 现有稿件流程（composer.py）

我们的 `composer.py` 已实现基础稿件生成：

```python
# 工作流程：选题 → 大纲 → 文章 → 标题 → 摘要
compose_draft(candidate, normalized_item, publish_mode, risk_keywords, llm_service)
```

**当前能力：**
- LLM 生成：大纲 + 文章 + 标题 + 摘要
- Python 模板兜底：无需 LLM 时降级使用
- Markdown 输出 + HTML 转换
- 风险词检测
- 编辑备注生成

**待提升空间：**
- 无素材搜索（无法获取选题的背景信息）
- 无去 AI 味处理
- 无多平台发布
- 无封面图生成

---

## 高星参考项目对比

### 一、AIWriteX (⭐500+)

**核心功能：**
- CrewAI 多智能体协作：研究员 → 作家 → 审核员 → 设计师
- AIForge 实时搜索：抓取竞品文章和背景资料
- 维度创意变换：同一素材多种风格
- 去 AI 味优化

**CrewAI 工作流示例：**
```python
# 内容生成引擎
crew = Crew(
    agents=[researcher, writer, reviewer, designer],
    tasks=[research_task, write_task, review_task, design_task],
    process=Process.sequential,  # 顺序执行
    verbose=True,
)
result = crew.kickoff(inputs=input_data)
```

**AIForge 搜索：**
```python
# 实时获取选题相关背景
results = aiforge_search(query, max_results=10)
```

**去 AI 味（基于 Humanizer-zh）：**
| 类别 | 检测模式 | 处理 |
|------|----------|------|
| 内容模式 | 过度强调意义、宣传语言 | 重写为自然表达 |
| 语言模式 | AI 词汇、否定排比、三段式 | 打乱公式结构 |
| 风格模式 | 破折号过度、粗体滥用 | 保留核心特征 |
| 填充词 | 填充短语、通用结论 | 删除客套话 |

---

### 二、md2wechat-skill

**核心功能：**
- Markdown → 微信格式 HTML
- 风格写作（Dan Koe 等）
- AI 去痕（三种强度）
- 封面图生成
- 草稿推送

**工作流程：**
```
Markdown 写作 → inspect(元数据检查) → preview(本地预览) → convert(转换) → draft(草稿)
```

**风格写作示例：**
```bash
# 查看可用风格
md2wechat write --list

# 用指定风格写文章
md2wechat write --style dan-koe

# 写作 + 去痕
md2wechat write --style dan-koe --humanize --humanize-intensity aggressive
```

**去痕效果对比：**
| 原文（AI 味） | 去痕后 |
|--------------|--------|
| 在当今快速发展的科技时代... | 这几年，AI 变化太快了 |
| 人工智能的重要性不言而喻... | AI 挺重要的，但不是玄乎的重要 |
| 此外，AI 技术还在改善我们的日常生活 | 顺手提一句，AI 确实让生活方便了不少 |

---

### 三、wechat-publisher-mcp

**核心功能：**
- MCP 服务接口
- Markdown → 微信 HTML 转换
- 封面图处理
- 预览 + 正式发布

**API 接口：**
| 工具 | 说明 |
|------|------|
| `wechat_publish_article` | 发布/预览文章 |
| `wechat_query_status` | 查询发布状态 |

**Claude Desktop 配置：**
```json
{
  "mcpServers": {
    "wechat-publisher": {
      "command": "wechat-publisher-mcp",
      "args": []
    }
  }
}
```

---

### 四、Wechatsync (⭐2k+)

**核心功能：**
- 29+ 平台同步
- Chrome 浏览器扩展
- MCP Server 支持
- CLI 工具

**支持平台：**
| 分类 | 平台 |
|------|------|
| 主流自媒体 | 微信公众号、知乎、小红书、抖音 |
| 技术社区 | 掘金、CSDN、SegmentFault、开源中国 |
| 通用平台 | 微博、头条、百家号、简书 |
| 财经 | 雪球、东方财富 |
| 自建站 | WordPress、Typecho、Hexo、Hugo |

**MCP 配置：**
```json
{
  "mcpServers": {
    "sync-assistant": {
      "command": "node",
      "args": ["/path/to/Wechatsync/packages/mcp-server/dist/index.js"],
      "env": {
        "MCP_TOKEN": "your-secret-token-here"
      }
    }
  }
}
```

**CLI 使用：**
```bash
# 同步文章到多个平台
wechatsync sync article.md -p zhihu,juejin,csdn

# 检查平台登录状态
wechatsync platforms --auth

# 从浏览器当前页面提取文章
wechatsync extract -o article.md
```

---

## 联网调研结果

### 一、微信公众号 API 自动化

**Tavily 调研发现：**

| 项目 | 说明 | 来源 |
|------|------|------|
| WeChat Draft Publisher | 自动发布 HTML 到草稿箱 | agentskills.best |
| wechat-article-publisher-skill | Claude Skill，Markdown/HTML → 草稿 | GitHub ⭐ |
| WeChat Auto-Publisher | Chrome CDP 自动化 | MCP Market |
| awkn-post-to-wechat | Claude Code skill | MCP Market |
| WeChat-MCP | 5 个子智能体 | GitHub |

**推荐方案（按集成难度）：**

1. **wechat-article-publisher-skill**（最简单）
   - 安装：`npx skills add https://github.com/iamzifei/wechat-article-publisher-skill`
   - 使用：`wechat-article-publisher publish article.md`

2. **API 直连**（我们已有基础）
   - 使用 `publishers.py` 中的 Playwright 方案
   - 或直接调用微信 API

3. **MCP 集成**（长期）
   - 接入 wechat-publisher-mcp
   - 或接入 Wechatsync MCP Server

---

### 二、AI 写作与去 AI 味

**Tavily 调研发现：**

| 工具 | 说明 | 特点 |
|------|------|------|
| GPTinf AI Humanizer | 重写 AI 文本绕过检测 | 去除 AI 检测信号 |
| AIHumanize.io | 保持语义的人性化改写 | 支持批量处理 |
| WriteHuman AI | 转 AI 文本为自然语言 | 完全不可检测 |
| Undetectable AI | 通过主流 AI 检测器 | 适合学术场景 |
| TextToHuman.com | AI → 真人写作风格 | 精确快速 |

**md2wechat 的去痕系统（最实用）：**

```bash
# 三种处理强度
md2wechat humanize article.md --intensity gentle   # 温和
md2wechat humanize article.md --intensity medium   # 中等（默认）
md2wechat humanize article.md --intensity aggressive # 激进

# 质量评分（5 维度，50 分制）
# 45-50: 优秀
# 35-44: 良好
# <35: 需重新修订
```

---

### 三、CrewAI 多智能体写作

**Tavily 调研发现：**

| 项目 | 说明 |
|------|------|
| CrewAI | 多智能体编排平台 |
| Autonomous Research Pipeline | 完全自主的研究+写作管线 |

**CrewAI 写作工作流：**
```python
from crewai import Crew, Agent, Task, Process

# 定义智能体
researcher = Agent(
    role='Content Researcher',
    goal='Research real world data for the topic',
    backstory="You specialize in researching...",
    verbose=True,
    allow_delegation=False,
    tools=[search_tool, browse_tool]
)

writer = Agent(
    role='Technical Writer',
    goal='Write a concise, engaging blog post',
    backstory="You transform complex concepts into compelling narratives...",
    verbose=True,
    allow_delegation=False
)

# 定义任务
research_task = Task(
    description="Research the latest AI trends",
    expected_output="3 key AI trends with brief descriptions",
    agent=researcher
)

write_task = Task(
    description="Write a blog post about research findings",
    expected_output="~200 word blog post",
    agent=writer
)

# 编排工作流
crew = Crew(
    agents=[researcher, writer],
    tasks=[research_task, write_task],
    process=Process.sequential
)

result = crew.kickoff()
```

---

### 四、多平台同步方案

**Tavily 调研发现：**

| 方案 | 平台数 | 特点 |
|------|--------|------|
| Wechatsync | 29+ | 开源免费，MCP 支持 |
| Wechatsync CLI | 29+ | 命令行工具 |
| 官方 API | 各平台独立 | 需要分别对接 |

**Wechatsync 的 MCP 工具：**
| 工具 | 说明 |
|------|------|
| `list_platforms` | 列出所有平台及登录状态 |
| `check_auth` | 检查指定平台登录状态 |
| `sync_article` | 同步文章到指定平台（草稿） |
| `extract_article` | 从当前浏览器页面提取文章 |
| `upload_image_file` | 上传本地图片到平台 |

---

## 差距分析

### 稿件生成层面

| 维度 | 我们 | AIWriteX/md2wechat | 差距 |
|------|------|-------------------|------|
| 素材搜索 | 无 | AIForge / Tavily | **-1** |
| 多风格生成 | 无 | CrewAI 编排 | **-1** |
| 去 AI 味 | 无 | Humanizer 体系 | **-1** |
| 封面图生成 | 无 | 通义/ModelScope | **-1** |
| 编辑预览 | 有 | 有 | 持平 |

### 发布层面

| 维度 | 我们 | Wechatsync | 差距 |
|------|------|-------------|------|
| 多平台同步 | 无 | 29+ 平台 | **-29** |
| MCP 支持 | 无 | 有 | **-1** |
| 草稿优先 | 有 | 有 | 持平 |
| 浏览器登录态 | Playwright | Chrome Ext | 可借鉴 |

### 技术实现层面

| 维度 | 我们 | 参考项目 | 差距 |
|------|------|----------|------|
| 多智能体 | 无 | CrewAI | **-1** |
| MCP 协议 | 无 | wechat-publisher/Wechatsync | **-1** |
| 浏览器自动化 | Playwright | Chrome Ext (Wechatsync) | 可借鉴 |

---

## 现成可用接口资源

### 一、微信草稿发布

| 资源 | Stars | 说明 | 链接 |
|------|-------|------|------|
| **wechat-article-publisher-skill** | - | Claude Skill，Markdown/HTML → 草稿 | [GitHub](https://github.com/iamzifei/wechat-article-publisher-skill) |
| **wechat-publisher-mcp** | - | MCP 服务 | [GitHub](https://github.com/your-username/wechat-publisher-mcp) |
| **WeChat-MCP** | - | 5 子智能体 | [GitHub](https://github.com/BiboyQG/WeChat-MCP) |
| **awkn-post-to-wechat** | - | Claude Code skill | [MCP Market](https://mcpmarket.com/tools/skills/wechat-auto-publisher) |

### 二、多平台同步

| 资源 | Stars | 说明 | 链接 |
|------|-------|------|------|
| **Wechatsync** | ⭐2k+ | 29+ 平台，MCP/CLI | [GitHub](https://github.com/wechatsync/Wechatsync) |
| **Wechatsync MCP** | - | MCP Server | [packages/mcp-server](https://github.com/wechatsync/Wechatsync/tree/main/packages/mcp-server) |

### 三、AI 写作与去 AI 味

| 资源 | Stars | 说明 | 链接 |
|------|-------|------|------|
| **md2wechat** | - | 去痕系统，三种强度 | [GitHub](https://github.com/geekjourneyx/md2wechat-skill) |
| **Humanizer-zh** | - | 中文 AI 去痕 | [GitHub](https://github.com/op7418/Humanizer-zh) |
| **CrewAI** | ⭐20k+ | 多智能体编排 | [crewai.com](https://crewai.com/) |
| **AIHumanize.io** | - | 在线去 AI 味 | [aihumanize.io](https://aihumanize.io/) |
| **Undetectable AI** | - | 通过检测器 | [undetectable.ai](https://undetectable.ai/) |

### 四、素材搜索

| 资源 | Stars | 说明 | 链接 |
|------|-------|------|------|
| **Tavily** | - | AI 搜索 API，1000次/月免费 | [tavily.com](https://tavily.com) |
| **AIForge** | - | AIWriteX 内置搜索 | - |

---

## 对接我们项目示例

### 1. 素材搜索（Tavily）

```python
# connectors.py 新增 search connector
import requests

TAVILY_API_KEY = "tvly-xxx"  # 从配置读取

async def search_background(query: str, max_results: int = 5) -> list[dict]:
    """搜索选题相关背景资料"""
    url = "https://api.tavily.com/search"
    payload = {
        "api_key": TAVILY_API_KEY,
        "query": query,
        "max_results": max_results,
        "include_answer": True,
    }
    resp = requests.post(url, json=payload, timeout=30)
    data = resp.json()
    return data.get("results", [])
```

### 2. 去 AI 味处理

```python
# composer.py 新增 humanize 函数
async def humanize_article(markdown: str, intensity: str = "medium") -> str:
    """调用 AI 去痕"""
    # 方案 A：使用 md2wechat humanize 子命令
    import subprocess
    result = subprocess.run(
        ["md2wechat", "humanize", "article.md", "--intensity", intensity],
        capture_output=True, text=True
    )
    return result.stdout

    # 方案 B：自己实现简单规则
    text = markdown
    # 去除 AI 填充词
    fillers = ["值得注意的是", "需要指出的是", "不言而喻的是"]
    for f in fillers:
        text = text.replace(f, "")
    # 变化句子长度
    # ... 省略
    return text
```

### 3. 微信草稿发布（MCP）

```python
# publishers.py 新增 MCP 客户端
from mcp import Client

async def publish_to_wechat_draft(markdown: str, title: str, cover_path: str = None) -> dict:
    """通过 MCP 发布到微信草稿"""
    # 方案 A：调用 wechat-publisher-mcp
    async with Client("wechat-publisher-mcp") as mcp:
        result = await mcp.call_tool("wechat_publish_article", {
            "title": title,
            "content": markdown,
            "coverImagePath": cover_path,
            "previewMode": False
        })
        return result

    # 方案 B：直接调用微信 API（我们已有）
    # 见 publishers.py 的现有实现
```

### 4. 多平台同步（Wechatsync MCP）

```python
# publishers.py 新增多平台同步
async def sync_to_platforms(
    markdown: str,
    platforms: list[str],  # ["zhihu", "juejin", "csdn"]
    title: str,
    cover_path: str = None
) -> dict:
    """同步文章到多个平台"""
    # 使用 Wechatsync MCP
    async with Client("wechatsync-mcp") as mcp:
        results = {}
        for platform in platforms:
            result = await mcp.call_tool("sync_article", {
                "content": markdown,
                "title": title,
                "platform": platform
            })
            results[platform] = result
        return results
```

### 5. CrewAI 多智能体写作

```python
# composer.py 新增 crew 模式
from crewai import Crew, Agent, Task, Process

async def crew_generate_article(topic: str, facts: list[str]) -> str:
    """CrewAI 多智能体写作"""
    researcher = Agent(
        role="Researcher",
        goal="Gather relevant background information",
        backstory="You are a research specialist...",
        tools=[tavily_search_tool]
    )

    writer = Agent(
        role="Writer",
        goal="Write engaging article content",
        backstory="You are an experienced journalist...",
        llm=llm_service
    )

    research_task = Task(
        description=f"Research and gather facts about: {topic}",
        expected_output="Comprehensive fact list",
        agent=researcher
    )

    write_task = Task(
        description=f"Write article using facts: {facts}",
        expected_output="Complete article in Markdown",
        agent=writer
    )

    crew = Crew(
        agents=[researcher, writer],
        tasks=[research_task, write_task],
        process=Process.sequential
    )

    result = crew.kickoff()
    return result.raw
```

---

## 可借鉴功能（按优先级）

### P0：立即可做（高价值，低成本）

#### 1. 素材搜索接入（Tavily）

**最快实现：**
```python
# connectors.py 新增
def _fetch_tavily(query: str, max_results: int = 5) -> list[dict]:
    """Tavily 搜索"""
    import os, requests
    api_key = os.environ.get("TAVILY_API_KEY") or config.get("tavily_api_key")
    if not api_key:
        return []
    resp = requests.post(
        "https://api.tavily.com/search",
        json={"api_key": api_key, "query": query, "max_results": max_results},
        timeout=30
    )
    return resp.json().get("results", [])
```

**免费额度：** 1000 次/月
**用途：** 为每个选题搜索背景资料，丰富文章内容

#### 2. 去 AI 味基础实现

**简单规则版（无需外部依赖）：**
```python
def simple_humanize(text: str) -> str:
    """简单去 AI 味"""
    # 去除 AI 填充词
    fillers = [
        "值得注意的是", "需要指出的是", "不言而喻的是",
        "首先", "其次", "最后", "综上所述",
        "因此", "所以", "由此可见"
    ]
    for f in fillers:
        text = text.replace(f, "")

    # 变化句子长度
    sentences = text.split("。")
    varied = []
    for i, s in enumerate(sentences):
        if s.strip() and i % 3 == 1:  # 每3句短一句
            s = s[:len(s)//2]  # 截断一半
        varied.append(s)
    text = "。".join(varied)

    return text
```

---

### P1：短期可做（中等价值，需要规划）

#### 3. 封面图生成

**使用 ModelScope（免费额度）：**
```python
# publishers.py 新增
async def generate_cover_image(title: str, summary: str) -> str:
    """AI 生成封面图"""
    from modelscope import snapshot_download
    from modelscope_outputs import ImageGeneration

    prompt = f"主题:{title}, 内容摘要:{summary}"
    generator = ImageGeneration()
    result = generator.generate(prompt)
    return result["image_url"]
```

#### 4. md2wechat 集成

**安装和使用：**
```bash
# 安装 CLI
npm install -g @geekjourneyx/md2wechat

# 或使用 Go
go install github.com/geekjourneyx/md2wechat-skill/cmd/md2wechat@v2.0.7

# 使用
md2wechat humanize article.md --intensity medium
md2wechat preview article.md
md2wechat convert article.md --draft --cover cover.jpg
```

#### 5. Wechatsync 集成

**安装 MCP Server：**
```bash
# 安装 Chrome 扩展并启用 MCP
# 在扩展设置中获取 Token

# Claude Desktop 配置
{
  "mcpServers": {
    "sync-assistant": {
      "command": "node",
      "args": ["/path/to/Wechatsync/packages/mcp-server/dist/index.js"],
      "env": {
        "MCP_TOKEN": "your-token"
      }
    }
  }
}
```

---

### P2：中期可做（高价值，需要设计）

#### 6. CrewAI 多智能体写作

**引入 CrewAI 依赖：**
```bash
pip install crewai
```

**工作流设计：**
```
选题输入 → Researcher(搜索素材) → Writer(生成文章) → Reviewer(审核) → Humanizer(去味)
```

#### 7. 多平台同步发布

**Wechatsync 平台列表：**
- 微信公众号（我们已有）
- 知乎、掘金、CSDN
- 头条号、百家号
- 小红书、微博

---

### P3：长期可做（高价值，成本高）

#### 8. MCP Server 自己实现

**参考 wechat-publisher-mcp：**
```python
# mcp_server.py
from mcp.server import Server

app = Server("wechat-publisher")

@app.list_tools()
async def list_tools():
    return [
        Tool(
            name="publish_draft",
            description="Publish article to WeChat draft",
            inputSchema={...}
        )
    ]

@app.call_tool()
async def call_tool(name, arguments):
    if name == "publish_draft":
        return await publish_draft(arguments)
```

#### 9. 完整 CrewAI Pipeline

**参考 AIWriteX：**
```
热点选题 → AIForge 搜索 → CrewAI 研究员 → CrewAI 作家 → 去 AI 味 → 封面图 → 草稿
```

---

## 实施建议

### 近期（1-2个月）

```
1. 素材搜索（P0）
   └── 接入 Tavily API

2. 去 AI 味基础版（P0）
   └── 简单规则实现

3. 封面图生成（P1）
   └── ModelScope 集成
```

### 中期（3-6个月）

```
4. md2wechat 集成（P1）
   └── 草稿推送复用

5. 去 AI 味增强版（P1）
   └── 对接 md2wechat humanize

6. Wechatsync 集成（P2）
   └── 多平台同步
```

### 远期（6个月+）

```
7. CrewAI 多智能体（P2）
   └── 研究员 + 作家 + 审核员

8. MCP Server 自实现（P3）
   └── 标准化接口

9. 完整 Pipeline（P3）
   └── 选题 → 素材 → 写作 → 去味 → 发布
```

---

## 技术债务清理

### composer.py 当前问题

1. **无素材搜索**：无法获取选题背景信息
2. **无去 AI 味**：生成文章有 AI 痕迹
3. **无封面图**：需要人工准备
4. **无多平台**：只支持微信公众号

### 建议的重构

```python
# 重构后的 composer.py 结构
composer/
├── __init__.py
├── base.py              # 基类和工具函数
├── generators/
│   ├── llm_generator.py    # LLM 生成
│   ├── template_generator.py # 模板生成
│   └── crew_generator.py    # CrewAI 生成
├── processors/
│   ├── humanizer.py         # 去 AI 味
│   ├── summarizer.py        # 摘要生成
│   └── title_generator.py   # 标题生成
├── publishers/
│   ├── wechat.py           # 微信公众号
│   ├── wechatsync.py       # 多平台同步
│   └── mcp.py              # MCP 发布
└── images/
    ├── cover_generator.py   # 封面图生成
    └── uploader.py          # 图片上传
```

---

## 参考链接

### 高星参考项目
- [AIWriteX](https://github.com/iniwap/AIWriteX) - ⭐500+，多智能体写作
- [md2wechat-skill](https://github.com/geekjourneyx/md2wechat-skill) - Markdown → 微信
- [wechat-publisher-mcp](https://github.com/your-username/wechat-publisher-mcp) - MCP 服务
- [Wechatsync](https://github.com/wechatsync/Wechatsync) - ⭐2k+，多平台同步

### 联网调研发现
- [wechat-article-publisher-skill](https://github.com/iamzifei/wechat-article-publisher-skill) - Claude Skill
- [WeChat-MCP](https://github.com/BiboyQG/WeChat-MCP) - 多智能体微信
- [CrewAI](https://crewai.com/) - 多智能体编排平台
- [Tavily](https://tavily.com) - AI 搜索 API

### AI 去 AI 味工具
- [AIHumanize.io](https://aihumanize.io/) - 在线去 AI 味
- [Undetectable AI](https://undetectable.ai/) - 通过检测器
- [Humanizer-zh](https://github.com/op7418/Humanizer-zh) - 中文去痕

---

*文档创建：2026-04-28*
*联网调研：Tavily API + 本地参考项目分析*
