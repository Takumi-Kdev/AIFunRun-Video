#!/usr/bin/env bash
# AIFunRun-Video セットアップ（venv + 依存 + .env + 検証）
set -euo pipefail
cd "$(dirname "$0")"
PY=python3
command -v "$PY" >/dev/null || { echo "python3 が見つかりません"; exit 1; }

echo "=== AIFunRun-Video セットアップ開始 ==="
if [ ! -x ".venv/bin/python" ]; then
  echo "[1/3] venv 作成"
  "$PY" -m venv .venv
  .venv/bin/pip install -U pip
else
  echo "[1/3] venv は既にあります"
fi
echo "[2/3] 依存導入"
.venv/bin/pip install -r requirements.txt

echo "[3/3] .env 準備 + 検証"
if [ ! -f "config/credentials/.env" ]; then
  cp config/credentials/.env.example config/credentials/.env
  echo "      .env を生成 → キーを記入（任意。無くてもルール生成で動作）"
fi
mkdir -p output state logs memory
"$PY" run.py check || echo "（注意: 上記の不足を確認してください。ffmpeg が必須です）"
echo "=== セットアップ完了 ==="
echo "生成:   python3 run.py factory 'AIの基本を解説するショート動画'"
echo "状況:   python3 run.py studio-status"
