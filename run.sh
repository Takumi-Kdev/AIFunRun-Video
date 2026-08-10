#!/usr/bin/env bash
# AIFunRun-Video 起動ヘルパー
#   ./run.sh mcp      … MCPサーバー起動（opencode/Claude Code から接続）
#   ./run.sh daemon   … 自律連続生産ループ
set -euo pipefail
cd "$(dirname "$0")"
PY=python3
[ -x ".venv/bin/python" ] && PY=".venv/bin/python"
command -v "$PY" >/dev/null || { echo "python3 が必要です"; exit 1; }

case "${1:-help}" in
  mcp)
    echo "MCPサーバー起動（stdio）。opencode の mcp 設定から接続:"
    echo '  opencode.json: { "mcp": { "video": { "type":"local", "command":["'$(command -v $PY 2>/dev/null || echo python3)'", "run.py", "mcp"] } } }'
    exec "$PY" run.py mcp
    ;;
  daemon)
    shift || true
    exec "$PY" run.py daemon "$@"
    ;;
  check)
    exec "$PY" run.py check
    ;;
  *)
    echo "使い方: $0 {mcp|daemon|check}"
    exit 1
    ;;
esac
