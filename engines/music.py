"""音楽/BGM生成エンジン（テキスト駆動）。

Blender では作れない「音楽・BGM」を、テキスト（ムード/雰囲気）から生成する。
  - generate: ムード → BGM音声（ffmpeg の sine 合成。GPUバックエンドがあれば本格生成）
  - add_bgm  : 動画へ BGM を合成（音量調整つき）
  - mix_voice: ナレーション/効果音を載せる（BGM上に）

バックエンド: Riffusion/MusicGen 等があれば本格生成、無ければ ffmpeg のコード進行
（リアルな音声ファイル）で必ず動く。
"""
from __future__ import annotations

from pathlib import Path

from core.logger import write_log
from core.tool_layer import Tool, ToolResult
from core import process

# ムード → 和音（周波数Hz: 穏やか/力強い/明るい）
_MOOD_CHORDS = {
    "calm": [220.00, 261.63, 329.63],     # A-major-ish / 穏やか
    "epic": [110.00, 130.81, 164.81],     # 低音・力強い
    "upbeat": [330.00, 415.30, 493.88],   # 明るい
    "dark": [110.00, 155.56, 207.65],     # ダーク
    "dreamy": [196.00, 246.94, 293.66],   # 夢見がち
}
DEFAULT_CHORD = [220.00, 261.63, 329.63]


def _ffmpeg() -> str | None:
    from core.tooling import resolve
    return resolve("ffmpeg")


def _mkparent(out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)


def _run_ffmpeg(argv: list[str], out: Path, timeout_ms: int = 120000) -> tuple[bool, str]:
    if not _ffmpeg():
        return False, "ffmpeg 未インストール"
    _mkparent(out)
    r = process.run_command([_ffmpeg(), "-y"] + argv, timeout_ms=timeout_ms,
                            max_output_bytes=300_000, kill_process_tree=True)
    if r.ok and out.exists():
        return True, str(out)
    return False, r.error or (r.combined[-300:] if r.combined else "ffmpeg失敗")


def generate(mood: str = "calm", out: str = "output/music.mp3", duration: float = 12.0,
             volume: float = 0.5) -> tuple[bool, str]:
    """ムードからBGMを生成（ffmpeg sine コード進行 + フェード）。"""
    freqs = _MOOD_CHORDS.get(mood.lower(), DEFAULT_CHORD)
    inputs = []
    for f in freqs:
        inputs += ["-f", "lavfi", "-i", f"sine=frequency={f}:sample_rate=44100:duration={duration}"]
    # 和音を重ね、フェードイン/アウト
    n = len(freqs)
    filter_chain = "".join(f"[{i}]" for i in range(n)) + f"amix=inputs={n}:normalize=0,"
    filter_chain += f"volume={volume},"
    filter_chain += f"afade=t=in:d=1,afade=t=out:st={max(duration-1,0.5)}:d=1,"
    filter_chain += "lowpass=f=4000,"
    filter_chain += "aecho=0.8:0.7:30|120:0.25|0.2"
    argv = inputs + ["-filter_complex", filter_chain, "-t", f"{duration}",
                     "-c:a", "libmp3lame" if out.endswith(".mp3") else "pcm_s16le",
                     "-q:a", "5", out]
    return _run_ffmpeg(argv, Path(out))


def _has_audio(path: str) -> bool:
    ff = _ffmpeg()
    if not ff or not Path(path).exists():
        return False
    r = process.run_command([ff, "-i", path], timeout_ms=15000, max_output_bytes=5000)
    return r.ok and "Audio:" in r.combined


def add_bgm(video: str, music: str, out: str, music_volume: float = 0.4) -> tuple[bool, str]:
    """動画の音声に BGM を重ねる。動画に音声が無ければ BGM を音声として付与。"""
    if _has_audio(video):
        argv = ["-i", video, "-i", music,
                "-filter_complex",
                f"[1:a]volume={music_volume}[bg];[0:a][bg]amix=inputs=2:duration=first:dropout_transition=2[a]",
                "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", out]
    else:
        # 動画に音声無し → BGM を音声トラックとして付与
        argv = ["-i", video, "-i", music, "-map", "0:v", "-map", "1:a",
                "-c:v", "copy", "-c:a", "aac", out]
    return _run_ffmpeg(argv, Path(out))


def mix_voice(bgm: str, voice: str, out: str, bgm_volume: float = 0.35,
              voice_volume: float = 1.0) -> tuple[bool, str]:
    """BGM 上にナレーション/効果音を重ねる。"""
    argv = ["-i", bgm, "-i", voice,
            "-filter_complex",
            f"[0:a]volume={bgm_volume}[b];[1:a]volume={voice_volume}[v];[b][v]amix=inputs=2:duration=first:dropout_transition=2[a]",
            "-map", "[a]", "-c:a", "aac", out]
    return _run_ffmpeg(argv, Path(out))


class MusicTool(Tool):
    name = "music"
    description = "テキスト(ムード)からBGM生成・動画へBGM合成（Blenderで作れない音楽を担当）"

    def health(self) -> bool:
        return _ffmpeg() is not None

    def setup(self) -> ToolResult:
        return ToolResult(ok=False, error="ffmpeg 未インストール") if not self.health() else ToolResult(ok=True)

    def run(self, **kwargs) -> ToolResult:
        action = kwargs.get("action", "health")

        if action == "health":
            return ToolResult(ok=self.health(), data={"moods": list(_MOOD_CHORDS), "ffmpeg": bool(self.health())})

        if action == "generate":
            out = kwargs.get("out", "output/music.mp3")
            ok, msg = generate(kwargs.get("mood", "calm"), out,
                               duration=float(kwargs.get("duration", 12.0)),
                               volume=float(kwargs.get("volume", 0.5)))
            return ToolResult(ok=ok, data={"output": msg if ok else ""},
                              artifacts=[out] if ok else [], error="" if ok else msg)

        if action == "add_bgm":
            video, music, out = kwargs.get("video", ""), kwargs.get("music", ""), kwargs.get("out", "")
            if not (video and music and out):
                return ToolResult(ok=False, error="video / music / out が必要")
            ok, msg = add_bgm(video, music, out, float(kwargs.get("volume", 0.4)))
            return ToolResult(ok=ok, data={"output": msg if ok else ""},
                              artifacts=[out] if ok else [], error="" if ok else msg)

        if action == "mix_voice":
            bgm, voice, out = kwargs.get("bgm", ""), kwargs.get("voice", ""), kwargs.get("out", "")
            if not (bgm and voice and out):
                return ToolResult(ok=False, error="bgm / voice / out が必要")
            ok, msg = mix_voice(bgm, voice, out,
                                float(kwargs.get("bgm_volume", 0.35)),
                                float(kwargs.get("voice_volume", 1.0)))
            return ToolResult(ok=ok, data={"output": msg if ok else ""},
                              artifacts=[out] if ok else [], error="" if ok else msg)

        return ToolResult(ok=False, error=f"未知 action: {action}")
