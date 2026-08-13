"""生成AIを使わず、手持ち素材を長尺作品へ自動配置するローカル素材庫。"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIBRARY = ROOT / "assets" / "library"
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm"}


def inventory() -> list[dict]:
    LIBRARY.mkdir(parents=True, exist_ok=True)
    items = []
    for path in LIBRARY.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in IMAGE_EXT | VIDEO_EXT:
            continue
        items.append({"path": str(path.resolve()), "name": path.stem,
                      "kind": "image" if path.suffix.lower() in IMAGE_EXT else "video",
                      "tokens": _tokens(path.stem + " " + path.parent.name)})
    return items


def _tokens(text: str) -> set[str]:
    return {token for token in re.split(r"[^\w一-龯ぁ-んァ-ヶ]+", text.lower()) if len(token) > 1}


def assign(shots: list[dict]) -> list[dict]:
    """ファイル名とショット文脈を照合し、同一素材の連続を避けて割り当てる。"""
    items = inventory()
    if not items:
        return shots
    last = ""
    for index, shot in enumerate(shots):
        query = _tokens(" ".join(str(shot.get(k, "")) for k in ("chapter_title", "purpose", "visual_prompt", "on_screen_text")))
        ranked = sorted(items, key=lambda item: (len(query & item["tokens"]), item["path"] != last), reverse=True)
        chosen = ranked[index % min(len(ranked), 5)] if not query else ranked[0]
        if chosen["path"] == last and len(ranked) > 1:
            chosen = ranked[1]
        shot["asset"] = {"path": chosen["path"], "kind": chosen["kind"], "source": "local-library"}
        last = chosen["path"]
    return shots
