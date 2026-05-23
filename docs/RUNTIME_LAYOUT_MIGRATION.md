# 运行目录迁移说明

适用脚本：`scripts/migrate_runtime_layout.ps1`

## 目标

把以下历史运行目录整理到新结构：

- `runtime/agent_html_cache` -> `runtime/cache/agent_html`
- `runtime/*.log` -> `runtime/logs/`
- `runtime/release/*` -> `dist/windows/`
- `backend/data/artifacts` -> `runtime/temp/publish_artifacts`
- `logs/*.log` -> `runtime/logs/`

同时检查多个 `state.json` 是否发生分叉。

## 执行前提

执行前必须先停止所有项目后端进程。

尤其要避免以下情况：

1. 同时存在不同 Python 环境启动的 `uvicorn`
2. 旧进程仍在写 `data/state.json`
3. 新进程已经开始写 `data/state/state.json`

如果不先停服，就可能在迁移过程中继续写入，导致状态分叉扩大。

## 建议步骤

1. 执行 `stop.bat`
2. 手动确认 8000 端口已释放
3. 执行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/migrate_runtime_layout.ps1
```

## 脚本行为

脚本会：

1. 生成多个 `state.json` 的摘要
2. 比较它们的哈希
3. 如果内容一致：
   - 归档旧 `data/state.json`
   - 归档旧 `backend/data/state.json`
4. 如果内容不一致：
   - 不自动删除旧状态文件
   - 只输出摘要到 `runtime/migration-archive/<timestamp>/state-summary.json`
5. 迁移低风险目录和日志文件

## 当前注意事项

如果 `data/state/state.json` 和 `data/state.json` 内容不同，不要直接删除其中任何一个。

先根据以下字段确认谁才是主状态文件：

1. `runtime.last_collect_at`
2. `app_meta.last_update_check.checked_at`
3. `raw_items` 数量
4. `briefs` 数量
5. 文件最后修改时间

确认后，再决定是否把另一个归档。
