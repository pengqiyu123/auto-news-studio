# Agent HTML Source Check 2026-05-07

本文件记录 2026-05-07 对 `D:\python\Auto-news2\aggregated_all_sources_20260507_145744.json` 中候选网址进行的**真实联网可访问性验证**结果。

验证方式：

- 使用真实 HTTP 请求访问候选 URL
- 请求头使用常规桌面浏览器 `User-Agent`
- 允许重定向
- 超时 15 秒
- 本轮仅验证“网址是否可访问并返回页面”
- 本轮**不代表**已经完成 RSS 适配、HTML 列表解析、正文抽取与新旧对比

## 总结

- 总数：40
- 可访问：32
- 403 / 401 拦截：3
- 超时：1
- 非 2xx/3xx 异常状态：1
- 证书 / DNS 等请求异常：3

## 可访问网址

### 综合科技媒体

- `36氪` — `https://36kr.com`
- `钛媒体` — `https://www.tmtpost.com`
- `虎嗅` — `https://www.huxiu.com`
- `创业邦` — `https://www.cyzone.cn`
- `品玩` — `https://www.pingwest.com`
- `爱范儿` — `https://www.ifanr.com`
- `雷科技` — `https://www.leikeji.com`

### 数码产品媒体

- `中关村在线` — `https://www.zol.com.cn`
- `太平洋电脑网` — `https://www.pconline.com.cn`
- `手机中国` — `https://www.cnmo.com`
- `什么值得买` — `https://www.smzdm.com`
- `IT之家` — `https://www.ithome.com`
- `驱动之家` — `https://www.mydrivers.com`

### AI 与芯片媒体

- `机器之心` — `https://www.jiqizhixin.com`
- `深度学习技术前沿` — `https://www.deeplearn.me`
- `量子位` — `https://www.qbitai.com`
- `智东西` — `https://www.zhidx.com`
- `半导体行业观察` — `https://www.semiconductor-today.com`

### 国际科技媒体

- `TechCrunch` — `https://techcrunch.com`
- `The Verge` — `https://www.theverge.com`
- `Engadget` — `https://www.engadget.com`
- `CNET` — `https://www.cnet.com`
- `Wired` — `https://www.wired.com`
- `Ars Technica` — `https://arstechnica.com`
- `Tom's Hardware` — `https://www.tomshardware.com`
- `AnandTech` — `https://www.anandtech.com`
  实际跳转到：`https://forums.anandtech.com/`

### 官方博客 / 官方入口

- `华为官方博客` — `https://www.huawei.com/cn`
- `小米官方博客` — `https://www.mi.com`
- `Apple Newsroom` — `https://www.apple.com/newsroom`
- `Samsung Newsroom` — `https://news.samsung.com`
- `NVIDIA Blog` — `https://blogs.nvidia.com`
- `Intel Newsroom` — `https://newsroom.intel.com`

## 补充搜集并验证成功的网址

以下网址不是直接从原始聚合文件照抄，而是额外补充搜索后进行真实请求验证得到。

- `Microsoft Official Blog` — `https://blogs.microsoft.com/`
- `Anthropic News` — `https://www.anthropic.com/news`
- `Amazon AWS News` — `https://www.aboutamazon.com/amazon-aws-news`
- `Google DeepMind Blog` — `https://deepmind.google/discover/blog/`
  实际跳转到：`https://deepmind.google/blog/`

## 当前不可用网址

### 被拦截

- `极客公园` — `https://www.geekpark.net` — `403`
- `电子发烧友` — `https://www.elecfans.com` — `403`
- `OpenAI Blog` — `https://openai.com/blog` — `403`
- `OpenAI News` — `https://openai.com/news/` — `403`

### 超时

- `芯东西` — `https://www.xindongxi.com`

### 状态异常

- `AMD Newsroom` — `https://www.amd.com/en/newsroom` — `404`

### 请求异常

- `爱搞机` — `https://www.aigaoji.com` — 证书主机名不匹配
- `数码多` — `https://www.soomal.com` — 证书链异常
- `AI前线` — `https://www.aifrontier.com` — DNS 解析失败
- `Meta Newsroom` — `https://about.fb.com/news/` — DNS 解析失败
- `Google Blog About` — `https://blog.google/about/` — SSL EOF
- `Google Search Blog` — `https://blog.google/products/search/` — SSL EOF

### 补充搜集但超时

- `Hugging Face Blog` — `https://huggingface.co/blog`
- `Mistral AI News` — `https://mistral.ai/news`

## 后续建议

- 先从“可访问网址”里继续拆分：
  - 哪些优先用 RSS
  - 哪些优先用 HTML 列表解析
  - 哪些虽然可访问，但结构复杂，后续可能需要浏览器抓取
- 对 `403` 站点单独做第二轮验证：
  - 是否存在 RSS
  - 是否存在可替代的官方新闻页
  - 是否需要浏览器会话或更强反爬策略

## 全量 HTML 文章获取能力验证

本轮对当前“已验证可访问”的网址继续执行了 HTML 文章能力测试，目标是回答：

- 列表页是否可打开
- 是否能找到像文章页的候选链接
- 详情页是否可抓取
- 是否能抽取出足够长的正文

判定口径：

- `working`
  当前启发式规则下，已经能找到文章级候选，并成功抽取正文
- `needs_rules`
  页面能抓，但当前候选筛选不够准，容易命中栏目页、专题页、商城页或其他非文章页
- `failed`
  当前环境下请求失败，或无法完成有效验证

### 当前可直接用于 HTML 的站点

- `钛媒体`
- `品玩`
- `爱范儿`
- `雷科技`
- `中关村在线`
- `太平洋电脑网`
- `手机中国`
- `IT之家`
- `驱动之家`
- `深度学习技术前沿`
- `量子位`
- `智东西`
- `半导体行业观察`
- `TechCrunch`
- `The Verge`
- `CNET`
- `Wired`
- `Ars Technica`
- `Tom's Hardware`
- `华为官方博客`
- `Apple Newsroom`
- `Microsoft Official Blog`
- `Anthropic News`
- `Amazon AWS News`

说明：

- 上述站点在当前测试下，已至少成功命中 1 个文章候选，并完成正文抽取
- 这代表“HTML 文章获取能力可用”，不代表当前规则已经达到生产级最优

### 当前需要补站点规则的站点

- `36氪`
- `虎嗅`
- `创业邦`
- `什么值得买`
- `机器之心`
- `Engadget`
- `AnandTech`
- `小米官方博客`
- `Samsung Newsroom`
- `Intel Newsroom`
- `Google DeepMind Blog`

说明：

- 这些站点并不是“不能抓”
- 问题主要在于当前启发式候选筛选会误命中：
  - 栏目页
  - 专题页
  - 搜索页
  - 商城页
  - 媒体素材页
- 适合后续为每个站点补充更精确的 `allow/deny` 规则

特别备注：

- `Samsung Newsroom`
  页面与正文提取都正常，但当前更容易命中媒体库和栏目页，不是文章页
- `Intel Newsroom`
  已经抓到新闻页正文，但当前启发式标题判定偏保守，建议后续放宽标题规则
- `小米官方博客`
  当前误命中商城页，说明站点入口可访问，但文章页筛选规则需要重做

### 当前验证失败的站点

- `NVIDIA Blog`

说明：

- 本轮在 HTML 验证阶段出现 DNS / 请求异常
- 但该站点前面已经确认 RSS 可用，项目接入时优先走 RSS 即可
