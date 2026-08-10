"""秘密情報の安全な読み込み。

config/credentials/ は .gitignore 済み（コミットされない）。
優先順: 環境変数 > config/credentials/*.env
"""
from __future__ import annotations

import os
from pathlib import Path

from .paths import ROOT

CRED_DIR = ROOT / "config" / "credentials"

_env_loaded = False


def _load_env_file() -> None:
    global _env_loaded
    if _env_loaded:
        return
    _env_loaded = True
    env_file = CRED_DIR / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip())


def get(key: str, default: str | None = None) -> str | None:
    _load_env_file()
    return os.environ.get(key, default)


def require(key: str) -> str:
    val = get(key)
    if not val:
        raise RuntimeError(f"秘密情報 {key} が未設定です。環境変数または config/credentials/.env に設定してください。")
    return val
