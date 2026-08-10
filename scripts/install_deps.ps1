# AIFunRun-Video 外部依存の導入（Windows）
# 必須: Python / Git / ffmpeg
# winget を使って導入します（Windows 10/11 標準）。
#
# 使い方（PowerShell）:
#   powershell -ExecutionPolicy Bypass -File scripts/install_deps.ps1

Write-Host "=== AIFunRun-Video 外部依存の導入（Windows） ==="

# winget が無ければ案内
if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
    Write-Host "winget が見つかりません。Windows 10/11 の Microsoft Store の App Installer を更新するか、"
    Write-Host "手動で以下を導入してください:"
    Write-Host "  - Python:  https://www.python.org/downloads/   (インストール時 'Add python.exe to PATH' にチェック)"
    Write-Host "  - Git:     https://git-scm.com/downloads"
    Write-Host "  - ffmpeg:  https://ffmpeg.org/download.html  (bin を PATH に追加)"
    exit 1
}

Write-Host "[winget] Python 3.12 を導入"
winget install --id Python.Python.3.12 -e --accept-package-agreements --accept-source-agreements

Write-Host "[winget] Git を導入"
winget install --id Git.Git -e --accept-package-agreements --accept-source-agreements

Write-Host "[winget] ffmpeg を導入"
winget install --id Gyan.FFmpeg -e --accept-package-agreements --accept-source-agreements

Write-Host ""
Write-Host "=== 確認 ==="
$missing = @()
foreach ($t in @('python','py','git','ffmpeg')) {
    if (Get-Command $t -ErrorAction SilentlyContinue) { Write-Host "  OK: $t" }
    else { Write-Host "  NG: $t"; $missing += $t }
}
if ($missing.Count -gt 0) {
    Write-Host "欠落: $($missing -join ', ')"
    Write-Host "→ ターミナルを開き直し、PATH が通ることを確認してください"
    exit 1
}
Write-Host "外部依存の導入が完了しました。次: setup.ps1"
