"""状態管理: state.json + イベントソーシング + スナップショット。

AIProductionOS-riot の StateManager 設計を受け継ぎつつ、Python でシンプルに実装。
- 全状態は state/state.json に集約
- あらゆる変更は state/events.jsonl に追記（監査・復元）
- 10分ごとのスナップショット + 起動時イベントリプレイ
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

from .logger import write_log
from .paths import ensure_dirs

SNAPSHOT_INTERVAL = 600  # 秒


def _state_dir() -> Path:
    return ensure_dirs()["state"]


def _state_file() -> Path:
    return _state_dir() / "state.json"


def _events_file() -> Path:
    return _state_dir() / "events.jsonl"


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _default_state() -> dict:
    return {
        "version": 1,
        "created_at": _now_iso(),
        "projects": {},       # project_id -> project dict
        "runs": [],           # 実行履歴
        "agents": {},         # エージェント状態
        "accounts": {},       # プラットフォームアカウント設定
    }


def load() -> dict:
    f = _state_file()
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            write_log(f"state.json 読込失敗（イベントから復元を試行）: {e}", "WARN")
            # 破損時: イベントログから直接復元（load()を再帰しない）
            return _rebuild_from_events()
    return _default_state()


def _rebuild_from_events() -> dict:
    st = _default_state()
    f = _events_file()
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                apply_event(st, json.loads(line))
            except Exception:  # noqa: BLE001
                continue
    try:
        save(st)
    except Exception:  # noqa: BLE001
        pass
    return st


def _atomic_write(path: Path, data: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(data, encoding="utf-8")
    tmp.replace(path)


def save(state: dict) -> None:
    _atomic_write(_state_file(), json.dumps(state, ensure_ascii=False, indent=2))


def record_event(state: dict, kind: str, payload: dict) -> None:
    """イベントを events.jsonl に追記し、state を変える。先に state を mutate 済みであること。"""
    ev = {
        "ts": _now_iso(),
        "kind": kind,
        "payload": payload,
    }
    with _events_file().open("a", encoding="utf-8") as f:
        f.write(json.dumps(ev, ensure_ascii=False) + "\n")
    save(state)


def replay_events() -> None:
    """起動時: events.jsonl をリプレイして state.json へ反映する。"""
    f = _events_file()
    if not f.exists():
        return
    state = _rebuild_from_events()  # load()を再帰しない
    lines = f.read_text(encoding="utf-8").splitlines()
    for line in lines:
        try:
            ev = json.loads(line)
            apply_event(state, ev)
        except Exception as e:  # noqa: BLE001
            write_log(f"イベントリプレイ失敗: {e}", "ERROR")
    save(state)
    write_log(f"イベントリプレイ完了: {len(lines)} 件")


def apply_event(state: dict, ev: dict) -> None:
    kind = ev.get("kind", "")
    p = ev.get("payload", {})
    if kind == "project.upsert":
        state.setdefault("projects", {})[p["id"]] = {**state["projects"].get(p["id"], {}), **p}
    elif kind == "run.record":
        state.setdefault("runs", []).append(p)
    elif kind == "agent.upsert":
        state.setdefault("agents", {})[p["id"]] = {**state["agents"].get(p["id"], {}), **p}
    elif kind == "account.upsert":
        state.setdefault("accounts", {})[p["id"]] = {**state["accounts"].get(p["id"], {}), **p}


def ensure_snapshot() -> None:
    """前回スナップショットから一定時間経過していれば events.jsonl をリセット。"""
    evf = _events_file()
    snap = _state_dir() / "snapshot.json"
    now = time.time()
    if snap.exists() and (now - snap.stat().st_mtime) < SNAPSHOT_INTERVAL:
        return
    state = load()
    _atomic_write(snap, json.dumps(state, ensure_ascii=False, indent=2))
    if evf.exists():
        evf.unlink()
    write_log("スナップショット保存 & イベントログリセット")


def new_project(project_id: str, title: str, mode: str, instruction: str) -> None:
    state = load()
    state.setdefault("projects", {})[project_id] = {
        "id": project_id,
        "title": title,
        "mode": mode,
        "instruction": instruction,
        "status": "planned",
        "steps": [],
        "artifacts": [],
        "metrics": {},
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    record_event(state, "project.upsert", state["projects"][project_id])


