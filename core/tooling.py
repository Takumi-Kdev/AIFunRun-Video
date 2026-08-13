"""外部クリエイティブツールの一元解決。

通常の PATH に加え、AIFunRun 本体が管理する portable tools と Windows の
winget 配下を探索する。リポジトリごとに同じ巨大ツールを重複配置しない。
"""
from __future__ import annotations

import os
import shutil
import sys
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _names(name: str) -> list[str]:
    suffix = ".exe" if sys.platform == "win32" else ""
    aliases = {
        "freecadcmd": ["FreeCADCmd", "freecadcmd"],
        "ffmpeg": ["ffmpeg"],
        "ffprobe": ["ffprobe"],
        "blender": ["blender"],
        "openscad": ["openscad"],
        "piper": ["piper"],
    }.get(name.lower(), [name])
    return [value if value.lower().endswith(suffix) else value + suffix for value in aliases]


def _roots() -> list[Path]:
    roots = [ROOT / ".tools", ROOT.parent / "AIFunRun" / ".tools"]
    local = os.environ.get("LOCALAPPDATA")
    if local:
        roots.append(Path(local) / "Microsoft" / "WinGet" / "Packages")
    return [path for path in roots if path.exists()]


@lru_cache(maxsize=64)
def resolve(name: str) -> str | None:
    """実行ファイルを PATH / portable tools / winget から見つける。"""
    found = shutil.which(name)
    if found:
        return found
    wanted = _names(name)
    patterns = {
        "ffmpeg": ["*FFmpeg*/**/ffmpeg.exe", "ffmpeg*/**/ffmpeg.exe"],
        "ffprobe": ["*FFmpeg*/**/ffprobe.exe", "ffmpeg*/**/ffprobe.exe"],
        "blender": ["blender-*/blender.exe", "**/blender.exe"],
        "openscad": ["openscad-*/openscad.exe", "**/openscad.exe"],
        "freecadcmd": ["FreeCAD-*/**/FreeCADCmd.exe", "**/freecadcmd.exe"],
        "piper": ["**/piper.exe"],
    }.get(name.lower(), [f"**/{value}" for value in wanted])
    for root in _roots():
        try:
            for pattern in patterns:
                path = next((item for item in root.glob(pattern) if item.is_file()), None)
                if path:
                    return str(path.resolve())
        except OSError:
            continue
    if name.lower() == "piper":
        candidate = Path(sys.executable).resolve().parent / _names("piper")[0]
        if candidate.exists():
            return str(candidate)
    return None


def inventory() -> dict[str, str | None]:
    return {name: resolve(name) for name in (
        "ffmpeg", "ffprobe", "blender", "openscad", "freecadcmd", "piper"
    )}


def activate(names: tuple[str, ...] = ("ffmpeg", "ffprobe")) -> None:
    """発見したツールを子プロセスや既存コードのshutil.whichからも見えるようにする。"""
    current = os.environ.get("PATH", "").split(os.pathsep)
    additions = []
    for name in names:
        path = resolve(name)
        if path and str(Path(path).parent) not in current + additions:
            additions.append(str(Path(path).parent))
    if additions:
        os.environ["PATH"] = os.pathsep.join([*additions, *current])
