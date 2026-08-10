"""中央設定とパス解決。"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_settings() -> dict:
    with (ROOT / "config" / "settings.json").open(encoding="utf-8") as f:
        return json.load(f)


def get_paths() -> dict:
    s = load_settings()
    p = s.get("paths", {})
    return {
        "memory": ROOT / p.get("memory_dir", "memory"),
        "state": ROOT / p.get("state_dir", "state"),
        "logs": ROOT / p.get("logs_dir", "logs"),
        "output": ROOT / "output",
        "config": ROOT / "config",
    }


def ensure_dirs() -> dict:
    paths = get_paths()
    for v in paths.values():
        Path(v).mkdir(parents=True, exist_ok=True)
    return paths
