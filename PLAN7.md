# Auto News Studio AI 模型层下一阶段计划（基于 GLM 修复后的复审版）

## Summary

这次复审结论可以分成两半：

### 已经修好的
GLM 这轮修复，确实把**地基问题**补上了：

- `update_llm_config()` 不再把前端传入的任务路由直接覆盖掉
- `providers` 会带上任务主备引用到的 provider，跨 provider fallback 能跑起来
- `_upgrade_state()` 不再每次启动都把保存好的 `tasks/providers` 重建掉
- 前端切换当前档位、测试档位时，不再顺手把任务路由重置

这部分现在已经从“错的”变成“基本可用”。

### 还没做的
但你前面骂得那几个点，复审后依然成立：

- UI 还是 **5 个任务**
- 路由还是 **raw provider/model**
- 卡片还是没有做成 `CC Switch` 那种**显式动作卡**
- 事件翻译仍借用 `summary` 任务，产品语义没收口
- “编辑模型 -> 当前预置模型 -> 任务路由”的信息架构还没真正完成

所以接下来不该再继续修地基，而是该进入**产品层重构**。

---

## Key Changes

### 1. 冻结已完成的底层，不再返工

本轮后续开发固定建立在以下现实上：

- 继续保留 GLM 已修好的 `tasks` 持久化逻辑
- 继续保留现有 primary/fallback failover 逻辑
- 继续保留现有 `profiles + providers + tasks` 状态结构，先在这个基础上重构产品层
- 本阶段不回退、不重写已工作的翻译链和 fallback 基础能力

固定要求：

- 任何新改动都不能重新引入“切换当前档位导致任务路由丢失”
- 任何新改动都不能让 `_upgrade_state()` 再次覆盖已保存任务
- 任何 UI 调整都必须兼容当前已存在的 `provider_key/model_id/fallback_*` 任务结构，直到下一步 schema 迁移真正落地

### 2. 先做交互重构，再做 schema 收口

下一阶段顺序固定改成：

1. **先重构页面交互**
2. **再做 5 任务 -> 3 任务收口**
3. **最后再做 profile-based 路由 schema**

原因固定：

- 现在用户最直接的不满，是“抄 `CC Switch` 都没抄对”，这是交互层问题
- 底层虽然还没优雅，但已经能工作；用户痛感最大的是“不会用、不好用、卡片没动作”
- 如果先动 schema，再动 UI，返工面会更大

### 3. 第一阶段：把模型档位卡片做成 CC Switch 式动作卡

参考本地：

- `projects/cc-switch/src/components/providers/ProviderCard.tsx`
- `projects/cc-switch/src/components/providers/ProviderActions.tsx`
- `projects/cc-switch/src/components/providers/EditProviderDialog.tsx`

固定改法：

#### 卡片必须具备显式动作
每张模型档位卡固定提供：

- 主按钮：
  - `设为当前`
  - `使用中`
- 图标按钮：
  - `编辑`
  - `复制`
  - `测试`
  - `删除`（仅自定义档位）

固定规则：

- 卡片点击只负责“选中”
- `编辑` 必须是显式按钮，不再靠“点卡片后右边改”
- `测试` 必须是卡片级动作，不只在右侧编辑区
- 删除前必须确认
- 所有图标按钮必须有 tooltip
- 当前档位禁删
- 预制档位不可删，只能复制

#### 页面结构固定为三块
顺序不能变：

1. `编辑模型`
2. `当前预置模型`
3. `任务路由`

当前页面虽然已经有这几个概念，但结构仍混杂，需要明确分段，不再让“统计卡 + 当前主模型 + 卡片 + 编辑器 + 任务路由”揉成一团。

#### 编辑流固定
- 点卡片：选中
- 点 `编辑`：进入编辑态
- 编辑器按钮固定为：
  - `保存`
  - `保存并测试`
  - `设为当前`
  - `取消编辑`
- 切换选中档位前，如有未保存修改，必须提示：
  - 保存
  - 放弃
  - 取消切换

### 4. 第二阶段：把 5 个任务收口成 3 个产品任务

用户可见任务固定收口为：

- `translation`
- `judgement`
- `article`

内部映射固定为：

- `translation`
  - 事件翻译
  - 现有 `intel_pipeline.py` 里的 `generate("summary", ...)` 改为真正的翻译任务键

- `judgement`
  - 候选题判断
  - 保留当前 `store.py` 的候选题初判逻辑

- `article`
  - 统一承接：
    - `outline`
    - 稿件摘要
    - `article`
    - `title`

固定约束：

- 用户界面只显示 3 个任务
- 后端运行时允许多个 prompt，但路由维度只认 3 个任务
- 不再让用户看到 `outline/title/summary` 这些内部拆分名

### 5. 第三阶段：路由从 provider/model 改成 profile-based

在第二阶段稳定后，再推进 schema 收口：

#### `LLMTaskConfig` 改成
- `task_key`
- `label`
- `primary_profile_id`
- `fallback_profile_id`
- `temperature`
- `max_tokens`
- `system_prompt`

#### 运行时解析改成
- 任务先找到 `profile_id`
- 再从 `profile` 解析出：
  - provider_key
  - base_url
  - api_key
  - model_id

这样任务路由真正引用“模型档位”，而不是裸 provider/model。

固定要求：

- 迁移时兼容旧字段读取
- 新保存统一只写 profile-based 字段
- 旧 `provider_key/model_id` 路由只保留过渡期兼容，不再作为主配置入口

---

## Public Interfaces / Types

### 第一阶段
- 不改后端接口 shape
- 只调整前端 `LLMSettingsPanel` 的交互结构与按钮体系

### 第二阶段
- 前端任务列表从 5 行改为 3 行
- 后端允许继续兼容 5 任务旧 state，但返回给前端时需投影成 3 任务视图，或在迁移时直接写回 3 任务

### 第三阶段
- `LLMTaskConfig`
  - 新增：
    - `primary_profile_id`
    - `fallback_profile_id`
  - 废弃：
    - `provider_key`
    - `model_id`
    - `fallback_provider_key`
    - `fallback_model_id`

- 新增或替换测试接口：
  - `POST /api/admin/llm/test-profile/{profile_id}`

---

## Test Plan

### 1. GLM 已修复部分不回退
- 保存任务路由后，刷新页面不丢
- 重启后端后，任务路由不丢
- 当前档位切换后，任务路由仍保持原值
- fallback provider 仍能继续命中

### 2. 卡片交互
- 每张卡片都有 `编辑 / 复制 / 测试 / 删除(自定义)` 按钮
- `编辑` 为显式动作，不靠点卡片隐式进入
- `测试` 可直接从卡片触发
- 删除前必须确认
- 图标按钮均有 tooltip

### 3. 页面结构
- 页面清晰分成：编辑模型 / 当前预置模型 / 任务路由
- 不再出现“按钮和状态混在一起、靠猜才能知道怎么用”的情况

### 4. 三任务收口
- 前端只显示 `translation / judgement / article`
- 事件翻译单独受 `translation` 控制
- 候选判断只受 `judgement` 控制
- 大纲/摘要/正文/标题统一受 `article` 控制

### 5. profile-based 路由
- 任务可引用主档位和备用档位
- 档位删除时，若被任务引用，必须先阻止或提示替换
- 测试档位接口按 `profile_id` 工作，不再依赖 provider key

---

## Assumptions

- GLM 这轮底层修复视为已验收通过，不在下一阶段重复返工
- 下一阶段优先解决“交互不对、任务过多、路由语义错位”，不是继续补 fallback 细节
- 第一阶段先不改后端 schema，避免把“交互修复”和“存储迁移”缠在一起
- 真正的终态仍然是“任务引用模型档位”，但要分阶段落地
