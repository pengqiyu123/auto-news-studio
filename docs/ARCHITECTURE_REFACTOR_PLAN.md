# 项目文件夹架构优化计划

更新时间：2026-05-22

适用范围：`auto-news-studio`

## 1. 结论先说

这个项目确实有结构优化需求，但不适合按企业级后端那套分层去重构。

它的真实约束很明确：

1. 单用户、本地运行，不是 SaaS。
2. 主要持久化介质是 JSON，不是数据库。
3. 维护者少，目录过深会直接增加导航成本。
4. 当前已经有一条可行演进路径：`StoreCore + mixins`。

所以这次优化目标应该是：

1. 控制大文件继续膨胀。
2. 让运行产物、配置、状态文件各归其位。
3. 在不推倒现有结构的前提下，做浅层拆分。
4. 优先降低维护成本，而不是追求“架构完整度”。

## 2. 当前问题

### 2.1 真正需要处理的问题

后端大文件：

- `backend/app/publishers.py`：约 4078 行
- `backend/app/store_core.py`：约 2841 行
- `backend/app/store_core_state.py`：约 1327 行
- `backend/app/models.py`：约 1281 行
- `backend/app/briefing.py`：约 1120 行

前端大文件：

- `frontend/src/styles.css`：约 3870 行
- `frontend/src/types.ts`：约 949 行
- `frontend/src/app.tsx`：约 836 行
- `frontend/src/components/IntelOverviewPage.tsx`：约 855 行
- `frontend/src/components/LLMSettingsPanel.tsx`：约 743 行

目录问题：

1. `data/`、`backend/data/`、`runtime/`、`logs/` 职责有重叠。
2. 运行期调试产物较多，容易回流到源码附近。
3. 后端大量模块仍平铺在 `backend/app/` 根下。
4. 前端页面组件、复用组件、样式、类型定义有一部分过度集中。

### 2.2 不应该解决成什么样

不建议把当前项目重构成：

- `domain/`
- `infra/`
- `repository/`
- `service/`
- `schema/`

多层嵌套的大型企业结构。

原因不是这些模式“错”，而是它们和当前项目规模、持久化方式、维护方式不匹配。

## 3. 务实的目标结构

目标不是推翻现有结构，而是在现有基础上整理成更容易维护的浅层目录。

### 3.1 推荐目录

```text
auto-news-studio/
  backend/
    app/
      core/
      routes/
      services/
      sources/
      store_mixins/
      main.py
      store.py
      store_core.py
      store_core_state.py
      models.py
    tests/
  frontend/
    src/
      components/
      hooks/
      lib/
      navigation/
      styles/
      test/
      app.tsx
      main.tsx
      types.ts
  config/
  data/
  runtime/
    cache/
    browser/
    logs/
    temp/
  dist/
  docs/
  archive/
```

### 3.2 目录职责

- `backend/app/core/`
  放通用常量、路径、时间工具、基础帮助函数。

- `backend/app/services/`
  放已经明显具备独立职责、又不适合继续塞进 `store_core.py` 或 `publishers.py` 的服务模块。

- `backend/app/routes/`
  继续保留 API 路由入口，不额外分层。

- `backend/app/store_mixins/`
  继续作为主拆分方向，不推翻。

- `frontend/src/styles/`
  承接拆出来的基础样式文件。

- `runtime/`
  只放运行期产物，不放源码意义上的正式数据。

- `dist/`
  只放发布包。

## 4. 核心原则

### 4.1 延续现有演进方向

后端不推翻 `StoreCore + mixins`，而是继续沿这条路拆。

重点是：

1. 把 `store_core.py` 继续瘦身。
2. 把不属于核心状态协调的逻辑挪到 `services/`。
3. 让 `store.py` 继续扮演总装配入口。

### 4.2 浅层拆分优先

优先：

- 平铺小文件
- 少量目录
- 单层分组

不优先：

- 为了“架构好看”增加多级目录
- 为了套模式而引入 repository/facade/migrations 架子

### 4.3 行数只作为信号，不作为硬指标

不使用“超过 1200 行必须拆”的硬规则。

更合理的判断标准是：

1. 一个文件是否同时承担了 3 类以上职责。
2. 改一个功能时，是否总要在同一个超大文件里来回定位。
3. 是否已经难以为局部逻辑写测试。
4. 是否存在天然边界，拆出来后能提升可读性。

也就是说：

- 行数只是提醒
- 职责混杂才是拆分依据

## 5. 具体拆分建议

### 5.1 第一优先级：`publishers.py`

这是当前最值得先拆的文件。

建议不要拆成深层目录，而是拆成浅层平铺模块：

```text
backend/app/services/
  wechat_publisher.py
  douyin_publisher.py
  browser_profiles.py
  publish_artifacts.py
```

说明：

1. `wechat_publisher.py`
   放公众号相关流程、选择器、草稿箱、发表记录、编辑器填充。
2. `douyin_publisher.py`
   放抖音相关流程。
3. `browser_profiles.py`
   放浏览器路径、profile、锁、会话等管理逻辑。
4. `publish_artifacts.py`
   放截图、HTML、检查文本等调试证据输出。

如果拆分过程中发现 `wechat_publisher.py` 仍然太大，再在文件内部用 class 或 section 拆，而不是一开始就拆成 6 个文件。

### 5.2 第二优先级：`store_core.py`

当前方向不是“换架构”，而是继续瘦身。

建议策略：

1. 保留 `store_core.py` 作为核心状态协调层。
2. 把明显独立的流程服务提到 `services/`。
3. 把通用基础工具提到 `core/`。
4. 把 JSON 读写、路径常量、备份等基础能力从业务逻辑中抽离。

建议新增但保持浅层：

```text
backend/app/core/
  paths.py
  time_utils.py
  constants.py

backend/app/services/
  runtime_cycle.py
  source_collection.py
  update_check.py
```

注意：

- 这里不是要把 `store_core.py` 清空
- 而是只把天然独立的一块块职责移出去

### 5.3 第三优先级：`models.py`

这里也不建议一次性切成一大片子包。

更务实的方式是按用途拆成少量平铺文件：

```text
backend/app/
  models_runtime.py
  models_intel.py
  models_publish.py
  models_settings.py
```

或者如果你希望更保守，也可以先只拆出：

- `models_publish.py`
- `models_intel.py`

把剩下部分留在 `models.py`。

### 5.4 第四优先级：前端样式和入口

前端不建议做完整 `features/*` 重构。

更合适的方案是：

```text
frontend/src/styles/
  tokens.css
  base.css
  layout.css
```

然后：

1. `styles.css` 保留为聚合入口。
2. 只把设计变量、基础样式、布局样式拆出去。
3. 页面级样式可以先继续留在主样式文件，或按需逐步抽。

### 5.5 第五优先级：`app.tsx` 和 `types.ts`

不做大规模 feature 化。

更务实的拆法：

`app.tsx`：

- 把 tab 配置
- 顶层数据加载编排
- UI 壳层逻辑

拆成 2 到 3 个辅助文件即可，不需要引入路由架构。

`types.ts`：

- 只把明显独立且引用密集的一组类型拆出去
- 不追求所有类型都模块化

可选做法：

```text
frontend/src/
  types.ts
  types_intel.ts
  types_publish.ts
```

## 6. 目录层面的直接优化

这部分收益高、风险低，建议优先做。

### 6.1 统一状态与运行产物边界

建议明确：

1. `data/`
   放正式状态文件和用户可恢复数据。
2. `runtime/cache/`
   放 agent HTML cache 等缓存。
3. `runtime/browser/`
   放浏览器 profile。
4. `runtime/logs/`
   放运行日志。
5. `runtime/temp/`
   放调试截图、检查文本、临时导出。
6. `dist/`
   放发布产物。

### 6.2 重点处理的冲突点

当前优先梳理：

1. `data/state.json` 与 `backend/data/state.json` 二选一，避免双状态入口。
2. `backend/data/artifacts/` 迁到 `runtime/temp/` 或 `runtime/cache/`。
3. `runtime/release/` 迁到 `dist/`。
4. 零散日志统一到 `runtime/logs/`。

## 7. 分阶段执行计划

### 阶段 1：只做目录边界整理

目标：

- 不改业务逻辑，只清理“放错地方的东西”。

任务：

1. 统一状态文件主入口。
2. 迁移运行时调试产物。
3. 统一日志目录。
4. 建立 `dist/`。
5. 调整 `.gitignore`。
6. 新写入统一走新目录，旧状态文件保留兼容读取，不要求一次性搬空所有历史运行文件。
7. 若发现多个 `state.json` 内容分叉，停止自动清理，只输出摘要并人工确认主状态文件。

验收标准：

- 源码目录附近不再持续产生运行垃圾。

当前状态：

- 已完成
- 新状态主入口已收敛到 `data/state/state.json`
- 旧 `data/state.json` 与 `backend/data/state.json` 已归档到 `runtime/migration-archive/`
- Agent HTML 缓存、旧日志、发布产物、发布调试产物已迁到新目录
- 新后端启动后已验证健康接口正常，且不会重新生成旧状态文件

### 阶段 2：建立浅层基础目录

目标：

- 建好 `core/` 和 `services/`，但不大改现有模块关系。

任务：

1. 新建 `backend/app/core/`
2. 新建 `backend/app/services/`
3. 把最基础的通用工具挪到 `core/`
4. 把最独立的流程逻辑挪到 `services/`

验收标准：

- 新代码不再默认继续堆到 `backend/app/` 根目录。

当前策略：

- 这一步与阶段 3 合并推进
- `backend/app/publishers/` 已存在包裹层，但仍大量代理到旧 `publishers.py`
- 下一步优先把低耦合的浏览器基础能力改成真实模块实现，而不是继续依赖 `_legacy`
- 当前已完成：
  - `frontend/src/screens/` 已建立 11 个界面目录，`app.tsx` 已从 `screens/*/page`、`screens/*/state` 取页面与状态入口
  - `backend/app/features/` 已建立与界面一一对应的目录骨架
  - `routes/intel.py`、`wechat.py`、`browser.py`、`settings.py`、`runtime.py` 已开始从 `features/*` 取实现
  - `browser_base.py` 已接管路径、selector、browser state、artifact 等基础 helper
  - `wechat.py` 已接管有测试覆盖的编辑器 helper、单标签页约束、作者裁剪、appmsg id 解析、发布设置 helper
  - `wechat.py` 已接管 `inspect_wechat_draft_box` 及其最小导航/抓取闭环
  - `wechat.py` 已接管 `inspect_wechat_publish_history` 的外层会话与导航流程，底层列表抓取暂复用 legacy 实现
  - `wechat.py` 已接管 `inspect_wechat_session` 与 `launch_wechat_dashboard`
  - `wechat.py` 已接管 `inspect_wechat_publish_history_with_overview`
  - `wechat.py` 已接管 `delete_wechat_remote_draft`
  - `douyin.py` 已接管标题/摘要裁剪 helper

### 阶段 3：拆 `publishers.py`

目标：

- 把最重的发布流程从一个超级文件拆成少量平铺模块。

任务：

1. 先拆微信与抖音
2. 再拆浏览器管理
3. 最后拆调试产物输出

验收标准：

- `publishers.py` 不再是 4000+ 行总包。

当前执行顺序：

1. 先拆浏览器基础能力与通用 helper
2. 再拆微信发布链
3. 再拆抖音发布链
4. 最后处理仍残留在旧文件中的调试与检查能力

当前下一步：

- 先把 `draft_box`、`publish_history`、`settings` 三组界面从薄壳推进成真实承载层
- 再继续完成微信远端交互链路剩余主链
- 已完成：`inspect_wechat_draft_box`
- 已完成：`inspect_wechat_publish_history`
- 已完成：`inspect_wechat_session`
- 已完成：`launch_wechat_dashboard`
- 已完成：`inspect_wechat_publish_history_with_overview`
- 已完成：`delete_wechat_remote_draft`
- 当前进行中：`run_browser_action`
- 后续优先级：抖音页面链路 `launch_douyin_dashboard` -> `inspect_douyin_session` -> `open_douyin_article_publish` -> `inspect_douyin_article_structure` -> `fill_douyin_article_from_brief`

### 阶段 4：继续瘦身 `store_core.py`

目标：

- 继续沿 mixin 路线演进，而不是另起炉灶。

任务：

1. 把基础工具继续移到 `core/`
2. 把独立流程移到 `services/`
3. 保持 `store_core.py` 只做核心协调

验收标准：

- 改某一块流程时，不必每次都深入 `store_core.py` 巨型文件。

### 阶段 5：处理前端两个最大痛点

目标：

- 控制样式文件和顶层入口文件继续膨胀。

任务：

1. 拆 `styles.css`
2. 整理 `app.tsx`
3. 按需拆一部分 `types.ts`

验收标准：

- 前端结构更清晰，但没有引入过重的新组织方式。

## 8. 本次重构不做的事

为了避免过度设计，明确以下内容不在本轮范围内：

1. 不引入 repository 模式。
2. 不引入完整 service/domain/infra 多层架构。
3. 不做数据库化改造。
4. 不做前端完整 feature-based 重写。
5. 不因为行数达标而机械拆文件。

## 9. 执行时的判断标准

每次拆分前，都问 3 个问题：

1. 这块逻辑是否天然独立？
2. 拆出来后是否更容易找、更容易测、更容易改？
3. 拆分后的文件数量，是否仍然符合一个人维护的导航习惯？

如果答案不是明确的“是”，就先不拆。

## 10. 推荐的第一批动作

如果现在就开始做，建议顺序如下：

1. 统一 `data/`、`runtime/`、`dist/` 的职责。
2. 优先拆 `publishers.py` 为：
   - `wechat_publisher.py`
   - `douyin_publisher.py`
   - `browser_profiles.py`
   - `publish_artifacts.py`
3. 再建立和补齐 `backend/app/core/` 与 `backend/app/services/`。
4. 继续瘦身 `store_core.py`，但不改现有 `mixin` 大方向。
5. 把 `styles.css` 先拆成：
   - `tokens.css`
   - `base.css`
   - `layout.css`

这套顺序比较贴合当前项目：改动集中、收益直接、不会把工具项目重构成企业平台。
