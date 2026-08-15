"""AIFunRun-Video 単体で動かすための軽量コスト記録スタブ。

統括（AIFunRun メイン）から実行される場合は本家の core.finance が
使われるのではなく、このリポジトリ単体でも工場コストを記録できるように
state/ 配下のローカル台帳へ追記する（統括側の実台帳とは分離）。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .paths import ensure_dirs

LEDGER_FILE = "video_cost.jsonl"


def _ledger_path() -> Path:
    return ensure_dirs()["state"] / LEDGER_FILE


def record(entry_type: str, amount: float, category: str, note: str = "") -> str:
    entry = {
        "ts": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "type": "expense" if entry_type != "income" else "income",
        "amount": round(float(amount), 4),
        "category": category or "other",
        "note": note or "",
    }
    with _ledger_path().open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry["ts"]


def _load_entries() -> list[dict]:
    p = _ledger_path()
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            out.append(json.loads(line))
        except Exception:  # noqa: BLE001
            continue
    return out


def summary() -> dict:
    entries = _load_entries()
    income = sum(e["amount"] for e in entries if e["type"] == "income")
    expense = sum(e["amount"] for e in entries if e["type"] == "expense")
    return {"income": income, "expense": expense, "net": income - expense,
            "entries": len(entries)}
