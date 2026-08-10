"""クリエイティブエンジン（music / imaging / transcribe）のテスト。"""
from __future__ import annotations

import shutil
from pathlib import Path

from engines import music, imaging, transcribe


def _need_ffmpeg():
    if not shutil.which("ffmpeg"):
        import pytest
        pytest.skip("ffmpeg なし")


def _make_img(path: Path):
    from PIL import Image
    Image.new("RGB", (200, 200), "green").save(path)


def _make_video(tmp_path):
    from engines import media_edit
    img = tmp_path / "v.png"
    _make_img(img)
    out = tmp_path / "v.mp4"
    ok, _ = media_edit.edit_media(str(img), str(out), fmt="vertical")
    return out


# ---- music ----

def test_music_generate(tmp_path):
    _need_ffmpeg()
    out = tmp_path / "bgm.mp3"
    ok, msg = music.generate("calm", str(out), duration=2.0)
    assert ok, msg
    assert out.exists() and out.stat().st_size > 0


def test_music_moods():
    assert "calm" in music._MOOD_CHORDS
    assert "epic" in music._MOOD_CHORDS


def test_music_add_bgm(tmp_path):
    _need_ffmpeg()
    v = _make_video(tmp_path)
    bgm = tmp_path / "bgm.mp3"
    music.generate("upbeat", str(bgm), duration=2.0)
    out = tmp_path / "with_bgm.mp4"
    ok, msg = music.add_bgm(str(v), str(bgm), str(out), 0.3)
    assert ok, msg
    assert out.exists() and out.stat().st_size > 0


def test_music_tool_actions(tmp_path):
    _need_ffmpeg()
    t = music.MusicTool()
    out = tmp_path / "m.mp3"
    r = t.run(action="generate", mood="epic", out=str(out), duration=1.5)
    assert r.ok is True
    assert out.exists()
    rh = t.run(action="health")
    assert rh.ok is True
    assert "moods" in rh.data


# ---- imaging ----

def test_imaging_generate(tmp_path):
    out = tmp_path / "img.png"
    ok, msg = imaging.procedural_image("サイバーパンクな背景", str(out))
    assert ok, msg
    assert out.exists() and out.stat().st_size > 0
    from PIL import Image
    im = Image.open(out)
    assert im.size == (1080, 1920)


def test_imaging_variety():
    a = imaging.procedural_image("夜の街", "output/_i1.png")
    b = imaging.procedural_image("朝の森", "output/_i2.png")
    assert a[0] and b[0]
    from PIL import Image
    import hashlib
    h1 = hashlib.md5(open("output/_i1.png", "rb").read()).hexdigest()
    h2 = hashlib.md5(open("output/_i2.png", "rb").read()).hexdigest()
    assert h1 != h2  # 異なるプロンプト → 異なる画像
    import os
    for f in ("output/_i1.png", "output/_i2.png"):
        try: os.remove(f)
        except OSError: pass


def test_imaging_thumbnail(tmp_path):
    _need_ffmpeg()
    v = _make_video(tmp_path)
    out = tmp_path / "th.jpg"
    ok, msg = imaging.extract_thumbnail(str(v), str(out))
    assert ok, msg
    assert out.exists()


def test_imaging_tool():
    t = imaging.ImagingTool()
    r = t.run(action="generate", prompt="テスト画像", out="output/_img_t.png")
    assert r.ok is True
    import os
    try: os.remove("output/_img_t.png")
    except OSError: pass


def test_imaging_tool_requires_prompt():
    t = imaging.ImagingTool()
    r = t.run(action="generate")
    assert r.ok is False


# ---- transcribe ----

def test_transcribe_health():
    t = transcribe.TranscribeTool()
    rh = t.run(action="health")
    assert "faster_whisper" in rh.data


def test_transcribe_unavailable_is_graceful(tmp_path):
    # faster-whisper が無ければ graceful なエラー（例外でない）
    t = transcribe.TranscribeTool()
    media = tmp_path / "x.mp4"
    media.write_bytes(b"")
    r = t.run(action="transcribe", media=str(media), out=str(tmp_path / "s.srt"))
    if not transcribe._whisper_available():
        assert r.ok is False
        assert "faster-whisper" in r.error
    else:
        # whisper 導入済みなら実行される（結果は空メディアでも例外を出さない）
        assert r.ok in (True, False)
