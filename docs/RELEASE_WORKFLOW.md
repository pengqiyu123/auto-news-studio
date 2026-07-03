# Release Workflow

## Scope

This document is the canonical release checklist for `D:\python\Auto-news2\auto-news-studio`.

It covers:

- version bump
- validation before release
- release notes
- Windows package build
- git commit / tag / push
- GitHub Release publication

This repo ships from `master` and the GitHub remote is:

- `https://github.com/pengqiyu123/auto-news-studio.git`

## Source Of Truth

The app version is primarily sourced from:

- [version.json](/d:/python/Auto-news2/auto-news-studio/version.json)

The backend and frontend both have local fallbacks that must stay aligned with that version.

## Files To Update For Every Release

When bumping the release version, update all of these together:

1. [version.json](/d:/python/Auto-news2/auto-news-studio/version.json)
2. [frontend/package.json](/d:/python/Auto-news2/auto-news-studio/frontend/package.json)
3. [frontend/package-lock.json](/d:/python/Auto-news2/auto-news-studio/frontend/package-lock.json)
4. [backend/app/store/base.py](/d:/python/Auto-news2/auto-news-studio/backend/app/store/base.py)
5. [backend/app/main.py](/d:/python/Auto-news2/auto-news-studio/backend/app/main.py)
6. [backend/app/store_mixins/settings_mixin.py](/d:/python/Auto-news2/auto-news-studio/backend/app/store_mixins/settings_mixin.py)
7. [frontend/src/lib/api.ts](/d:/python/Auto-news2/auto-news-studio/frontend/src/lib/api.ts)
8. Any tests with pinned app-version expectations
9. [README.md](/d:/python/Auto-news2/auto-news-studio/README.md)
10. A new release note under [docs/release](/d:/python/Auto-news2/auto-news-studio/docs/release)

## Pre-Release Rules

Before tagging a release:

1. Do not overwrite or reuse an existing git tag.
2. Do not treat `git push` as a published release.
3. Do not publish if the Windows package has not been built and checked.
4. Do not publish using synthetic or placeholder release notes.
5. If browser automation or publishing logic changed, validate the real chain, not just mocks.

## Recommended Release Order

Use this order every time:

1. Finish code changes.
2. Review `git status`.
3. Bump version files.
4. Write release notes.
5. Run validation.
6. Build Windows package.
7. Review `git diff`.
8. Commit.
9. Tag.
10. Push branch and tag.
11. Create GitHub Release.
12. Verify the Release page, updater metadata, and tag / release notes / GitHub Release alignment.

## Validation Checklist

Run validation from repo root unless noted otherwise.

### Frontend

```powershell
Set-Location D:\python\Auto-news2\auto-news-studio\frontend
npm run build
```

If you changed targeted frontend behavior, also run the relevant test files, for example:

```powershell
npm test -- --run src/hooks/wechat/useWechatState.test.tsx src/hooks/content/useBriefsState.test.tsx
```

### Backend

From repo root:

```powershell
Set-Location D:\python\Auto-news2\auto-news-studio
$env:PYTHONPATH='D:\python\Auto-news2\auto-news-studio'
pytest backend/tests -q
```

If the full suite is too heavy for a patch release, run the affected test set explicitly and record that scope in the release note.

### Optional Syntax Safety

```powershell
Set-Location D:\python\Auto-news2\auto-news-studio
python -m compileall backend/app
```

## Release Notes

Each release must have a dedicated markdown file:

- format: `docs/release/RELEASE_NOTES_X.Y.Z.md`

Example:

```markdown
# 0.2.13 更新说明

## 本次重点
- ...

## 修复
- ...

## 验证
- ...
```

Release notes should describe:

- user-visible outcomes
- important fixes
- validation actually performed
- any release caveats

## Windows Package Build

The Windows package is built by:

- [scripts/build_release.ps1](/d:/python/Auto-news2/auto-news-studio/scripts/build_release.ps1)

Run:

```powershell
Set-Location D:\python\Auto-news2\auto-news-studio
powershell -ExecutionPolicy Bypass -File .\scripts\build_release.ps1
```

Expected artifacts:

1. `dist/windows/auto-news-studio-windows/`
2. `dist/windows/auto-news-studio-windows.zip`

The package currently bundles:

- backend app code
- frontend `dist`
- `.venv` when present
- startup / stop / doctor scripts
- `version.json`
- `README.md`
- `LICENSE`
- `docs/DISTRIBUTION.md`

## Git Commit And Tag

Review the final diff first:

```powershell
Set-Location D:\python\Auto-news2\auto-news-studio
git status --short
git diff --stat
```

Then stage, commit, and tag:

```powershell
git add .
git commit -m "release: ship v0.2.13"
git tag v0.2.13
```

If the tag already exists locally:

```powershell
git tag --list v0.2.13
```

Do not delete and reuse it for a different payload. Bump to the next version instead.

## Push To GitHub

Push branch and tag:

```powershell
Set-Location D:\python\Auto-news2\auto-news-studio
git push origin master
git push origin v0.2.13
```

The helper script [scripts/release_version.ps1](/d:/python/Auto-news2/auto-news-studio/scripts/release_version.ps1) can push a tag after frontend build and backend compile, but it does not create release notes, does not build the Windows zip, and does not publish the GitHub Release. Treat it as a helper, not the full workflow.

## Publish GitHub Release

### Option A: GitHub CLI

```powershell
Set-Location D:\python\Auto-news2\auto-news-studio
gh release create v0.2.13 dist/windows/auto-news-studio-windows.zip `
  --title "v0.2.13" `
  --notes-file docs/release/RELEASE_NOTES_0.2.13.md
```

### Option B: GitHub API Using Existing Git Credentials

```powershell
Set-Location D:\python\Auto-news2\auto-news-studio
$cred = cmd /c "echo protocol=https&echo host=github.com&echo.&exit" | git credential fill
$token = ($cred | Select-String '^password=').ToString().Replace('password=', '').Trim()

$headers = @{
  Authorization = "Bearer $token"
  Accept = "application/vnd.github+json"
  "User-Agent" = "Auto-News-Studio"
  "X-GitHub-Api-Version" = "2022-11-28"
}

$body = @{
  tag_name = "v0.2.13"
  target_commitish = "master"
  name = "v0.2.13"
  body = (Get-Content .\docs\release\RELEASE_NOTES_0.2.13.md -Raw)
  draft = $false
  prerelease = $false
} | ConvertTo-Json -Depth 8

Invoke-RestMethod -Method Post `
  -Uri "https://api.github.com/repos/pengqiyu123/auto-news-studio/releases" `
  -Headers $headers `
  -Body $body `
  -ContentType "application/json"

$release = Invoke-RestMethod -Method Get `
  -Uri "https://api.github.com/repos/pengqiyu123/auto-news-studio/releases/tags/v0.2.13" `
  -Headers $headers

$uploadUri = $release.upload_url.Split('{')[0] + '?name=auto-news-studio-windows.zip'
Invoke-RestMethod -Method Post `
  -Uri $uploadUri `
  -Headers $headers `
  -InFile .\dist\windows\auto-news-studio-windows.zip `
  -ContentType "application/zip"
```

## Post-Release Verification

After publishing the GitHub Release:

1. Open the Release page and confirm the zip is attached.
2. Confirm the tag and release title match exactly.
3. Confirm `version.json` inside the repo and inside the Windows package is the new version.
4. Start the app and verify the version shown by the UI/API matches the release.
5. Confirm the release notes file used for publication matches the shipped tag.
6. Confirm update metadata resolves correctly from GitHub Releases.

## Product-Specific Release Risks

Pay extra attention to these areas when they changed:

1. Browser automation
   Real WeChat / Douyin flows can pass unit tests but still fail on real pages.

2. PostgreSQL truth mode
   If `STATE_BACKEND=postgres` behavior changed, verify both write path and read path.

3. Draft / publish reconciliation
   Check that local records and remote state still match after release.

4. Startup lifecycle
   If backend startup, runtime, or settings boot changed, stop and restart the actual service before signoff.

## Minimum Release Evidence To Keep

For each shipped version, keep:

1. the commit SHA
2. the tag
3. the release note markdown
4. the built zip
5. the commands used for validation

## Current Patch Release Template

For the current repo state, a practical patch release sequence looks like:

```powershell
Set-Location D:\python\Auto-news2\auto-news-studio

# 1. Validate
$env:PYTHONPATH='D:\python\Auto-news2\auto-news-studio'
pytest backend/tests/test_db_ingest_projection.py backend/tests/test_briefs_mixin.py -q
Set-Location .\frontend
npm test -- --run src/hooks/wechat/useWechatState.test.tsx src/hooks/content/useBriefsState.test.tsx
npm run build
Set-Location ..

# 2. Build release zip
powershell -ExecutionPolicy Bypass -File .\scripts\build_release.ps1

# 3. Review and ship
git status --short
git add .
git commit -m "release: ship v0.2.13"
git tag v0.2.13
git push origin master
git push origin v0.2.13
```
