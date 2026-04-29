$ErrorActionPreference = "Stop"

$projectRoot = "D:\python\Auto-news2\projects"
$targets = @(
  @{ Name = "TrendRadar-master"; Repo = "https://github.com/sansan0/TrendRadar.git"; Branch = "master" },
  @{ Name = "DataCube-AI-Space-main"; Repo = "https://github.com/Rswcf/DataCube-AI-Space.git"; Branch = "main" },
  @{ Name = "Folo-dev"; Repo = "https://github.com/RSSNext/Folo.git"; Branch = "dev" },
  @{ Name = "gorse-master"; Repo = "https://github.com/gorse-io/gorse.git"; Branch = "master" },
  @{ Name = "newshub-main"; Repo = "https://github.com/Varshithvhegde/newshub.git"; Branch = "main" },
  @{ Name = "ai_news_rss_summarizer-main"; Repo = "https://github.com/gth-ai/ai_news_rss_summarizer.git"; Branch = "main" },
  @{ Name = "onefilellm-main"; Repo = "https://github.com/jimmc414/onefilellm.git"; Branch = "main" }
)

function Invoke-GitCloneWithRetry {
  param(
    [string]$Repo,
    [string]$Branch,
    [string]$Dest,
    [int]$Retries = 3
  )

  for ($attempt = 1; $attempt -le $Retries; $attempt++) {
    Write-Host "[$attempt/$Retries] Cloning $Repo ($Branch) ..."
    git clone --depth 1 --filter=blob:none --branch $Branch $Repo $Dest
    if ($LASTEXITCODE -eq 0) {
      return
    }
    if (Test-Path $Dest) {
      Remove-Item -LiteralPath $Dest -Recurse -Force
    }
    Start-Sleep -Seconds (3 * $attempt)
  }

  throw "Clone failed after $Retries attempts: $Repo"
}

foreach ($target in $targets) {
  $dest = Join-Path $projectRoot $target.Name
  $backup = "$dest.__old"

  if (Test-Path $backup) {
    Remove-Item -LiteralPath $backup -Recurse -Force
  }

  if (Test-Path $dest) {
    Rename-Item -LiteralPath $dest -NewName ([System.IO.Path]::GetFileName($backup))
  }

  try {
    Invoke-GitCloneWithRetry -Repo $target.Repo -Branch $target.Branch -Dest $dest
    if (Test-Path $backup) {
      Remove-Item -LiteralPath $backup -Recurse -Force
    }
    $sha = (git -C $dest rev-parse HEAD).Trim()
    Write-Host "Updated $($target.Name) -> $sha"
  } catch {
    if (Test-Path $dest) {
      Remove-Item -LiteralPath $dest -Recurse -Force
    }
    if (Test-Path $backup) {
      Rename-Item -LiteralPath $backup -NewName ([System.IO.Path]::GetFileName($dest))
    }
    Write-Warning "Failed to refresh $($target.Name): $($_.Exception.Message)"
  }
}
