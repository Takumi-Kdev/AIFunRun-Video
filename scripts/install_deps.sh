#!/usr/bin/env bash
# AIFunRun-Video 外部依存のOS別導入（Linux / macOS）
#
# 必須: python3 / git / ffmpeg
# 任意: brew or apt/dnf で導入（ffmpeg が動画生成に必須）
#
# 使い方:  bash scripts/install_deps.sh
set -euo pipefail

echo "=== AIFunRun-Video 外部依存の導入（Linux/macOS） ==="
UNAME="$(uname -s)"

case "$UNAME" in
  Darwin)
    # macOS: Homebrew
    if ! command -v brew >/dev/null 2>&1; then
      echo "Homebrew が必要です → https://brew.sh  (インストール: /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\")"
      exit 1
    fi
    echo "[brew] python / git / ffmpeg を導入"
    brew install python git ffmpeg
    ;;
  Linux)
    if command -v apt-get >/dev/null 2>&1; then
      echo "[apt] python3 / venv / pip / git / ffmpeg を導入"
      sudo apt-get update
      sudo apt-get install -y python3 python3-venv python3-pip git ffmpeg
    elif command -v dnf >/dev/null 2>&1; then
      echo "[dnf] python3 / pip / git / ffmpeg を導入"
      sudo dnf install -y python3 python3-pip git ffmpeg
    elif command -v pacman >/dev/null 2>&1; then
      echo "[pacman] python / git / ffmpeg を導入"
      sudo pacman -Sy --noconfirm python python-pip git ffmpeg
    else
      echo "対応パッケージマネージャ（apt/dnf/pacman）が見つかりません。"
      echo "手動で python3 / git / ffmpeg を導入してください。"
      exit 1
    fi
    ;;
  *)
    echo "Windows は scripts/install_deps.ps1 を使ってください。"
    exit 1
    ;;
esac

echo ""
echo "=== 確認 ==="
MISSING=""
for t in python3 git ffmpeg; do
  if command -v "$t" >/dev/null 2>&1; then echo "  OK: $t"; else echo "  NG: $t"; MISSING="$MISSING $t"; fi
done
if [ -n "$MISSING" ]; then
  echo "欠落:${MISSING} → パスを確認するか導入し直してください"
  exit 1
fi
echo "外部依存の導入が完了しました。次: bash setup.sh"
