"""CreativePlanを、人が編集せずに視聴可能な一本の作品へ構成する。"""
from __future__ import annotations

import json
import math
import shutil
from pathlib import Path

from core import process
from core.tooling import resolve
from core.tool_layer import Tool, ToolResult


def _font(size: int):
    from PIL import ImageFont
    candidates = [
        Path("C:/Windows/Fonts/YuGothB.ttc"), Path("C:/Windows/Fonts/meiryob.ttc"),
        Path("C:/Windows/Fonts/YuGothM.ttc"), Path("C:/Windows/Fonts/meiryo.ttc"),
    ]
    for path in candidates:
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size=size)
            except OSError:
                continue
    return ImageFont.load_default()


def _wrap(text: str, limit: int = 14) -> list[str]:
    text = str(text or "").strip()
    if not text:
        return [""]
    return [text[i:i + limit] for i in range(0, len(text), limit)][:4]


def render_frame(shot: dict, plan: dict, out: Path, index: int) -> str:
    """一貫したvisual bibleを保ちながら、ショットごとに異なる画面を描く。"""
    from PIL import Image, ImageDraw
    target_w, target_h = plan.get("resolution", [1080, 1920])
    scale = min(1.0, 960 / max(target_w, target_h))
    width, height = max(360, int(target_w * scale)), max(360, int(target_h * scale))
    colors = (plan.get("visual_bible") or {}).get("palette") or ["#050816", "#23D5FF", "#8A5CFF", "#F4F7FF"]
    bg, accent, violet, foreground = (colors + ["#050816", "#23D5FF", "#8A5CFF", "#F4F7FF"])[:4]
    image = Image.new("RGB", (width, height), bg)
    draw = ImageDraw.Draw(image, "RGBA")

    # 深度のある光、軌道、グリッド。ショットごとに重心を移して静止画感を減らす。
    center_x = int(width * (0.30 + 0.08 * (index % 5)))
    center_y = int(height * (0.27 + 0.06 * ((index * 3) % 5)))
    max_r = int(min(width, height) * 0.62)
    for ring in range(18, 0, -1):
        radius = int(max_r * ring / 18)
        alpha = int(3 + 18 * (1 - ring / 18))
        draw.ellipse((center_x-radius, center_y-radius, center_x+radius, center_y+radius), fill=accent + f"{alpha:02x}")
    for grid in range(1, 9):
        y = int(height * grid / 10)
        draw.line((0, y, width, y), fill=(120, 145, 190, 12), width=1)
    orbit = int(min(width, height) * (0.16 + 0.018 * index))
    draw.ellipse((center_x-orbit, center_y-orbit, center_x+orbit, center_y+orbit), outline=accent + "99", width=max(1, width // 360))
    draw.arc((center_x-orbit*2, center_y-orbit*2, center_x+orbit*2, center_y+orbit*2), index*37, index*37+210, fill=violet + "AA", width=max(2, width // 220))
    dot_x = center_x + int(math.cos(index * 1.17) * orbit * 1.8)
    dot_y = center_y + int(math.sin(index * 1.17) * orbit * 1.8)
    draw.ellipse((dot_x-7, dot_y-7, dot_x+7, dot_y+7), fill=accent)

    pad = int(width * 0.075)
    kicker_font = _font(max(12, int(width * 0.026)))
    title_font = _font(max(28, int(width * 0.072)))
    body_font = _font(max(17, int(width * 0.036)))
    draw.text((pad, pad), f"SCENE {index + 1:02d}  //  {str(shot.get('purpose', 'STORY')).upper()}", font=kicker_font, fill=accent)
    lines = _wrap(shot.get("on_screen_text") or shot.get("narration"), 13 if target_h >= target_w else 22)
    line_h = int(title_font.size * 1.25)
    text_y = int(height * (0.55 if target_h >= target_w else 0.48))
    for line_no, line in enumerate(lines):
        draw.text((pad, text_y + line_no * line_h), line, font=title_font, fill=foreground)
    body_y = text_y + len(lines) * line_h + int(height * 0.035)
    draw.line((pad, body_y, pad + int(width * 0.18), body_y), fill=accent, width=max(2, width // 260))
    draw.text((pad, body_y + int(height * 0.025)), str(shot.get("motion", "flow")).upper(), font=body_font, fill=violet)
    draw.text((pad, height - pad - body_font.size), str(plan.get("concept", "AIFunRun Creative"))[:48], font=body_font, fill=(210, 220, 242, 130))
    out.parent.mkdir(parents=True, exist_ok=True)
    image.save(out, quality=94)
    return str(out)


def _srt_time(seconds: float) -> str:
    millis = int(round(seconds * 1000))
    hours, millis = divmod(millis, 3_600_000)
    minutes, millis = divmod(millis, 60_000)
    secs, millis = divmod(millis, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def write_subtitles(plan: dict, out: Path) -> str:
    cursor, rows = 0.0, []
    for index, shot in enumerate(plan.get("shots", []), 1):
        duration = float(shot.get("duration", 3))
        rows += [str(index), f"{_srt_time(cursor)} --> {_srt_time(cursor + duration)}", str(shot.get("narration", "")), ""]
        cursor += duration
    out.write_text("\n".join(rows), encoding="utf-8")
    return str(out)


def _run_ffmpeg(args: list[str], timeout_ms: int = 240_000) -> tuple[bool, str]:
    ffmpeg = resolve("ffmpeg")
    if not ffmpeg:
        return False, "ffmpegが見つかりません"
    result = process.run_command([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", *args], timeout_ms=timeout_ms,
                                 max_output_bytes=300_000, kill_process_tree=True)
    return result.ok, result.error or result.combined[-600:]


def compose(plan: dict, out_dir: Path, voice: str | None = None) -> dict:
    """設計図からショット、字幕、音声、BGMを統合したfinal.mp4を作る。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    frames_dir, clips_dir = out_dir / "storyboard", out_dir / "_clips"
    frames_dir.mkdir(exist_ok=True)
    clips_dir.mkdir(exist_ok=True)
    width, height = (int(v) for v in plan.get("resolution", [1080, 1920]))
    fps = int(plan.get("fps", 30))
    frame_paths, clip_paths = [], []
    errors = []
    for index, shot in enumerate(plan.get("shots", [])):
        frame = Path(render_frame(shot, plan, frames_dir / f"shot_{index + 1:02d}.png", index))
        frame_paths.append(str(frame))
        clip = clips_dir / f"shot_{index + 1:02d}.mp4"
        duration = max(1.0, float(shot.get("duration", 3)))
        total_frames = max(2, round(duration * fps))
        zoom = "min(zoom+0.0008,1.08)" if index % 2 == 0 else "if(lte(zoom,1.0),1.08,max(1.0,zoom-0.0008))"
        vf = (f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},"
              f"zoompan=z='{zoom}':d={total_frames}:s={width}x{height}:fps={fps},format=yuv420p")
        ok, detail = _run_ffmpeg(["-loop", "1", "-i", str(frame), "-vf", vf, "-t", f"{duration:.3f}",
                                  "-an", "-c:v", "libx264", "-preset", "veryfast", str(clip)])
        if ok and clip.exists():
            clip_paths.append(str(clip.resolve()))
        else:
            errors.append(f"shot {index + 1}: {detail}")
    if not clip_paths:
        return {"ok": False, "errors": errors or ["ショットを映像化できませんでした"], "artifacts": frame_paths}

    concat = clips_dir / "concat.txt"
    concat.write_text("\n".join(f"file '{path.replace(chr(39), chr(39)*2)}'" for path in clip_paths), encoding="utf-8")
    visual = out_dir / "visual_master.mp4"
    ok, detail = _run_ffmpeg(["-f", "concat", "-safe", "0", "-i", str(concat), "-c:v", "libx264",
                              "-preset", "veryfast", "-pix_fmt", "yuv420p", str(visual)])
    if not ok:
        return {"ok": False, "errors": errors + [detail], "artifacts": frame_paths}

    subtitle = Path(write_subtitles(plan, out_dir / "subtitles.srt"))
    duration = float(plan.get("duration_seconds") or sum(float(s.get("duration", 3)) for s in plan.get("shots", [])))
    bgm = out_dir / "score.mp3"
    from . import music
    mood = "epic" if "高揚" in plan.get("emotional_arc", []) else "upbeat"
    music_ok, music_detail = music.generate(mood, str(bgm), duration=duration + 1, volume=0.34)
    if not music_ok:
        errors.append(f"music: {music_detail}")

    final = out_dir / "final.mp4"
    voice_ok = bool(voice and Path(voice).exists())
    if voice_ok and music_ok:
        args = ["-i", str(visual), "-i", str(voice), "-i", str(bgm), "-filter_complex",
                "[1:a]volume=1.0[v];[2:a]volume=0.16[b];[v][b]amix=inputs=2:duration=longest:dropout_transition=2[a]",
                "-map", "0:v", "-map", "[a]", "-t", f"{duration:.3f}", "-c:v", "copy", "-c:a", "aac",
                "-movflags", "+faststart", str(final)]
    elif voice_ok or music_ok:
        audio = str(voice) if voice_ok else str(bgm)
        args = ["-i", str(visual), "-i", audio, "-map", "0:v", "-map", "1:a", "-t", f"{duration:.3f}",
                "-c:v", "copy", "-c:a", "aac", "-movflags", "+faststart", str(final)]
    else:
        shutil.copy2(visual, final)
        args = []
    if args:
        ok, detail = _run_ffmpeg(args)
        if not ok:
            errors.append(f"master: {detail}")
            shutil.copy2(visual, final)
    quality = inspect_video(final, expected=(width, height), target_duration=duration)
    return {
        "ok": final.exists() and quality.get("playable", False),
        "final": str(final), "quality": quality, "errors": errors,
        "artifacts": [*frame_paths, str(subtitle), str(visual), *( [str(bgm)] if bgm.exists() else [] ), str(final)],
    }


def inspect_video(path: Path | str, expected: tuple[int, int] | None = None, target_duration: float | None = None) -> dict:
    ffprobe = resolve("ffprobe")
    path = Path(path)
    if not ffprobe or not path.exists():
        return {"playable": False, "score": 0, "issues": ["ffprobeまたは動画がありません"]}
    result = process.run_command([ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
                                 timeout_ms=30_000, max_output_bytes=150_000)
    try:
        data = json.loads(result.stdout)
    except (ValueError, TypeError):
        return {"playable": False, "score": 0, "issues": [result.error or "解析不能"]}
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), {})
    audio = next((s for s in streams if s.get("codec_type") == "audio"), {})
    duration = float((data.get("format") or {}).get("duration") or video.get("duration") or 0)
    issues, score = [], 45 if video else 0
    if audio:
        score += 20
    else:
        issues.append("音声トラックなし")
    if expected and (video.get("width"), video.get("height")) == expected:
        score += 20
    elif expected:
        issues.append(f"解像度差異: {video.get('width')}x{video.get('height')}")
    if duration > 0 and (not target_duration or abs(duration - target_duration) <= max(1.5, target_duration * .12)):
        score += 15
    else:
        issues.append(f"尺差異: {duration:.2f}秒")
    return {"playable": bool(video and duration > 0), "score": min(score, 100), "duration": round(duration, 3),
            "width": video.get("width"), "height": video.get("height"), "video_codec": video.get("codec_name"),
            "audio_codec": audio.get("codec_name"), "size_bytes": path.stat().st_size, "issues": issues}


class ComposerTool(Tool):
    name = "composer"
    description = "AIのCreativePlanからショット・字幕・音声・BGMを統合し完成動画を創作"

    def health(self) -> bool:
        return bool(resolve("ffmpeg") and resolve("ffprobe"))

    def run(self, **kwargs) -> ToolResult:
        action = kwargs.get("action", "compose")
        if action == "health":
            return ToolResult(ok=self.health(), data={"ffmpeg": bool(resolve("ffmpeg")), "ffprobe": bool(resolve("ffprobe"))})
        if action == "inspect":
            data = inspect_video(str(kwargs.get("video", "")))
            return ToolResult(ok=bool(data.get("playable")), data=data, error="" if data.get("playable") else "動画品質NG")
        if action == "compose":
            plan = kwargs.get("plan") or {}
            result = compose(plan, Path(str(kwargs.get("out_dir", "output/composed"))), kwargs.get("voice"))
            return ToolResult(ok=result["ok"], data=result, artifacts=result.get("artifacts", []),
                              error="; ".join(result.get("errors", [])))
        return ToolResult(ok=False, error=f"未知 action: {action}")
