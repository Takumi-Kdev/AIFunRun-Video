from core import creative


TEMPLATE = {"id": "test", "name": "テスト", "pattern": "ai", "resolution": [360, 640], "fps": 24, "voice": "auto"}


def test_one_line_intent_becomes_complete_plan(monkeypatch):
    monkeypatch.setattr("core.llm.chat", lambda *a, **k: None)
    plan = creative.create_plan("宇宙旅行を20秒のTikTok動画にして", TEMPLATE)
    assert plan["duration_seconds"] == 20
    assert plan["platform"] == "TikTok"
    assert len(plan["shots"]) >= 4
    assert all(shot["narration"] and shot["visual_prompt"] and shot["camera"] for shot in plan["shots"])
    assert plan["autonomy"]["human_required"] == ["外部公開の最終承認のみ"]


def test_plan_is_saved_for_human_and_engines(tmp_path, monkeypatch):
    monkeypatch.setattr("core.llm.chat", lambda *a, **k: None)
    plan = creative.create_plan("未来の教育", TEMPLATE)
    artifacts = creative.save_plan(plan, tmp_path)
    assert (tmp_path / "creative_plan.json").exists()
    assert (tmp_path / "storyboard.md").exists()
    assert len(artifacts) == 2


def test_llm_plan_is_normalized(monkeypatch):
    monkeypatch.setattr("core.llm.chat", lambda *a, **k: '{"concept":"新しい構想","shots":[{"narration":"a"},{"narration":"b"},{"narration":"c"}]}')
    plan = creative.create_plan("テスト動画", TEMPLATE)
    assert plan["source"] == "deepseek-director"
    assert plan["concept"] == "新しい構想"
    assert len(plan["shots"]) == 3
    assert round(sum(s["duration"] for s in plan["shots"])) == plan["duration_seconds"]
