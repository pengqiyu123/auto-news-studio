# Auto News Studio 代码重构计划（PLAN8）

## Summary

当前代码库存在严重的文件臃肿问题，违背项目维护规范：

| 文件 | 当前行数 | 建议上限 |
|------|----------|----------|
| `store.py` | **4970** | 800 |
| `models.py` | 994 | 800 |
| `LLMSettingsPanel.tsx` | 770 | 800 |
| `types.ts` | 745 | 800 |

`store.py` 接近 5000 行，是最大的问题。需要按功能领域拆分成多个模块，每个模块职责单一。

---

## 现状分析

### store.py (4970 行)

当前职责：
- JSON 文件读写和状态管理
- LLM 配置管理（profiles、providers、tasks）
- 自动化模式和运行时控制
- 候选题、Draft、Publish 任务管理
- WeChat 频道和浏览器会话管理
- 实体观察列表管理
- 情报事件/预警状态重建
- 大量辅助函数

### models.py (994 行)

当前职责：
- 所有 Pydantic 数据模型定义
- 40+ 个模型类

### LLMSettingsPanel.tsx (770 行)

当前职责：
- AI 模型设置完整 UI
- 档位列表、编辑器、测试功能
- 任务路由配置 UI

---

## 拆分策略

### 1. store.py 拆分

按功能领域拆分成 8 个模块：

#### `store_base.py` (~200 行)
- 基础状态读写（`_read`、`_write`、`_upgrade_state`）
- 基础日志（`_append_log`）
- 状态文件路径常量

#### `store_llm.py` (~400 行)
- `get_llm_config()`
- `update_llm_config()`
- `test_llm_provider()`
- `build_provider_from_profile()`
- `build_tasks_from_profile()`
- `merge_llm_profiles()`
- `default_llm_state()`

#### `store_runtime.py` (~400 行)
- 运行时状态管理
- `start_runtime()`
- `stop_runtime()`
- `get_runtime_status()`
- 自动化周期控制

#### `store_automation.py` (~500 行)
- 自动化模式管理
- `get_automation_modes()`
- `update_automation_plan()`
- 模式定义常量

#### `store_intel.py` (~400 行)
- 情报相关状态管理
- `_rebuild_intel_for_state()`
- `list_intel_events()`
- `list_intel_alerts()`
- 实体观察列表

#### `store_drafts.py` (~400 行)
- Draft 草稿管理
- `list_drafts()`
- `create_draft()`
- `update_draft()`
- `delete_draft()`

#### `store_publish.py` (~400 行)
- 发布任务管理
- `list_publish_tasks()`
- `create_publish_task()`
- `sync_wechat_drafts()`
- 浏览器会话管理

#### `store_channels.py` (~300 行)
- 渠道配置管理
- WeChat 渠道设置
- 频道相关配置

### 2. models.py 拆分

按领域拆分成 4 个模块：

#### `models_base.py` (~300 行)
- BaseModel 配置
- 基础类型定义

#### `models_intel.py` (~300 行)
- IntelEvent、IntelAlert
- DiscoveryItem、RawItem
- 情报相关模型

#### `models_draft.py` (~300 行)
- DraftItem
- PublishTask
- 写稿相关模型

#### `models_llm.py` (~200 行)
- LLMConfig、LLMTaskConfig
- LLMProfileConfig
- LLM 相关模型

### 3. 入口文件保持不变

- `store.py` 变成导入入口：`from .store_base import StudioStore`（保留类定义在 store_base）
- 或者创建 `__init__.py` 统一导出

---

## 实施顺序

### Phase 1: 创建 store_llm.py
1. 复制 `build_provider_from_profile` 到新文件
2. 复制 `build_tasks_from_profile` 到新文件
3. 复制 `merge_llm_profiles` 到新文件
4. 复制 `default_llm_state` 到新文件
5. 复制 `get_llm_config`、`update_llm_config`、`test_llm_provider` 到新文件
6. 在 store.py 中删除已移动的函数，保留导入

### Phase 2: 创建 models_llm.py
1. 复制 LLM 相关模型到新文件
2. 在 models.py 中删除已移动的模型
3. 导入统一处理

### Phase 3: 创建 store_runtime.py
1. 运行时相关函数迁移
2. 保持 store.py 入口不变

### Phase 4: 创建剩余模块
1. store_intel.py
2. store_drafts.py
3. store_publish.py
4. store_channels.py
5. store_base.py

### Phase 5: 验证
1. 编译检查
2. API 测试
3. 功能回归测试

---

## 注意事项

1. **保持向后兼容**：`StudioStore` 类结构不变，只是内部实现分散到多个文件
2. **导入路径**：所有模块间导入使用相对导入
3. **类型注解**：保持类型注解，便于 IDE 支持
4. **测试覆盖**：每个拆分的模块单独验证
5. **文档注释**：每个拆分的函数添加简洁注释

---

## 风险控制

- 拆分前确保所有代码有编译检查
- 每拆分一个模块，立即验证相关 API
- 保留 git 分支，便于回滚
- 拆分后总行数应该降低到合理范围

---

## 验收标准

1. `store.py` 行数降到 800 以下
2. `models.py` 行数降到 800 以下
3. 所有 API 端点功能正常
4. 编译检查无错误
5. 前端能正常加载和保存配置
