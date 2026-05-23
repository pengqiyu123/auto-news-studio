# 发布流程

## 版本号位置

每次发版需要同步更新以下文件中的版本号：

| 文件 | 说明 |
|------|------|
| `version.json` | 主版本入口 |
| `frontend/package.json` | 前端版本 |
| `frontend/package-lock.json` | 锁文件 |
| `backend/app/store_base.py` | 后端默认版本常量 |
| `backend/app/main.py` | 启动时版本 |
| `backend/app/store_mixins/settings_mixin.py` | 设置相关版本 |
| `frontend/src/lib/api.ts` | 前端 API 兜底版本 |
| 测试文件中的硬编码版本 | 如有 |

## 发版步骤

### 1. 代码与测试

```bash
# 前端构建 + 类型检查
cd frontend && npm run build

# 后端语法检查
python -m compileall backend/app

# 后端测试
python -m pytest backend/tests/ -q

# 前端测试
cd frontend && npm run test -- --run
```

### 2. 编写更新说明

新建 `docs/release/RELEASE_NOTES_x.y.z.md`，格式示例：

```markdown
# vX.Y.Z

## 改动
- xxx
- xxx

## 修复
- xxx
```

### 3. 构建分发包

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build_release.ps1
```

产物位于 `dist/windows/auto-news-studio-windows.zip`。分发包默认 offline-ready，包含 `.venv`。

### 4. 提交与打 Tag

```bash
git add <本次版本相关文件>
git commit -m "release: ship vX.Y.Z"
git tag vX.Y.Z
git push origin master vX.Y.Z
```

### 5. 发布 GitHub Release

**方式 A：使用 gh CLI**

```bash
gh release create vX.Y.Z dist/windows/auto-news-studio-windows.zip \
  --title "vX.Y.Z" \
  --notes-file docs/release/RELEASE_NOTES_X.Y.Z.md
```

**方式 B：无 gh 时，用 Git 凭据调 API**

```powershell
# 读取凭据
$cred = cmd /c "echo protocol=https&echo host=github.com&echo.&exit" | git credential fill
$token = ($cred | Select-String '^password=').ToString().Replace('password=', '').Trim()

# 创建 Release
$headers = @{
  Authorization = "Bearer $token"
  Accept = "application/vnd.github+json"
  "User-Agent" = "Auto-News-Studio"
  "X-GitHub-Api-Version" = "2022-11-28"
}
$body = @{
  tag_name = "vX.Y.Z"
  target_commitish = "master"
  name = "vX.Y.Z"
  body = (Get-Content docs/release/RELEASE_NOTES_X.Y.Z.md -Raw)
  draft = $false
  prerelease = $false
} | ConvertTo-Json -Depth 8

Invoke-RestMethod -Method Post `
  -Uri "https://api.github.com/repos/<owner>/<repo>/releases" `
  -Headers $headers -Body $body -ContentType "application/json"

# 上传 zip 资产
$release = Invoke-RestMethod -Method Get `
  -Uri "https://api.github.com/repos/<owner>/<repo>/releases/tags/vX.Y.Z" `
  -Headers $headers
$uploadUri = $release.upload_url.Split('{')[0] + '?name=auto-news-studio-windows.zip'
Invoke-RestMethod -Method Post `
  -Uri $uploadUri -Headers $headers `
  -InFile dist/windows/auto-news-studio-windows.zip `
  -ContentType "application/zip"
```

### 6. 验证

- 启动应用，确认首页/设置页出现更新提示
- 确认 GitHub Release 页面可见 zip 资产

## 注意事项

- **git push 不等于发版**：应用读取的是 GitHub Releases，不是 commit。必须创建 Release 才会触发旧版本更新提示。
- **不要复用旧 tag**：如果本地已存在同名 tag，必须升级版本号。
- **浏览器链路回归**：涉及微信/抖音浏览器操作时，`check-drafts`、`check-publish-history`、`sync`、`delete` 共享同一把浏览器锁，必须串行验证。
- **Agent 回归**：先确认调度器已停止，再依次测试 sync → deep-dive → brief → agent/articles。
- **前端 dist 依赖**：某些后端测试读取 `frontend/dist/assets`，所以先 `npm run build` 再跑后端回归。
- **重启后再验证**：改过后端代码后，必须 stop + start，否则命中旧常驻进程。
