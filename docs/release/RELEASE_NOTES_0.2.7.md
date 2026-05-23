# 0.2.7 更新说明

## 本次重点
- 新增主链融合版 Agent HTML 采集能力：HTML 文档可在保留 target、revision、缓存与重提取能力的同时，并入统一 `raw_items -> discovery_items -> intel_events -> intel_alerts` 主链。
- 补齐 `agent-html` 管理接口与主链同步入口，支持目标页抓取、发现项查看、文档查看、重提取与 `mainline-sync`。
- 新增 HTML 主链相关测试，覆盖 API 行为与 HTML 数据映射进主链的关键回归。
- 更新 README 与配套文档，明确 RSS 优先、HTML 补洞、统一主链复用与后续维护边界。

## 兼容性
- 版本号已更新为 `0.2.7`。
- GitHub Releases 需要同步发布 `v0.2.7`，旧版本才会识别到更新。

## 备注
- 传统 RSS 工作流保持可用，HTML 作为补充输入，不替代稳定 RSS 源。
- HTML 专属缓存、文档 revision 与重提取能力继续保留，用于维护与排障。
- 分发包继续包含项目 `.venv`，保持 Windows 离线可安装。
