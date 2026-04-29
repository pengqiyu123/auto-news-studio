# Auto News Studio `PLAN12`：CC-Switch 一等公民接入计划

## Summary

本轮目标是让 CC-Switch 成为项目里的**一等公民模型配置中心**，不是“导入一下名字和 key”，而是真正把 CC-Switch 里已经定义好的协议语义带进来并跑通。

固定目标：

- 修复“HTML 首页也被测成成功”的假绿问题
- 不再把 CC profile 压扁成只有 `base_url + api_key + model_id`
- 按 CC-Switch 自身语义支持 4 种格式：
  - `openai_chat`
  - `openai_responses`
  - `anthropic`
  - `gemini_native`
- 运行时与测试链都按已验证格式工作，避免“测试通过但写稿不能用”
- 保持当前产品心智不变：
  - 左侧模型卡片不改
  - 用户仍只配置 `当前默认模型 + 备用模型`
  - AI 仍只服务稿件生成

固定设计原则：

- **不新增 repo 自己的 protocol_family 抽象**
- **直接复用 CC-Switch 已有语义**
- **UI 必须说真话，不能把连接探活当作写稿可用**

---

## Key Changes

### 1. CC 导入改为“保真导入”，不再压扁

在 `cc_switch_bridge.py` 导入 CC-Switch provider 时，除现有字段外，固定保留以下 CC 元数据：

- `cc_app_type`
- `cc_api_format`
- `cc_is_full_url`
- `cc_endpoint_auto_select`
- `cc_endpoint_candidates`
- `cc_base_url_raw`
- `cc_last_verified_endpoint`
- `cc_last_verified_format`
- `cc_last_verified_model`
- `cc_probe_status`
- `cc_probe_message`

固定规则：

- 从 `providers.meta` 读取：
  - `apiFormat`
  - `isFullUrl`
  - `endpointAutoSelect`
  - `usage_script.baseUrl`
- 从 `provider_endpoints` 读取候选端点列表
- `settings_config` 只继续提取运行所需的 key/base/model，不整块原样持久化
- `cc_endpoint_candidates` 需去重并保持稳定顺序
- 旧 profile 缺少这些字段时按空值兼容，不影响启动

### 2. 新增 CC 端点解析器，按格式和 URL 真实构造请求

后端新增统一 resolver，固定输入为：

- profile 原始信息
- `cc_api_format`
- `cc_is_full_url`
- `cc_endpoint_auto_select`
- `cc_endpoint_candidates`
- `cc_base_url_raw`
- `cc_last_verified_*`

固定候选顺序：

1. `cc_last_verified_endpoint`
2. `cc_endpoint_candidates`
3. `cc_base_url_raw`
4. `usage_script.baseUrl` 兜底

固定 URL 归一化规则：

- `isFullUrl = true` 时，不再拼接协议路径
- `isFullUrl = false` 时，按 `apiFormat` 补目标路径
- 已经是完整消息端点或 responses 端点时，不重复拼接
- 兼容 CC-Switch 已有的常见兼容后缀处理思路，例如：
  - `/api/anthropic`
  - `/apps/anthropic`
  - `/anthropic`
  - `/api/coding`

固定格式解析规则：

- `openai_chat` -> `/v1/chat/completions`
- `openai_responses` -> `/v1/responses`
- `anthropic` -> `/v1/messages` 或已给定完整 messages URL
- `gemini_native` -> Gemini 原生 `generateContent` 入口

固定降级规则：

- 若 `endpointAutoSelect = false`：
  - 只按声明格式尝试
  - 失败即返回明确错误
- 若 `endpointAutoSelect = true`：
  - 先试声明格式
  - 再按候选格式顺序自动探测
- `gemini_native` 不自动降级为 OpenAI/Anthropic 格式

### 3. 测试链重写：测试真实协议，不再把 HTML 当成功

`llm.py` 里的测试能力改为按 resolved format 分流，不再统一使用 `chat.completions.create(...)`。

固定测试行为：

- `openai_chat`：走 OpenAI SDK `chat.completions`
- `openai_responses`：走 OpenAI SDK `responses`
- `anthropic`：走原生 HTTP `messages`
- `gemini_native`：走原生 HTTP `generateContent`

固定错误判定：

- 返回 HTML 文本一律判失败
- 需要把这类结果标记为 `html_homepage`
- 连接失败、认证失败、模型不存在、协议不匹配分别明确分类

固定模型处理：

- profile 显式有 model 时优先用它
- OpenAI 风格且 model 为空时：
  - 可尝试模型发现
  - 发现不到则返回 `model_missing`
  - 不再盲猜“default 成功就算可用”
- `anthropic / gemini_native` 不盲猜默认模型

测试成功后固定回写：

- `cc_last_verified_endpoint`
- `cc_last_verified_format`
- `cc_last_verified_model`
- `cc_probe_status = verified`
- `cc_probe_message`

测试失败后固定回写：

- `cc_probe_status`
- `cc_probe_message`
- 保留上次成功验证结果，除非用户主动重新覆盖

### 4. 运行时生成链支持多格式，避免“测通不能写”

稿件生成链不能再假设“所有 provider 都是 OpenAI Chat”。

固定运行时分流：

- `openai_chat`：继续走现有 chat completions
- `openai_responses`：走 responses API
- `anthropic`：走 messages API
- `gemini_native`：走 generateContent

固定运行顺序：

- 当前默认模型先尝试：
  1. 已验证 endpoint/format/model
  2. 若允许 auto-select，再试 resolver 的其他候选
- 当前默认模型彻底失败后，才进入备用模型
- 主备切换语义保持不变，但切换单位从“provider key”升级为“已解析可用目标”

固定约束：

- 若 profile 只有“测试通过但仅验证了连接、不具备写稿路径”，UI 不能把它标成可用于稿件
- 运行时错误必须保留明确原因：
  - 认证失败
  - 协议不匹配
  - 模型缺失
  - HTML 主页
  - 端点不可达

### 5. 设置页与状态表达：卡片不动，但状态必须更真实

`LLMSettingsPanel` 左侧模型卡片区域保持原样，不改视觉结构。

右侧和测试反馈固定增强为：

- 显示 CC 来源信息：
  - `Claude / Codex / Gemini`
  - 声明格式
  - 是否完整 URL
  - 是否自动选端点
- 显示 probe 状态：
  - `已验证`
  - `返回首页`
  - `认证失败`
  - `协议不匹配`
  - `缺少模型`
  - `连接失败`
- 测试结果文案要明确说明：
  - 是“可连接”
  - 还是“可用于稿件生成”
- 允许保存未验证的 CC profile
- 但当未验证 profile 被设为当前默认模型时，页面需明确提示存在运行风险

固定产品约束：

- 不新增任务路由 UI
- 不改“默认模型 + 备用模型”心智
- 不把协议细节堆成面向小白的技术文档式说明

---

## Public Interfaces / Types

### 后端类型扩展
扩展 `LLMProfileConfig`：

- `cc_app_type?: string`
- `cc_api_format?: "openai_chat" | "openai_responses" | "anthropic" | "gemini_native" | null`
- `cc_is_full_url?: boolean`
- `cc_endpoint_auto_select?: boolean`
- `cc_endpoint_candidates?: string[]`
- `cc_base_url_raw?: string`
- `cc_last_verified_endpoint?: string | null`
- `cc_last_verified_format?: string | null`
- `cc_last_verified_model?: string | null`
- `cc_probe_status?: string | null`
- `cc_probe_message?: string | null`

扩展 `LLMTestResult`：

- `probe_status`
- `probe_message`
- `resolved_endpoint`
- `resolved_format`
- `resolved_model`
- `supports_generation`

### 前端类型扩展
同步 `types.ts` 中的 `LLMProfile` / `LLMTestResult` 结构，按加法兼容处理。

### 运行时内部
保留现有 `current_profile_id / fallback_profile_id` 结构，不恢复任务路由。  
运行时 task 仍只合成 `article`，但其底层调用改为多格式分流。

---

## Test Plan

### 1. 导入与兼容
- 从 CC-Switch 导入 profile 后，能看到 `apiFormat / isFullUrl / endpointAutoSelect / endpoint candidates`
- 旧 state 中没有这些字段时可正常启动
- 非 CC profile 不受影响

### 2. HTML 假绿修复
- `https://www.fucheers.top` 这类返回首页 HTML 的端点必须判失败
- UI 不再显示“测试成功”
- probe 状态显示为 `返回首页` 或等价错误态

### 3. 多格式探测
- `openai_chat` profile 能通过 chat completions 测通
- `openai_responses` profile 能通过 responses 测通
- `anthropic` profile 能通过 messages 测通
- `gemini_native` profile 能通过 Gemini 原生接口测通
- `endpointAutoSelect=false` 时不自动换格式
- `endpointAutoSelect=true` 时会尝试候选格式

### 4. 写稿运行时
- 当前默认模型为 OpenAI Chat 型 CC profile 时，可正常生成稿件
- 当前默认模型为 Responses 型 CC profile 时，可正常生成稿件
- 当前默认模型为 Anthropic 型 CC profile 时，可正常生成稿件
- 当前默认模型为 Gemini 型 CC profile 时，可正常生成稿件
- 主模型失败时，备用模型可按现有规则接管
- 不再出现“测试通过但生成失败只是因为协议不对”

### 5. 回归
- NVIDIA / SiliconFlow / OpenAI 等原生 profile 测试与生成不回退
- 左侧模型卡片外观和交互不变
- 设置页仍只保留 `当前默认模型 + 备用模型`
- 前端构建、后端编译通过

### 6. 本机重点样本
至少验证以下真实样本的导入与测试反馈：

- `Codex 直连中转`
- `小熊API`
- `Fucheers`
- `MIMO`
- `Zhipu GLM`
- `SiliconFlow`
- `GLM`
- `glm-4.7-flash`

---

## Assumptions

- 本轮不改变“AI 只服务稿件生成”的产品边界
- 本轮不恢复任务路由配置
- `CC-Switch` 是长期配置中心，不按当前本机少数中转站行为做缩水设计
- `provider_endpoints`、`meta.apiFormat`、`meta.isFullUrl`、`meta.endpointAutoSelect` 都视为真实配置来源
- 若某 profile 只能验证连接但未完成写稿能力验证，UI 必须明确区分，不允许假装“完全可用”
