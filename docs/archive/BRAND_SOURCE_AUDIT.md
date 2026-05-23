# 品牌官方信息源审计脚本

`[scripts/validate_brand_sources.py](/d:/python/Auto-news2/auto-news-studio/scripts/validate_brand_sources.py:1)` 用来按品牌搜索并验证官方信息源，当前只认两类可直连源：

- `RSS/Atom`
- `WordPress REST`

脚本会：

- 访问每个品牌的官网、新闻页、博客页
- 搜索页面里的 feed 线索
- 生成常见 feed 路径候选
- 用项目当前抓取逻辑直接测试候选源
- 输出 `JSON` 和 `Markdown` 报告

## 用法

全量跑一轮：

```powershell
.venv\Scripts\python scripts\validate_brand_sources.py
```

只测某几个品牌：

```powershell
.venv\Scripts\python scripts\validate_brand_sources.py --brand OpenAI --brand Apple
```

报告默认输出到：

- `runtime/brand-source-audit/brand_sources_latest.json`
- `runtime/brand-source-audit/brand_sources_latest.md`

## 判定规则

- `有`：当前 `auto-news-studio` 驱动可直连成功，并解析出有效条目
- `没有`：没找到可测试官方源，或找到了候选但当前驱动都未验证通过

## 说明

- 脚本不会改项目现有源配置
- 不把登录页、社媒时间线、纯网页新闻页算作当前可用源
- 若后续要真正接入新源，可直接复用报告里的推荐 `key / driver / schedule / tags`
