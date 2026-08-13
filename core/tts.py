"""TTS 層。複数バックエンドに対応し、無ければ静かにスキップ（フォールバック設計）。

バックエンド優先:
  1. Piper（ローカルNeural TTS、日本語音声対応）
  2. espeak-ng（軽量、質は低い）
  3. なし（ナレーション無しでテロップのみの動画に）

Piper の日本語音声は tools/ に .onnx と .json を置く。
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from .paths import ensure_dirs

JP_VOICES = [
    "ja_JP/kaori/kaori",
    "ja_JP/maori/maori",
    "ja_JP",  # ベース名のみの場合
]


def _find_piper() -> str | None:
    found = shutil.which("piper")
    if found:
        return found
    sibling = Path(sys.executable).resolve().parent / ("piper.exe" if sys.platform == "win32" else "piper")
    return str(sibling) if sibling.exists() else None


def _windows_sapi_available() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import pyttsx3  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False


def _find_voice() -> tuple[Path, Path] | None:
    tools = ensure_dirs()["config"].parent / "tools" / "voices"
    for v in JP_VOICES:
        onnx_candidates = [tools / f"{v}.onnx", Path(str(v) + ".onnx")]
        for onnx in onnx_candidates:
            if onnx.exists():
                json_path = Path(str(onnx) + ".json")
                return onnx, (json_path if json_path.exists() else onnx.with_suffix(".json"))
    return None


def available() -> dict:
    return {
        "piper": bool(_find_piper()),
        "espeak_ng": bool(shutil.which("espeak-ng") or shutil.which("espeak")),
        "voice": bool(_find_voice()),
        "windows_sapi": _windows_sapi_available(),
    }


def synthesize(text: str, out_wav: Path) -> str | None:
    """text を音声にし、out_wav に書き出す。成功ならパス、失敗/非対応なら None。"""
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    piper = _find_piper()
    if piper and _find_voice():
        return _synthesize_piper(piper, text, out_wav)
    if _windows_sapi_available():
        sapi_result = _synthesize_windows_sapi(text, out_wav)
        if sapi_result:
            return sapi_result
    espeak = shutil.which("espeak-ng") or shutil.which("espeak")
    if espeak:
        return _synthesize_espeak(espeak, text, out_wav)
    return None


def _synthesize_windows_sapi(text: str, out_wav: Path) -> str | None:
    """Windows標準の日本語音声を使い、ネット接続なしでWAVを生成する。"""
    try:
        import pyttsx3

        engine = pyttsx3.init("sapi5")
        voices = engine.getProperty("voices") or []
        preferred = next(
            (
                voice
                for voice in voices
                if "haruka" in f"{getattr(voice, 'name', '')} {getattr(voice, 'id', '')}".lower()
                or "ja-jp" in f"{getattr(voice, 'languages', '')}".lower()
            ),
            None,
        )
        if preferred is not None:
            engine.setProperty("voice", preferred.id)
        engine.save_to_file(text, str(out_wav))
        engine.runAndWait()
        engine.stop()
        if out_wav.exists() and out_wav.stat().st_size > 44:
            return str(out_wav)
    except Exception:  # noqa: BLE001
        pass
    return None


def _synthesize_piper(piper: str, text: str, out_wav: Path) -> str | None:
    onnx, _ = _find_voice()  # type: ignore[assignment]
    cmd = [piper, "--model", str(onnx), "--output_file", str(out_wav)]
    try:
        r = subprocess.run(cmd, input=text, capture_output=True, text=True, timeout=120)
        if r.returncode == 0 and out_wav.exists():
            return str(out_wav)
    except Exception:  # noqa: BLE001
        pass
    return None


def _synthesize_espeak(espeak: str, text: str, out_wav: Path) -> str | None:
    cmd = [espeak, "-v", "ja", "-w", str(out_wav), text]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=120)
        if r.returncode == 0 and out_wav.exists():
            return str(out_wav)
    except Exception:  # noqa: BLE001
        pass
    return None
