"""動画創作ファクトリー（core/factory.py）のテスト。"""
from __future__ import annotations

import shutil
from pathlib import Path

from core import factory


def test_list_templates():
    tpl = factory.list_templates()
    ids = [t.get("id") for t in tpl]
    assert "short_explainer" in ids
    assert "news_presenter" in ids
    assert "ai_visual" in ids


def test_load_template():
    t = factory.load_template("news_presenter")
    assert t is not None
    assert t["pattern"] == "human"
    assert "render" in t["steps"]


def test_detect_template():
    assert factory._detect_template("ニュース風の動画を作って") == "news_presenter"
    assert factory._detect_template("幻想的なAI感のあるショート") == "ai_visual"
    assert factory._detect_template("何か解説動画") == "short_explainer"


def test_factory_run_produces_report():
    res = factory.run("AIツールの基本を解説するショート動画を作って", template="ai_visual")
    assert res["ok"] is True
    assert res["template"] == "ai_visual"
    assert res["pattern"] == "ai"
    assert isinstance(res["script"], list) and res["script"]
    assert isinstance(res["steps"], list) and res["steps"]
    # 全ステーションが結果を持つ
    stations = [s["station"] for s in res["steps"]]
    assert "plan" in stations
    assert "background" in stations
    assert "voice" in stations
    # 実ファイル（script.txt は必ず、背景は ffmpeg があれば）が生成されている
    assert any(Path(a).name == "script.txt" for a in res["artifacts"])


def test_factory_run_short_explainer():
    # フルステーション（assets/scene/render 含む）が安全に完走する
    res = factory.run("マスコットキャラが話す解説ショート", template="short_explainer")
    assert res["ok"] is True
    stations = {s["station"]: s["ok"] for s in res["steps"]}
    assert "plan" in stations
    assert "assets" in stations  # フォールバックでも必ず結果を持つ
    assert "scene" in stations
    assert "render" in stations
    assert "background" in stations


def test_factory_action_interface():
    r = factory.action("list", {})
    assert r["ok"] is True
    r2 = factory.action("status", {})
    assert r2["ok"] is True
    assert "total_runs" in r2["data"]
    r3 = factory.action("bogus", {})
    assert r3["ok"] is False
