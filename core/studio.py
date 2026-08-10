"""動画スタジオ（多チャンネル・多トラック管理）。

「何が何を動かしているか分からなくなる」問題を解決するため、制作ライン
（=トラック）をアカウント×路線×動画タイプ×キャラの単位で**分離管理**する。

- 各トラック: config/tracks/*.json で定義（account / content_line / template / character）
- 各トラックは独立した出力ディレクトリ・state名前空間・生産キューを持つ
- メイン指示システムは `studio_status()` で全トラックの状況を一元確認できる

構成:
  config/accounts.json   … SNSアカウント（投稿先・プラットフォーム）
  config/lines.json      … コンテンツ路線（永遠/バズ/ニュース等・戦略）
  config/tracks/*.json   … トラック定義（分離の単位）
  state["tracks"][id]    … トラックごとの実行履歴・キュー（分離）
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from . import state
from .logger import write_log
from .paths import ROOT, ensure_dirs

ACCOUNTS_FILE = ROOT / "config" / "accounts.json"
LINES_FILE = ROOT / "config" / "lines.json"
TRACKS_DIR = ROOT / "config" / "tracks"


def _load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return default


def _now_stamp() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y%m%d_%H%M%S")


# ---- アカウント / 路線 / トラック ----

def list_accounts() -> dict:
    return _load_json(ACCOUNTS_FILE, {})


def list_lines() -> dict:
    return _load_json(LINES_FILE, {})


def list_tracks() -> list[dict]:
    if not TRACKS_DIR.exists():
        return []
    out = []
    for p in sorted(TRACKS_DIR.glob("*.json")):
        try:
            t = json.loads(p.read_text(encoding="utf-8"))
            if t.get("id"):
                out.append(t)
        except Exception:  # noqa: BLE001
            continue
    return out


def get_track(track_id: str) -> dict | None:
    for t in list_tracks():
        if t.get("id") == track_id:
            return t
    return None


def _track_state(track_id: str) -> dict:
    """トラックの実行履歴・キュー（読み取り用・state の分離名前空間）。"""
    st = state.load()
    tr = st.setdefault("tracks", {}).setdefault(track_id, {"runs": [], "queue": []})
    tr.setdefault("runs", [])
    tr.setdefault("queue", [])
    return tr


def _open_track(track_id: str) -> tuple[dict, dict]:
    """トラックを開く（st, tr）。変更後に state.save(st) すること。"""
    st = state.load()
    tracks = st.setdefault("tracks", {})
    tr = tracks.setdefault(track_id, {"runs": [], "queue": []})
    tr.setdefault("runs", [])
    tr.setdefault("queue", [])
    return st, tr


# ---- 実行 ----

def run_track(track_id: str, instruction: str, count: int = 1) -> dict:
    """指定トラックで動画を生成（分離された出力・状態に記録）。"""
    track = get_track(track_id)
    if not track:
        return {"ok": False, "error": f"トラック未定義: {track_id}"}
    if not track.get("active", True):
        return {"ok": False, "error": f"トラック非アクティブ: {track_id}"}

    from . import factory
    out_root = ensure_dirs()["output"] / "tracks" / track_id
    out_root.mkdir(parents=True, exist_ok=True)
    st, tr = _open_track(track_id)

    reports = []
    ok_any = False
    for i in range(max(int(count), 1)):
        out_dir = out_root / f"{_now_stamp()}_{i}"
        res = factory.run(
            instruction,
            template=track.get("template"),
            out_dir=str(out_dir),
            label=track_id,
        )
        run = {
            "ts": _now_stamp(),
            "instruction": instruction[:60],
            "project_id": res.get("project_id"),
            "status": res.get("status"),
            "artifacts": res.get("artifacts", []),
            "steps": len(res.get("steps", [])),
        }
        tr["runs"].append(run)
        reports.append(run)
        ok_any = ok_any or bool(res.get("ok"))
    state.save(st)
    return {"ok": ok_any, "track": track_id, "count": count, "runs": reports}


def enqueue_track(track_id: str, instruction: str) -> dict:
    """トラックの生産キューへ指示を積む（自動連続生産用）。"""
    track = get_track(track_id)
    if not track:
        return {"ok": False, "error": f"トラック未定義: {track_id}"}
    st, tr = _open_track(track_id)
    tr["queue"].append({"instruction": instruction[:200], "ts": _now_stamp()})
    state.save(st)
    return {"ok": True, "track": track_id, "queued": len(tr["queue"])}


def run_pending(track_id: str | None = None, limit: int = 10) -> dict:
    """未処理キューの指示を自動生産（スケジューラ用・分離管理のまま）。"""
    produced = 0
    ids = [track_id] if track_id else [t["id"] for t in list_tracks()]
    for tid in ids:
        st, tr = _open_track(tid)
        remaining = tr["queue"][:limit]
        tr["queue"] = tr["queue"][limit:]
        state.save(st)
        for item in remaining:
            r = run_track(tid, item.get("instruction", ""))
            produced += 1 if r.get("ok") else 0
    return {"ok": True, "produced": produced}


# ---- 状況（一元確認） ----

def track_status(track_id: str) -> dict:
    track = get_track(track_id)
    if not track:
        return {"ok": False, "error": f"トラック未定義: {track_id}"}
    tr = _track_state(track_id)
    runs = tr["runs"]
    return {
        "ok": True,
        "track": track,
        "run_count": len(runs),
        "queue_length": len(tr["queue"]),
        "last_run": runs[-1] if runs else None,
        "recent_runs": runs[-5:],
    }


def studio_status() -> dict:
    """メイン指示システム用：全トラック・アカウント・路線の状況を一元で返す。"""
    accounts = list_accounts()
    lines = list_lines()
    tracks = []
    for t in list_tracks():
        tid = t["id"]
        tr = _track_state(tid)
        runs = tr["runs"]
        # 状態集計
        by_status = {}
        for r in runs:
            by_status[r.get("status", "?")] = by_status.get(r.get("status", "?"), 0) + 1
        tracks.append({
            "id": tid,
            "name": t.get("name"),
            "account": t.get("account"),
            "account_name": (accounts.get(t.get("account")) or {}).get("name"),
            "content_line": t.get("content_line"),
            "line_name": (lines.get(t.get("content_line")) or {}).get("name"),
            "template": t.get("template"),
            "character": t.get("character"),
            "active": t.get("active", True),
            "run_count": len(runs),
            "by_status": by_status,
            "queue_length": len(tr["queue"]),
            "last_run": (runs[-1] if runs else None),
        })
    return {
        "accounts": accounts,
        "lines": lines,
        "track_count": len(tracks),
        "active_tracks": sum(1 for t in tracks if t["active"]),
        "total_runs": sum(t["run_count"] for t in tracks),
        "tracks": tracks,
    }


# ---- システムIF ----

def action(name: str, args: dict) -> dict:
    """システムIF（core/systems から呼ばれる）。"""
    if name == "status":
        return {"ok": True, "data": studio_status()}
    if name == "list_accounts":
        return {"ok": True, "data": list_accounts()}
    if name == "list_lines":
        return {"ok": True, "data": list_lines()}
    if name == "list_tracks":
        return {"ok": True, "data": list_tracks()}
    if name == "run":
        return run_track(str(args.get("track", "")), str(args.get("instruction", "")),
                         int(args.get("count", 1)))
    if name == "enqueue":
        return enqueue_track(str(args.get("track", "")), str(args.get("instruction", "")))
    if name == "run_pending":
        return run_pending(str(args.get("track") or None) or None, int(args.get("limit", 10)))
    return {"ok": False, "error": f"studio.action 不明: {name}"}
