"""メディア編集・合成エンジン（engines/media_edit）のテスト。"""
from __future__ import annotations

import shutil
from pathlib import Path

from engines import media_edit


def _need_ffmpeg():
    if not shutil.which("ffmpeg"):
        import pytest
        pytest.skip("ffmpeg なし")


def _make_img(path: Path, color="red"):
    from PIL import Image
    img = Image.new("RGB", (200, 200), color)
    img.save(path)


def test_edit_media_resize(tmp_path):
    _need_ffmpeg()
    img = tmp_path / "in.png"
    _make_img(img)
    out = tmp_path / "out.mp4"
    ok, msg = media_edit.edit_media(str(img), str(out), fmt="vertical")
    assert ok, msg
    assert out.exists() and out.stat().st_size > 0


def test_edit_media_speed_and_text(tmp_path):
    _need_ffmpeg()
    img = tmp_path / "in.png"
    _make_img(img)
    out = tmp_path / "out.mp4"
    ok, msg = media_edit.edit_media(str(img), str(out), fmt="square", speed=2.0, burn_text="こんにちは")
    assert ok, msg
    assert out.exists()


def test_image_to_video_slideshow(tmp_path):
    _need_ffmpeg()
    a, b = tmp_path / "a.png", tmp_path / "b.png"
    _make_img(a, "red")
    _make_img(b, "blue")
    out = tmp_path / "slide.mp4"
    ok, msg = media_edit.image_to_video([str(a), str(b)], str(out), duration=1.0, fmt="vertical")
    assert ok, msg
    assert out.exists() and out.stat().st_size > 0


def test_image_to_video_relative_paths(tmp_path, monkeypatch):
    # 回帰: 相対パス出力でも concat のパス解決が壊れないこと
    _need_ffmpeg()
    monkeypatch.chdir(tmp_path)
    a, b = tmp_path / "a.png", tmp_path / "b.png"
    _make_img(a, "red")
    _make_img(b, "blue")
    out = "slide.mp4"  # 相対パス
    ok, msg = media_edit.image_to_video([str(a), str(b)], out, duration=1.0)
    assert ok, msg
    assert (tmp_path / "slide.mp4").exists()


def test_composite(tmp_path):
    _need_ffmpeg()
    a = tmp_path / "a.png"
    _make_img(a)
    base = tmp_path / "base.mp4"
    ok, _ = media_edit.edit_media(str(a), str(base), fmt="vertical")
    assert ok
    # オーバーレイ(半透明PNG動画)として画像をループ
    ov = tmp_path / "overlay.mp4"
    from engines import media_edit as me
    ok2, _ = me.edit_media(str(a), str(ov), fmt="vertical", speed=1.0)
    out = tmp_path / "comp.mp4"
    ok3, msg = media_edit.composite(str(base), str(ov), str(out))
    assert ok3, msg
    assert out.exists() and out.stat().st_size > 0


def test_media_edit_tool_actions(tmp_path):
    from core.tool_layer import ToolResult
    _need_ffmpeg()
    img = tmp_path / "in.png"
    _make_img(img)
    out = tmp_path / "tool_out.mp4"
    t = media_edit.MediaEditTool()
    r = t.run(action="edit", input=str(img), out=str(out), format="horizontal")
    assert r.ok is True
    assert out.exists()
    # health
    r2 = t.run(action="health")
    assert r2.ok is True


def test_media_edit_tool_requires_input():
    t = media_edit.MediaEditTool()
    r = t.run(action="edit", out="x.mp4")  # input なし
    assert r.ok is False
