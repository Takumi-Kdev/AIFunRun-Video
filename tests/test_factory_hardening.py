"""工場の堅牢化・量産・追加機能のテスト（高速・フェイクレジストリ使用）。"""
from __future__ import annotations

from core import factory
from core.tool_layer import ToolResult


class _FR(ToolResult):
    def __init__(self, ok=True, data=None, error="", artifacts=None):
        super().__init__(ok=ok, data=data if data is not None else {}, error=error,
                         artifacts=artifacts or [])


class FakeRegistry:
    """各エンジンが速く決定的な結果を返すフェイク。"""
    def call(self, name, **kw):
        if name == "gen3d":
            return _FR(ok=True, data={"glb": "/tmp/model.glb", "placeholder_script": "# x"})
        if name in ("animate",):
            action = kw.get("action", "")
            if action == "render":
                return _FR(ok=True, data={"code": "bpy.ops.render.render(animation=True)"})
            return _FR(ok=True, data={"code": "# scene/shot"})
        if name == "tts":
            return _FR(ok=True, artifacts=["/tmp/voice.wav"])
        if name == "video2d":
            return _FR(ok=True, artifacts=["/tmp/background.mp4"])
        if name == "video_edit":
            return _FR(ok=True, artifacts=["/tmp/edited.mp4"])
        if name == "moderation":
            return _FR(ok=True, data={"ok": True})
        return _FR(ok=True, data={})


def _fast(monkeypatch):
    monkeypatch.setattr(factory, "_reg", lambda: FakeRegistry())


def test_validate_template():
    t = {"id": "x", "name": "X", "pattern": "a", "resolution": [1080, 1920],
         "fps": 30, "steps": ["plan", "background"]}
    assert factory.validate_template(t)["ok"] is True
    bad = dict(t, steps=["not_a_station"])
    assert factory.validate_template(bad)["ok"] is False
    bad2 = dict(t, resolution=[-1, 0])
    assert factory.validate_template(bad2)["ok"] is False


def test_load_characters():
    chars = factory.load_characters()
    assert "mascot" in chars
    assert "human_avatar" in chars
    assert chars["mascot"]["voice"] == "kokoro"


def test_resolve_character():
    from core.factory import _resolve_character
    c = _resolve_character({"character": "mascot"})
    assert c["name"] == "3Dマスコット"
    assert _resolve_character({"character": "unknown_x"}) is not None
    assert _resolve_character({}) is None


def test_run_fast_with_all_stations(monkeypatch):
    _fast(monkeypatch)
    res = factory.run("幻想的なショート動画", template="ai_visual")
    assert res["ok"] is True
    assert "character" in res
    assert "moderate" in [s["station"] for s in res["steps"]]
    # ai_visual: plan/moderate/background/voice/edit
    stations = {s["station"] for s in res["steps"]}
    assert {"plan", "background", "voice", "edit", "moderate"} <= stations


def test_run_batch_fast(monkeypatch):
    _fast(monkeypatch)
    res = factory.run_batch(3, "解説ショート", template="ai_visual")
    assert res["count"] == 3
    assert res["succeeded"] == 3
    assert len(res["reports"]) == 3


def test_status_shape():
    st = factory.status()
    assert "total_runs" in st
    assert "by_status" in st
    assert "by_template" in st
    assert "recent" in st


def test_action_batch_and_status(monkeypatch):
    _fast(monkeypatch)
    r = factory.action("batch", {"count": 2, "instruction": "テスト"})
    assert r["ok"] is True
    assert r["data"]["count"] == 2
    r2 = factory.action("status", {})
    assert r2["ok"] is True
    r3 = factory.action("characters", {})
    assert r3["ok"] is True
    r4 = factory.action("bogus", {})
    assert r4["ok"] is False


def test_action_validate():
    r = factory.action("validate", {"template": "short_explainer"})
    assert r["data"]["ok"] is True


def test_run_guard_timeout(monkeypatch):
    # 1工程が固まっても全体が止まらないことを確認（タイムアウト）
    import time

    def slow_call():
        time.sleep(30)  # 遅すぎる
        return _FR(ok=True)
    monkeypatch.setattr(factory, "_reg", lambda: FakeRegistry())
    # タイムアウトは factory._run_guarded の単体で検証
    st, _ = factory._run_guarded(slow_call, timeout=0.1, retries=0)
    assert st == "timeout"
