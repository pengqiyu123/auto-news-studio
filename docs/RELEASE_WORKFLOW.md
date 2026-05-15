# 发布与更新流程

## 目标

每次上传 GitHub 时，版本号、更新说明、分发包、GitHub Release、应用内更新提示要保持一致。

## 已验证版本

- `v0.2.6` 已按本流程完成完整发布（commit + tag + release + zip 资产）
- 旧版本启动后可通过 GitHub Releases 检测到更新
- 应用内首页与设置页会显示更新横幅 / 红点

## 标准流程

1. 修改代码并完成测试
2. 更新版本号
   - `version.json`
   - `frontend/package.json`
   - `frontend/package-lock.json`
   - `backend/app/store_base.py`
   - `backend/app/main.py`
   - `backend/app/store_mixins/settings_mixin.py`
   - `frontend/src/lib/api.ts`
   - 如有测试里写死的版本号，一并更新
   - 如有默认版本常量，一并更新
3. 编写本次更新说明
   - 新建 `docs/RELEASE_NOTES_x.y.z.md`
   - 同步更新 `README.md` 里的当前版本和 release notes 链接
4. 构建验证
   - 先跑与本次改动直接相关的测试
   - `cd frontend && npm run build`
   - `.\.venv\Scripts\python.exe -m compileall backend/app`
   - 再补一轮基础回归，例如：`.\.venv\Scripts\python.exe -m pytest backend/tests/test_intel_pipeline.py backend/tests/test_admin_pagination.py backend/tests/test_agent_upload_guard.py`
   - `cd frontend && npm run test -- --run`
5. 生成 Windows 分发包
   - 运行 `powershell -ExecutionPolicy Bypass -File scripts/build_release.ps1`
   - 产物位于 `runtime/release/auto-news-studio-windows.zip`
6. 提交并推送 GitHub
   - 建议先确认只提交本次版本相关文件，避免把工作区无关改动一并推上去
7. 打 Git tag
   - 例如：`git tag vX.Y.Z`
   - `git push origin vX.Y.Z`
8. 在 GitHub 仓库发布 Release
   - Tag: `vX.Y.Z`
   - Title: `vX.Y.Z`
   - Body: 使用 `docs/RELEASE_NOTES_X.Y.Z.md`
   - 如本机已安装 `gh` 并已登录，可直接用 `gh release create`
   - 如本机未安装 `gh`，但 `git push` 已可用，则优先复用 Git 凭据发 Release：
     - 用 `cmd /c "echo protocol=https&echo host=github.com&echo.&exit" | git credential fill` 读取 GitHub 凭据
     - 再用 `Invoke-RestMethod` 调 `https://api.github.com/repos/<repo>/releases`
     - 当前仓库已实测可用，不依赖 `GH_TOKEN` 环境变量
9. 启动应用检查
   - 首页出现更新横幅
   - 设置页显示更新状态
   - 侧栏“设置”出现红点

## 本地验证注意事项

- 发版前的 Python 测试、打包、自检都应使用项目 `.venv`，不要依赖机器全局环境。
- 某些后端接口测试会读取 `frontend/dist/assets`，所以发布前必须先执行一次 `cd frontend && npm run build`，再跑完整后端回归。
- 只要改过后端代码，手工 API 验证前必须先 `stop.bat`，再 `start.bat`。否则很容易命中旧的常驻进程，看到“代码已改、接口没变”的假象。
- 如果发布内容涉及抖音 / 微信浏览器链，必须补一次真实页面链路验证，并保留最新 artifact 作为证据。
- Agent 回归时，先确认 `GET /api/admin/runtime/status` 显示传统调度器已停止，再做：
  1. `POST /api/admin/sources/sync?triggered_by=agent`
  2. `POST /api/admin/intel/events/{event_id}/deep-dive?triggered_by=agent`
  3. `POST /api/admin/intel/events/{event_id}/brief?triggered_by=agent`
  4. `POST /api/admin/agent/articles`
- Agent 长文上传只走 `/api/admin/agent/articles`；不要拿传统简报去调 `/api/admin/briefs/{brief_id}/wechat-draft`。
- 微信浏览器链回归时，`check-drafts`、`check-publish-history`、`sync to draft`、`delete remote draft` 共享同一把浏览器锁，必须串行验证。

## 分发包约定

- 分发包默认是 offline-ready
- `scripts/build_release.ps1` 会把项目 `.venv` 一起打包进去
- 目标是让 Windows 用户解压后直接安装、直接启动
- 正式发布前应先生成并检查分发包，再执行 GitHub Release

## 当前流程缺口与补齐约定

- `release notes` 已迁移到 `docs/` 目录，发布正文与 README 链接都应使用 `docs/RELEASE_NOTES_x.y.z.md`。
- 版本号不只在 `version.json` 与 `frontend/package.json`，还散落在后端默认常量、前端兜底值和测试里；发版必须统一替换。
- 仅 `git push` 与 `git tag` 还不够，必须继续创建 GitHub Release 并上传 zip，旧版本客户端才会检测到更新。
- 如果本次改动是渠道链路优化，release notes 里必须明确写清是哪条链路，例如“抖音链路优化”或“微信公众号链路修复”。

## 本次实测结果

- 仅推送 `master` 不足以触发旧版更新提示
- 必须同步创建并发布 GitHub Release
- 旧版更新检测读取的是 `releases/latest`
- `RELEASE_NOTES_x.y.z.md` 可以直接作为 Release 正文
- 如果本地已经存在旧 tag（例如 `v0.2.4`），新的上传批次必须升级版本号，不能复用旧 tag
- 当前机器即使没有 `gh`、没有显式 `GITHUB_TOKEN`，也可能通过 Git 凭据管理器中的 GitHub 凭据完成 Release API 发布
- `v0.2.1`、`v0.2.5`、`v0.2.6` 已验证过：`git credential fill + Invoke-RestMethod` 可直接创建 Release，其中 `v0.2.5` 与 `v0.2.6` 还验证了 zip 资产上传

## 无 gh 时的可用发布方式

### 1. 从 Git 凭据中读取 GitHub token

```powershell
$cred = cmd /c "echo protocol=https&echo host=github.com&echo.&exit" | git credential fill
$token = ($cred | Select-String '^password=').ToString().Replace('password=', '').Trim()
```

### 2. 创建 Release

```powershell
$headers = @{
  Authorization = "Bearer $token"
  Accept = "application/vnd.github+json"
  "User-Agent" = "Auto-News-Studio"
  "X-GitHub-Api-Version" = "2022-11-28"
}

$tag = "vX.Y.Z"
$notes = "docs/RELEASE_NOTES_X.Y.Z.md"

$body = @{
  tag_name = $tag
  target_commitish = "master"
  name = $tag
  body = (Get-Content $notes -Raw)
  draft = $false
  prerelease = $false
  generate_release_notes = $false
} | ConvertTo-Json -Depth 8

Invoke-RestMethod -Method Post `
  -Uri "https://api.github.com/repos/pengqiyu123/auto-news-studio/releases" `
  -Headers $headers `
  -Body $body `
  -ContentType "application/json"
```

### 3. 上传 Windows 分发包

```powershell
$tag = "vX.Y.Z"

$release = Invoke-RestMethod -Method Get `
  -Uri "https://api.github.com/repos/pengqiyu123/auto-news-studio/releases/tags/$tag" `
  -Headers $headers

$assetPath = (Resolve-Path "runtime/release/auto-news-studio-windows.zip").Path
$assetName = Split-Path $assetPath -Leaf
$uploadBase = $release.upload_url.Split('{')[0]
$uploadUri = $uploadBase + '?name=' + [uri]::EscapeDataString($assetName)

Invoke-RestMethod -Method Post `
  -Uri $uploadUri `
  -Headers $headers `
  -InFile $assetPath `
  -ContentType "application/zip"
```

## 为什么旧版本有时检测不到更新

应用读取的是 **GitHub Releases**，不是普通 commit。

所以：

- 只改版本号并 push，不会被旧版本识别为新版本
- 必须再发布对应的 GitHub Release，更新提示才会出现

## 当前仓库约定

- 版本检测来源：`https://github.com/pengqiyu123/auto-news-studio/releases`
- 当前项目会在启动后自动检查一次更新
- 如果发现未忽略的新版本，侧栏“设置”会显示红点
