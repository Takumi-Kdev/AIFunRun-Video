from pathlib import Path

import pytest

from core import creative
from core.tooling import resolve
from engines import composer


def _plan(monkeypatch):
    monkeypatch.setattr("core.llm.chat", lambda *a, **k: None)
    template = {"name": "test", "pattern": "ai", "resolution": [360, 640], "fps": 15, "voice": "auto"}
    plan = creative.create_plan("光の未来を8秒で", template)
    plan["shots"] = plan["shots"][:4]
    for shot in plan["shots"]:
        shot["duration"] = 2
    plan["duration_seconds"] = 8
    return plan


def test_render_frame_creates_visual(tmp_path, monkeypatch):
    plan = _plan(monkeypatch)
    path = composer.render_frame(plan["shots"][0], plan, tmp_path / "frame.png", 0)
    assert Path(path).stat().st_size > 1000


@pytest.mark.skipif(not (resolve("ffmpeg") and resolve("ffprobe")), reason="ffmpeg required")
def test_compose_creates_playable_final_with_quality(tmp_path, monkeypatch):
    plan = _plan(monkeypatch)
    result = composer.compose(plan, tmp_path)
    assert result["ok"] is True
    assert Path(result["final"]).exists()
    assert result["quality"]["playable"] is True
    assert result["quality"]["score"] >= 80
    assert result["quality"]["width"] == 360
    assert result["quality"]["height"] == 640
    assert (tmp_path / "subtitles.srt").exists()


def test_portable_tools_are_shared_from_aifunrun_installation():
    assert resolve("ffmpeg")
    assert resolve("ffprobe")
    assert resolve("blender")
