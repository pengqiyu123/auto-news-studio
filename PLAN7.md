# Auto News Studio AI 模型档位交互重构计划（参考本地 CC Switch 复审版）

## Summary

基于对本地 `projects/cc-switch` 的复审，这轮要修的不是“多加几个按钮”这么简单，而是把 AI 设置页改成和 `CC Switch` 一样的**实体驱动交互**：

- **卡片是操作对象**
- **编辑是明确动作**
- **测试是档位级动作**
- **路由引用档位，不直接引用 provider/model**
- **用户只看 3 个任务，不再看 5 个内部任务**

本轮固定按这套顺序重构页面：

1. **编辑模型**
2. **当前预置模型**
3. **任务路由**

任务固定为 3 个：

- `translation`：信息翻译
- `judgement`：信息候选判断
- `article`：写稿件

内部调用映射固定为：

- `translation` -> 事件翻译
- `judgement` -> 候选题判断
- `article` -> 大纲 / 摘要 / 正文 / 标题

研究依据固定来自本地参考，而不是空想：

- `projects/cc-switch/src/components/providers/ProviderCard.tsx`
- `projects/cc-switch/src/components/providers/ProviderActions.tsx`
- `projects/cc-switch/src/components/providers/EditProviderDialog.tsx`

---

## Key Changes

### 1. 页面信息架构重排

AI 设置页固定拆成 3 段，顺序不能变：

1. **编辑模型**
   - 这里放模型档位卡片列表 + 档位编辑器
   - 卡片是主入口，不再把“编辑能力”藏到页面右侧默认表单里

2. **当前预置模型**
   - 单独展示当前正在被系统默认继承的档位
   - 明确告诉用户：这是“默认档位”，不是“所有任务都只能跟它走”

3. **任务路由**
   - 只显示 `translation / judgement / article`
   - 每个任务选择“主档位 + 备用档位”
   - 路由选择对象固定为 `profile_id`

### 2. 模型档位卡片改成 CC Switch 式动作卡

每张档位卡片固定包含两层动作：

#### 主按钮
- `设为当前`
- `使用中`

规则固定：

- 当前档位显示 `使用中`，禁用
- 非当前但已配置可用档位显示 `设为当前`
- 未配置完整（缺 key）显示禁用态，并提示先补全配置

#### 图标动作区
每张卡片固定提供：

- `编辑`
- `复制`
- `测试`
- `删除`（仅自定义档位）

固定约束：

- `编辑` 是显式按钮，不能再靠“点卡片默认右侧改”
- `测试` 是卡片级动作，不再只放编辑区底部
- 预置档位不可删除，只能复制
- 删除前必须二次确认
- 图标按钮必须有 tooltip
- 卡片点击只做“选中”，不直接承担全部操作语义

视觉状态固定：

- 当前默认档位：强高亮
- 当前选中档位：次高亮
- 未配置 Key：弱化 + 状态标签
- 最近测试成功 / 失败：在卡片底部或角标显示最近结果

### 3. 编辑流改成“选中 + 编辑按钮进入编辑态”

保留当前页面内编辑，不照搬 CC Switch 的全屏弹窗，但交互语义固定对齐：

- 点卡片：只选中
- 点 `编辑`：进入编辑态，并聚焦右侧编辑器
- 编辑器顶部明确显示：
  - 档位名称
  - 是否预置 / 自定义
  - 当前是否启用
  - 最近测试结果

编辑器固定按钮组：

- `保存`
- `保存并测试`
- `设为当前`
- `取消编辑`

固定规则：

- `保存并测试` 先保存，再按当前档位执行连通性测试
- 当前档位可以继续编辑，但不会因为保存而自动覆盖所有任务路由
- 切换选中档位时，如果有未保存修改，必须先提示：
  - 保存修改
  - 放弃修改
  - 继续留在当前编辑对象

### 4. 配置结构改成“任务引用档位”，不再直接引用 provider/model

`profiles` 继续保留为唯一模型资产。

`tasks` 固定改为只保存：

- `task_key`
- `label`
- `primary_profile_id`
- `fallback_profile_id`
- `temperature`
- `max_tokens`
- `system_prompt`

不再让任务配置直接保存：

- `provider_key`
- `model_id`
- `fallback_provider_key`
- `fallback_model_id`

运行时固定由 `profile_id -> profile -> provider/base_url/api_key/model_id` 解析。

### 5. 任务路由只保留 3 行，并且只能选档位

任务路由区固定只显示：

- `信息翻译`
- `候选判断`
- `写稿件`

每行固定两列：

- 主档位
- 备用档位

固定约束：

- 下拉源来自已存在档位列表，不来自 `PROVIDER_REGISTRY`
- 可以选“跟随当前预置模型”作为显式默认项
- 不能再出现“服务商下拉 + 模型下拉”的裸路由方式
- 路由文案必须是产品语义，不出现 `outline/title/summary` 这些内部实现名

### 6. 测试能力改成档位级测试，不再是 provider 级测试

新增或替换为档位级测试接口：

- `POST /api/admin/llm/test-profile/{profile_id}`

测试行为固定：

- 使用该档位自己的完整配置测试
- 返回：
  - `ok`
  - `model`
  - `provider_key`
  - `latency_ms`
  - `error`

前端固定消费方式：

- 卡片 `测试` 按钮可直接触发
- 编辑器 `保存并测试` 也走同一接口
- 最近测试时间与结果写回该档位卡片

### 7. 旧 5 任务迁移到新 3 任务

旧配置迁移固定规则：

- `summary` 的翻译用途迁到 `translation`
- `judgement` 保持到 `judgement`
- `article / outline / title / summary(稿件摘要)` 统一收口到 `article`

迁移优先级固定：

1. `article`
2. `outline`
3. `title`
4. `summary`
5. `current_profile_id`

迁移后：

- state 中只保留 3 个任务
- 前端只渲染 3 个任务
- 旧 5 任务字段只做一次兼容读取，不再写回

---

## Public Interfaces / Types

### 类型调整
- `LLMTaskConfig`
  - 新增：
    - `primary_profile_id`
    - `fallback_profile_id`
  - 移除产品主语义中的：
    - `provider_key`
    - `model_id`
    - `fallback_provider_key`
    - `fallback_model_id`

### 接口调整
- `GET /api/admin/llm/config`
  - 返回 3 个任务的 profile-based 路由
- `PUT /api/admin/llm/config`
  - 只接受 3 个任务键
  - 以提交的任务路由为真值
- `POST /api/admin/llm/test-profile/{profile_id}`
  - 档位级测试接口
- 旧 `test/{provider_key}` 可保留短期兼容，但前端不再使用

---

## Test Plan

### 1. 页面结构
- 页面顺序固定为：编辑模型 -> 当前预置模型 -> 任务路由
- 不再出现 5 个任务路由行
- 不再出现基于 raw provider/model 的任务选择器

### 2. 卡片交互
- 每张卡片都有 `编辑 / 复制 / 测试 / 删除(自定义)` 按钮
- 当前档位显示 `使用中`
- 非当前可用档位显示 `设为当前`
- 预置档位不可删除
- 删除前有确认
- 图标按钮均有 tooltip

### 3. 编辑流
- 点卡片只选中
- 点 `编辑` 才进入编辑态
- 有未保存修改时切换档位会弹出处理提示
- `保存并测试` 可成功返回并更新测试结果展示

### 4. 路由行为
- `translation` 只影响事件翻译
- `judgement` 只影响候选判断
- `article` 同时影响大纲、摘要、正文、标题
- 路由选择对象始终是档位卡片，不是 provider/model

### 5. 迁移兼容
- 旧 5 任务配置启动后自动收口成 3 任务
- 旧数据不会导致前端崩溃
- 旧 state 中没有新字段时可按默认值工作

### 6. 测试与运行
- 档位卡片可直接测试
- 当前档位切换不影响已显式绑定任务的独立路由
- failover 仍可按主档位/备用档位工作
- 日志能看出实际命中的档位

---

## Assumptions

- 本轮只重构 AI 模型设置层，不改情报链、写稿 prompt、预警算法
- 当前项目是 Web 管理台，因此不照搬 CC Switch 的全屏弹窗，但保留它的“卡片动作优先”交互原则
- “编辑模型”仍使用当前页内编辑器，而不是新开独立页面
- 本轮不引入 CC Switch 的拖拽排序、配额统计、用量配置等扩展能力
- 用户最终可见任务固定为 3 个：`translation / judgement / article`
