"""ログ出力。logs/ にタイムスタンプ付きで追記する。"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from .paths import ensure_dirs, get_paths


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def write_log(entry: str, level: str = "INFO") -> str:
    ensure_dirs()
    logfile = get_paths()["logs"] / "run.log"
    line = f"[{now_iso()}] [{level}] {entry}"
    with logfile.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    return line


def get_logger(name: str) -> logging.Logger:
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
    return logging.getLogger(name)
