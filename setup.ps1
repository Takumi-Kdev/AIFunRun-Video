# AIFunRun-Video ワンショットセットアップ（Windows PowerShell）
#
# 使い方:
#   powershell -ExecutionPolicy Bypass -File setup.ps1
#
# 内容: 外部依存(install_deps.ps1) → venv → pip → .env → 検証

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $MyInvocation.MyCommand.Path -Parent)

Write-Host "=== AIFunRun-Video セットアップ開始 ==="

# 1) 外部依存（python/git/ffmpeg）
Write-Host "[1/4] 外部依存の導入"
powershell -ExecutionPolicy Bypass -File scripts/install_deps.ps1

# 2) venv 作成 + pip
Write-Host "[2/4] venv 作成 + 依存導入"
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    py -m venv .venv
}
.\.venv\Scripts\python -m pip install -U pip
.\.venv\Scripts\pip install -r requirements.txt

# 3) .env 雛形
Write-Host "[3/4] .env 準備"
New-Item -ItemType Directory -Force -Path "config\credentials" | Out-Null
if (-not (Test-Path "config\credentials\.env")) {
    if (Test-Path "config\credentials\.env.example") {
        Copy-Item "config\credentials\.env.example" "config\credentials\.env"
        Write-Host "      .env を生成 → キーを記入（任意。無くてもルール生成で動作）"
    } else {
        Set-Content -Path "config\credentials\.env" -Value "# AIFunRun-Video 秘密情報`n# DEEPSEEK_API_KEY=`n# BLENDER_HOST=`n# BLENDER_PORT=`n"
        Write-Host "      .env.example が無いため空の .env を生成"
    }
} else {
    Write-Host "      .env は既にあります"
}
New-Item -ItemType Directory -Force -Path output,state,logs,memory | Out-Null

# 4) 検証
Write-Host "[4/4] 検証"
& .\.venv\Scripts\python run.py check
Write-Host "=== セットアップ完了 ==="
Write-Host "生成:   .venv\Scripts\python run.py factory 'AIの基本を解説するショート動画'"
Write-Host "状況:   .venv\Scripts\python run.py studio-status"
