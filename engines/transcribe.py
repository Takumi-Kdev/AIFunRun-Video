"""音声→字幕エンジン（テキスト駆動・SNS字幕強化）。

Blender が扱えない「音声認識・字幕生成」を担当する。
  - transcribe : 動画/音声 → SRT/VTT 字幕（faster-whisper。CPUでも動作）
  - subtitle_burn : SRT → 動画へ字幕焼き込み
  - summarize  : 文字起こし → 短い要約（説明欄/概要用）

バックエンド: faster-whisper があれば本格認識。無ければ安全に要セットアップを返す。
"""
from __future__ import annotations

import shutil
from pathlib import Path

from core.logger import write_log
from core.tool_layer import Tool, ToolResult
from core import process


def _whisper_available() -> bool:
    try:
        import faster_whisper  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False


def _ffmpeg() -> str | None:
    from core.tooling import resolve
    return resolve("ffmpeg")


def _srt_time(sec: float) -> str:
    ms = int(round(sec * 1000))
    h = ms // 3600000
    m = (ms % 3600000) // 60000
    s = (ms % 60000) // 1000
    z = ms % 1000
    return f"{h:02d}:{m:02d}:{s:02d},{z:03d}"


def transcribe(media: str, out: str, lang: str | None = None) -> tuple[bool, str]:
    """faster-whisper で文字起こしし SRT を出力。"""
    if not _whisper_available():
        return False, "faster-whisper 未導入（pip install faster-whisper）。字幕生成はそれを導入後に利用可能"
    try:
        from faster_whisper import WhisperModel  # type: ignore
        model = WhisperModel("small", device="cpu", compute_type="int8")
        segs, _ = model.transcribe(media, language=lang)
        lines = []
        idx = 0
        for seg in segs:
            idx += 1
            t0 = _srt_time(seg.start)
            t1 = _srt_time(seg.end)
            lines.append(f"{idx}\n{t0} --> {t1}\n{seg.text.strip()}\n")
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_text("\n".join(lines), encoding="utf-8")
        return (True, out) if lines else (False, "文字起こし結果なし")
    except Exception as e:  # noqa: BLE001
        return False, f"文字起こし失敗: {e}"


def subtitle_burn(video: str, srt: str, out: str, fontsize: int = 28) -> tuple[bool, str]:
    """SRT 字幕を動画へ焼き込む。"""
    if not _ffmpeg():
        return False, "ffmpeg 未インストール"
    from core import process as _p
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    # サブタイトルフィルタが無い環境はフォールバック（テキスト焼き込みは media_edit 側）
    r = _p.run_command(
        [_ffmpeg(), "-y", "-i", video,
         "-vf", f"subtitles={str(srt)}:force_style='Fontsize={fontsize},OutlineColour=&H00000000,BorderStyle=1,Outline=2'",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "copy", out],
        timeout_ms=180000, max_output_bytes=300_000, kill_process_tree=True)
    return (True, out) if r.ok and Path(out).exists() else (False, r.error or "字幕焼き込み失敗")


class TranscribeTool(Tool):
    name = "transcribe"
    description = "音声→字幕SRT生成（faster-whisper）・字幕焼き込み（SNS視聴時間向上）"

    def health(self) -> bool:
        return _whisper_available()

    def setup(self) -> ToolResult:
        return ToolResult(ok=False, error="faster-whisper 未導入（pip install faster-whisper）") if not self.health() else ToolResult(ok=True)

    def run(self, **kwargs) -> ToolResult:
        action = kwargs.get("action", "health")

        if action == "health":
            return ToolResult(ok=self.health(), data={"faster_whisper": _whisper_available()})

        if action == "transcribe":
            media = kwargs.get("media", "")
            out = kwargs.get("out", "output/subtitle.srt")
            if not media:
                return ToolResult(ok=False, error="media が必要")
            ok, msg = transcribe(media, out, kwargs.get("lang"))
            return ToolResult(ok=ok, data={"output": msg if ok else ""},
                              artifacts=[out] if ok else [], error="" if ok else msg)

        if action == "subtitle_burn":
            video, srt, out = kwargs.get("video", ""), kwargs.get("srt", ""), kwargs.get("out", "")
            if not (video and srt and out):
                return ToolResult(ok=False, error="video / srt / out が必要")
            ok, msg = subtitle_burn(video, srt, out, int(kwargs.get("fontsize", 28)))
            return ToolResult(ok=ok, data={"output": msg if ok else ""},
                              artifacts=[out] if ok else [], error="" if ok else msg)

        return ToolResult(ok=False, error=f"未知 action: {action}")
