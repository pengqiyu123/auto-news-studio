# 发布与更新流程

## 目标

每次上传 GitHub 时，版本号、更新说明、分发包、GitHub Release、应用内更新提示要保持一致。

## 已验证版本

- `v0.2.3` 已按本流程完成发布
- 旧版本启动后可通过 GitHub Releases 检测到更新
- 应用内首页与设置页会显示更新横幅 / 红点

## 标准流程

1. 修改代码并完成测试
2. 更新版本号
   - `version.json`
   - `frontend/package.json`
   - 如有默认版本常量，一并更新
3. 编写本次更新说明
   - 新建 `RELEASE_NOTES_x.y.z.md`
4. 构建验证
   - `.\.venv\Scripts\python.exe -m pytest backend/tests/test_admin_pagination.py backend/tests/test_intel_pipeline.py`
   - `.\.venv\Scripts\python.exe -m compileall backend/app`
   - `cd frontend && npm run build`
   - `cd frontend && npx vitest --run`
5. 生成 Windows 分发包
   - 运行 `powershell -ExecutionPolicy Bypass -File scripts/build_release.ps1`
   - 产物位于 `runtime/release/auto-news-studio-windows.zip`
6. 提交并推送 GitHub
7. 打 Git tag
   - 例如：`git tag v0.2.3`
   - `git push origin v0.2.3`
8. 在 GitHub 仓库发布 Release
   - Tag: `v0.2.3`
   - Title: `v0.2.3`
   - Body: 使用 `RELEASE_NOTES_0.2.3.md`
9. 启动应用检查
   - 首页出现更新横幅
   - 设置页显示更新状态
   - 侧栏“设置”出现红点

## 分发包约定

- 分发包默认是 offline-ready
- `scripts/build_release.ps1` 会把项目 `.venv` 一起打包进去
- 目标是让 Windows 用户解压后直接安装、直接启动
- 正式发布前应先生成并检查分发包，再执行 GitHub Release

## 本次实测结果

- 仅推送 `master` 不足以触发旧版更新提示
- 必须同步创建并发布 GitHub Release
- 旧版更新检测读取的是 `releases/latest`
- `RELEASE_NOTES_x.y.z.md` 可以直接作为 Release 正文
- 如果本地已经存在旧 tag（例如 `v0.2.4`），新的上传批次必须升级版本号，不能复用旧 tag
- 当前机器若未安装 `gh` 且没有 GitHub token，则只能先完成 `push + tag + 分发包`，再到 GitHub 页面手动发布 Release

## 为什么旧版本有时检测不到更新

应用读取的是 **GitHub Releases**，不是普通 commit。

所以：

- 只改版本号并 push，不会被旧版本识别为新版本
- 必须再发布对应的 GitHub Release，更新提示才会出现

## 当前仓库约定

- 版本检测来源：`https://github.com/pengqiyu123/auto-news-studio/releases`
- 当前项目会在启动后自动检查一次更新
- 如果发现未忽略的新版本，侧栏“设置”会显示红点
