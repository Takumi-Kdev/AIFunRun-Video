#!/usr/bin/env bash
# AIFunRun-Video ワンショットセットアップ（Linux / macOS）
#
# 使い方:  bash setup.sh
#   外部依存（python/git/ffmpeg）が無ければ scripts/install_deps.sh を自動実行
#   venv 作成 → pip 導入 → .env 生成 → 検証（run.py check）
# Windows は setup.ps1 を使うこと。
set -euo pipefail
cd "$(dirname "$0")"

echo "=== AIFunRun-Video セットアップ開始 ==="

# 0) 外部依存（python3 / git / ffmpeg）
NEED_DEPS=""
for t in python3 git ffmpeg; do
  command -v "$t" >/dev/null 2>&1 || NEED_DEPS="$NEED_DEPS $t"
done
if [ -n "$NEED_DEPS" ]; then
  echo "[0/5] 外部依存が欠落:${NEED_DEPS} → install_deps.sh を実行"
  if [ "$(uname -s)" = "Windows" ]; then
    echo "Windows は scripts/install_deps.ps1 / setup.ps1 を使ってください。"
    exit 1
  fi
  bash scripts/install_deps.sh
else
  echo "[0/5] 外部依存（python3/git/ffmpeg）: あり"
fi

# 1) venv + 依存導入
PY="python3"
if [ -x ".venv/bin/python" ] && [ -x ".venv/bin/pip" ]; then
  PY=".venv/bin/python"
  echo "[1/5] venv は既にあります"
elif [ ! -x ".venv/bin/python" ] && [ ! -x ".venv/bin/pip" ]; then
  echo "[1/5] venv 作成を試行"
  if python3 -m venv .venv 2>/dev/null && [ -x ".venv/bin/python" ]; then
    .venv/bin/pip install -U pip
    PY=".venv/bin/python"
    echo "      venv 使用: $PY"
  else
    echo "      venv 作成不可 → システム python3 を使用（python3-venv が無い環境向け）"
    rm -rf .venv
  fi
else
  # 中途半端な .venv がある → 作り直し
  echo "[1/5] 不完全な .venv を修復"
  rm -rf .venv
  if python3 -m venv .venv 2>/dev/null && [ -x ".venv/bin/python" ]; then
    .venv/bin/pip install -U pip
    PY=".venv/bin/python"
  else
    rm -rf .venv
    echo "      venv 作成不可 → システム python3 を使用"
  fi
fi
echo "      pip 依存を導入"
if "$PY" -m pip install -r requirements.txt 2>/dev/null; then
  :
elif "$PY" -m pip install --user -r requirements.txt 2>/dev/null; then
  :
elif "$PY" -m pip install --break-system-packages -r requirements.txt 2>/dev/null; then
  :
else
  echo "      （pip 導入が環境により制限されています。依存が既に入っていれば続行します）"
fi

# 2) .env 雛形
echo "[2/5] .env 準備"
if [ ! -f "config/credentials/.env" ]; then
  cp config/credentials/.env.example config/credentials/.env
  echo "      .env を生成 → キーを記入（任意。無くてもルール生成で動作）"
else
  echo "      .env は既にあります"
fi

# 3) 実行ディレクトリ
echo "[3/5] 実行ディレクトリ準備"
mkdir -p output state logs memory

# 4) 検証
echo "[4/5] システム検証"
if "$PY" run.py check; then
  echo ""
  echo "=== セットアップ完了（検証OK） ==="
else
  echo ""
  echo "=== セットアップ完了（注意あり。上の検証を確認） ==="
fi
echo ""
echo "生成:   $PY run.py factory 'AIの基本を解説するショート動画'"
echo "状況:   $PY run.py studio-status"
echo "opencode MCP:   ./run.sh mcp"
