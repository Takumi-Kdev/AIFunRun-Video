"""メディア編集・合成エンジン（FFmpeg + Blender overlay 統合）。

添付された画像・動画を FFmpeg で編集し、Blender でレンダーした3Dオーバーレイを
合成するなど、クリエイティブな加工を実現する。

Actions:
  - edit            : 画像/動画を編集（リサイズ/形式/速度/トリム/字幕/テキスト/音声）
  - image_to_video  : 複数画像 → ケンバーンズ風スライドショー動画
  - composite       : ベース映像 + Blender RGBA オーバーレイ → 合成
  - blender_overlay : Blender で透明背景シーンをレンダーする bpy コードを生成し合成手順を返す

実行は core.process（タイムアウト + プロセスツリー回収付きの堅牢 ffmpeg 実行）。
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from core.logger import write_log
from core.tool_layer import Tool, ToolResult
from core import process


def _ffmpeg() -> str | None:
    from core.tooling import resolve
    return resolve("ffmpeg")


def _filters() -> set[str]:
    """利用可能な ffmpeg フィルタ名の集合（環境差で欠けている場合にフォールバック）。"""
    ff = _ffmpeg()
    if not ff:
        return set()
    r = process.run_command([ff, "-hide_banner", "-filters"], timeout_ms=10000, max_output_bytes=20000)
    out = set()
    for line in r.combined.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            out.add(parts[1])
    return out


def _mkparent(out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)


def _drawtext_font_option() -> str:
    """fontconfig がないWindows版FFmpeg向けに日本語フォントを明示する。"""
    candidates = []
    configured = os.environ.get("AIFUNRUN_FONT_FILE", "").strip()
    if configured:
        candidates.append(Path(configured))
    if os.name == "nt":
        fonts = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
        candidates.extend([fonts / "meiryo.ttc", fonts / "YuGothM.ttc", fonts / "msgothic.ttc"])
    for candidate in candidates:
        if candidate.is_file():
            # FFmpegのfilter構文ではドライブ文字のコロンをエスケープする。
            value = candidate.resolve().as_posix().replace(":", r"\:").replace("'", r"\'")
            return f":fontfile='{value}'"
    return ""


def _run_ffmpeg(argv: list[str], out: Path, timeout_ms: int = 120000) -> tuple[bool, str]:
    if not _ffmpeg():
        return False, "ffmpeg 未インストール"
    _mkparent(out)
    r = process.run_command([_ffmpeg(), "-y"] + argv, timeout_ms=timeout_ms,
                            max_output_bytes=300_000, kill_process_tree=True)
    if r.ok and out.exists():
        return True, str(out)
    return False, r.error or (r.combined[-300:] if r.combined else "ffmpeg失敗")


# ---- フィルタ構築 ----------------------------------------------------------- #

def _format_filter(fmt: str) -> str:
    if fmt == "vertical":
        return "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2"
    if fmt == "horizontal":
        return "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2"
    if fmt == "square":
        return "scale=1080:1080:force_original_aspect_ratio=decrease,pad=1080:1080:(ow-iw)/2:(oh-ih)/2"
    return ""


def edit_media(input_media: str, out: str, *, resize: tuple[int, int] | None = None,
               fmt: str | None = None, speed: float = 1.0, trim: tuple[float, float] | None = None,
               burn_text: str | None = None, subtitles: str | None = None,
               audio: str | None = None, rotate: int = 0) -> tuple[bool, str]:
    """画像/動画を編集して出力する。"""
    filters = _filters()
    vf_parts = []
    if fmt:
        f = _format_filter(fmt)
        if f:
            vf_parts.append(f)
    elif resize:
        vf_parts.append(f"scale={int(resize[0])}:{int(resize[1])}")
    if rotate:
        vf_parts.append(f"rotate={rotate}*PI/180:ow='rotw(ih)':oh='roth(ih)'")
    if speed and speed != 1.0:
        vf_parts.append(f"setpts={1.0/float(speed):.4f}*PTS")
    if burn_text and "drawtext" in filters:
        t = burn_text.replace(":", r"\:").replace("'", r"\'")
        font = _drawtext_font_option()
        vf_parts.append(f"drawtext=text='{t}'{font}:fontcolor=white:fontsize=72:x=(w-text_w)/2:y=(h-text_h)/2:box=1:boxcolor=black@0.5")
    elif burn_text:
        write_log("burn_text: drawtext フィルタなし（スキップ）", "WARN")
    if subtitles and Path(subtitles).exists() and ("subtitles" in filters or "ass" in filters):
        vf_parts.append(f"subtitles={str(subtitles)}")
    elif subtitles:
        write_log("burn_subtitles: subtitles フィルタなし（スキップ）", "WARN")

    argv = []
    if trim:
        argv += ["-ss", f"{trim[0]}", "-t", f"{trim[1]}"]
    argv += ["-i", input_media]
    if vf_parts:
        argv += ["-vf", ",".join(vf_parts)]
    if speed and speed != 1.0 and _has_audio(input_media):
        # 音声も速度合わせ（簡易: atempo は 0.5〜2.0 のみ）
        argv += ["-filter:a", f"atempo={min(max(1.0/float(speed),0.5),2.0):.4f}"]
    if audio and Path(audio).exists():
        argv += ["-i", audio, "-map", "0:v", "-map", "1:a", "-shortest"]
    else:
        argv += ["-map", "0:v", "-map", "0:a?"]
    argv += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac"]
    argv += [out]
    return _run_ffmpeg(argv, Path(out))


def _has_audio(path: str) -> bool:
    ff = _ffmpeg()
    if not ff or not Path(path).exists():
        return False
    r = process.run_command([ff, "-i", path], timeout_ms=15000, max_output_bytes=5000)
    return r.ok and "Audio:" in r.combined


def image_to_video(images: list[str], out: str, *, duration: float = 3.0,
                   fmt: str = "vertical") -> tuple[bool, str]:
    """複数画像 → ケンバーンズ風スライドショー（zoompan + concat）。"""
    if not images:
        return False, "画像がありません"
    tmp_dir = Path(out).parent / "_slides"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    clips = []
    f = _format_filter(fmt) or "scale=1080:1920:force_original_aspect_ratio=decrease"
    for i, img in enumerate(images):
        if not Path(img).exists():
            continue
        c = tmp_dir / f"c{i}.mp4"
        # 画像→ zoompan（ゆっくりズーム）
        argv = [
            "-loop", "1", "-i", img,
            "-vf", f"{f},zoompan=z='min(zoom+0.0015,1.25)':d={int(duration*30)}:s=1080x1920:fps=30",
            "-t", f"{duration}", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(c),
        ]
        ok, _ = _run_ffmpeg(argv, c)
        if ok:
            clips.append(str(c))
    if not clips:
        return False, "スライドクリップ生成に失敗"
    # concat は list 内の相対パスを list ファイルの場所基準で解釈するため、絶対パスにする
    concat = tmp_dir / "list.txt"
    concat.write_text("\n".join(f"file '{Path(c).resolve()}'" for c in clips), encoding="utf-8")
    out_p = Path(out).resolve()
    _mkparent(out_p)
    argv = ["-f", "concat", "-safe", "0", "-i", str(concat), "-c", "copy", str(out_p)]
    ok, msg = _run_ffmpeg(argv, out_p)
    return ok, msg


def composite(base: str, overlay: str, out: str, *, x: int = 0, y: int = 0) -> tuple[bool, str]:
    """ベース映像に Blender RGBA オーバーレイを重ねて合成する。"""
    argv = ["-i", base, "-i", overlay,
            "-filter_complex", f"[1:v]format=rgba[ov];[0:v][ov]overlay={x}:{y}[outv]",
            "-map", "[outv]", "-map", "0:a?", "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", str(out)]
    return _run_ffmpeg(argv, Path(out))


def blender_overlay_script(base: str, out: str, *, scene_type: str = "abstract_3d",
                           frames: int = 90) -> dict:
    """Blender で透明背景シーンをレンダーする bpy コードを生成（合成手順つき）。

    生成コードを Blender で実行 → RGBA 動画 → composite() でベースに重ねる。
    """
    from engines import scene as scene_mod
    code = scene_mod.build_scene(
        f"オーバーレイ {scene_type}", scene_type=scene_type,
        out=out, resolution=(1920, 1080), fps=30, frames=frames,
    )
    # 透明背景化 + alpha 出力へ変換
    code = code.replace(
        "bpy.context.scene.render.image_settings.file_format = 'FFMPEG'",
        "bpy.context.scene.render.film_transparent = True\n"
        "bpy.context.scene.render.image_settings.file_format = 'FFMPEG'\n"
        "bpy.context.scene.render.ffmpeg.codec = 'PNG'",
    ).replace("bpy.context.scene.render.ffmpeg.codec = 'H264'", "")
    return {"code": code, "base": base, "out": out,
            "note": "生成した bpy コードを Blender で実行 → RGBA動画を出力 → composite() で合成"}


class MediaEditTool(Tool):
    name = "media_edit"
    description = "FFmpegで画像/動画を編集・合成（Blender overlay対応・ケンバーンズ・字幕・テキスト・音声）"

    def health(self) -> bool:
        return _ffmpeg() is not None

    def setup(self) -> ToolResult:
        return ToolResult(ok=False, error="ffmpeg 未インストール") if not self.health() else ToolResult(ok=True)

    def run(self, **kwargs) -> ToolResult:
        action = kwargs.get("action", "health")

        if action == "health":
            return ToolResult(ok=self.health(), data={"ffmpeg": bool(self.health())})

        if action == "edit":
            inp = kwargs.get("input", "")
            out = kwargs.get("out", "")
            if not inp or not out:
                return ToolResult(ok=False, error="input / out が必要")
            try:
                resize = None
                if kwargs.get("resize"):
                    w, h = (int(x) for x in str(kwargs["resize"]).split("x"))
                    resize = (w, h)
                trim = None
                if kwargs.get("trim"):
                    s, d = (float(x) for x in str(kwargs["trim"]).split(":"))
                    trim = (s, d)
                ok, msg = edit_media(
                    inp, out, resize=resize, fmt=kwargs.get("format"),
                    speed=float(kwargs.get("speed", 1.0)), trim=trim,
                    burn_text=kwargs.get("text"), subtitles=kwargs.get("subtitles"),
                    audio=kwargs.get("audio"), rotate=int(kwargs.get("rotate", 0)),
                )
                return ToolResult(ok=ok, data={"output": msg if ok else ""},
                                  artifacts=[out] if ok else [],
                                  error="" if ok else msg)
            except Exception as e:  # noqa: BLE001
                return ToolResult(ok=False, error=f"edit失敗: {e}")

        if action == "image_to_video":
            images = kwargs.get("images", [])
            out = kwargs.get("out", "")
            if not images or not out:
                return ToolResult(ok=False, error="images(list) / out が必要")
            ok, msg = image_to_video(list(images), out,
                                     duration=float(kwargs.get("duration", 3.0)),
                                     fmt=kwargs.get("format", "vertical"))
            return ToolResult(ok=ok, data={"output": msg if ok else ""}, artifacts=[out] if ok else [],
                              error="" if ok else msg)

        if action == "composite":
            base, overlay, out = kwargs.get("base", ""), kwargs.get("overlay", ""), kwargs.get("out", "")
            if not (base and overlay and out):
                return ToolResult(ok=False, error="base / overlay / out が必要")
            ok, msg = composite(base, overlay, out, x=int(kwargs.get("x", 0)), y=int(kwargs.get("y", 0)))
            return ToolResult(ok=ok, data={"output": msg if ok else ""}, artifacts=[out] if ok else [],
                              error="" if ok else msg)

        if action == "blender_overlay":
            base = kwargs.get("base", "")
            out = kwargs.get("out", "output/overlay.png")
            if not base:
                return ToolResult(ok=False, error="base が必要")
            info = blender_overlay_script(base, out, scene_type=kwargs.get("scene_type", "abstract_3d"),
                                          frames=int(kwargs.get("frames", 90)))
            return ToolResult(ok=True, data=info)

        return ToolResult(ok=False, error=f"未知 action: {action}")
