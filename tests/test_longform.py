from pathlib import Path

import pytest

from core import factory, llm, longform
from core.tooling import resolve
from engines import composer


TEMPLATE = {"id": "longform_documentary", "name": "長尺", "resolution": [1920, 1080],
            "fps": 30, "duration_seconds": 600, "ai_policy": "deepseek_only"}


def test_duration_parser_supports_minutes_hours_and_cap():
    assert longform.parse_duration("12分の動画") == 720
    assert longform.parse_duration("1時間30分") == 5400
    assert longform.parse_duration("999時間") == 10800


def test_longform_plan_is_horizontal_chaptered_and_deepseek_only(monkeypatch):
    monkeypatch.setattr("core.llm.chat", lambda *a, **k: None)
    plan = longform.create_longform_plan("AI時代の仕事を10分で解説", TEMPLATE)
    assert plan["duration_seconds"] == 600
    assert plan["resolution"] == [1920, 1080]
    assert len(plan["chapters"]) >= 3
    assert len(plan["shots"]) >= 20
    assert round(sum(float(s["duration"]) for s in plan["shots"])) == 600
    assert plan["ai_policy"]["allowed"] == ["deepseek"]
    assert "text-to-video" in plan["ai_policy"]["forbidden"]


def test_longform_topic_and_metadata_do_not_keep_format_fragments(monkeypatch):
    monkeypatch.setattr(llm, "_api_available", lambda: False)
    monkeypatch.setattr(llm, "chat", lambda *args, **kwargs: None)
    plan = longform.create_longform_plan(
        "AI時代の仕事設計を10分の横動画で解説",
        {"duration_seconds": 600, "fps": 30},
    )
    assert plan["concept"] == "AI時代の仕事設計"
    assert "10分で深掘り" in plan["metadata"]["title"]
    assert "#長尺動画" in plan["metadata"]["hashtags"]
    assert all(s["visual_mode"] in longform.VISUAL_MODES for s in plan["shots"])


def test_factory_auto_detects_longform():
    assert factory._detect_template("横型の長尺動画を作って") == "longform_documentary"
    assert factory._detect_template("AIを10分で解説して") == "longform_documentary"
    assert factory._effective_timeout(90, "longform_documentary", "10分の動画") == 2100
    assert factory._effective_timeout(90, "short_explainer", "10分の動画") == 90


@pytest.mark.skipif(not (resolve("ffmpeg") and resolve("ffprobe")), reason="ffmpeg required")
def test_chapters_and_resume_render(tmp_path, monkeypatch):
    monkeypatch.setattr("core.llm.chat", lambda *a, **k: None)
    template = {**TEMPLATE, "resolution": [480, 270], "fps": 12, "duration_seconds": 8}
    plan = longform.create_longform_plan("横型長尺テストを8秒", template)
    plan["resolution"] = [480, 270]
    plan["fps"] = 12
    plan["shots"] = plan["shots"][:4]
    for shot in plan["shots"]:
        shot["duration"] = 2
    plan["duration_seconds"] = 8
    plan["chapter_marks"] = [{"title": "導入", "start": 0}, {"title": "結論", "start": 4}]
    first = composer.compose(plan, tmp_path)
    assert first["ok"] is True
    assert (tmp_path / "chapters.ffmeta").exists()
    second = composer.compose(plan, tmp_path)
    assert second["ok"] is True
    assert second["resumed_clips"] == 4
    assert Path(second["final"]).exists()
