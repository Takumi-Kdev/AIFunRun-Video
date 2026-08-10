"""動画スタジオ（多トラック管理）のテスト。"""
from __future__ import annotations

from core import studio


def test_list_accounts():
    a = studio.list_accounts()
    assert "acct_main" in a
    assert "acct_buzz" in a
    assert a["acct_main"]["platform"] == "youtube"


def test_list_lines():
    l = studio.list_lines()
    assert "evergreen" in l
    assert "viral" in l
    assert "strategy" in l["evergreen"]


def test_list_tracks():
    t = studio.list_tracks()
    ids = [x["id"] for x in t]
    assert "track_evergreen_main" in ids
    assert "track_viral_buzz" in ids
    assert "track_news_edu" in ids


def test_get_track():
    t = studio.get_track("track_evergreen_main")
    assert t is not None
    assert t["account"] == "acct_main"
    assert t["template"] == "short_explainer"
    assert studio.get_track("nope") is None


def test_run_track_is_isolated(monkeypatch):
    """トラック実行が分離された出力・状態に記録される。"""
    from core import factory
    class _FR:
        ok = True
        status = "created"
        project_id = "track_track_evergreen_main_x"
        artifacts = ["/tmp/a.mp4"]
        steps = []
    def fake_run(*a, **k):
        # 分離引数が渡ることを確認
        assert k.get("label") == "track_evergreen_main"
        assert k.get("template") == "short_explainer"
        assert "tracks" in (k.get("out_dir") or "")
        return {"ok": True, "project_id": "track_track_evergreen_main_x",
                "status": "created", "artifacts": ["/tmp/a.mp4"], "steps": []}
    monkeypatch.setattr(factory, "run", fake_run)
    res = studio.run_track("track_evergreen_main", "AI解説動画")
    assert res["ok"] is True
    assert res["track"] == "track_evergreen_main"
    assert len(res["runs"]) == 1
    # 分離stateに記録
    st = studio._track_state("track_evergreen_main")
    assert len(st["runs"]) >= 1
    assert st["runs"][-1]["project_id"].startswith("track_")


def test_run_unknown_track():
    res = studio.run_track("nope", "x")
    assert res["ok"] is False


def test_inactive_track_rejected(monkeypatch):
    # active=False のトラックは拒否
    monkeypatch.setattr(studio, "get_track", lambda tid: {"id": tid, "active": False, "template": "ai_visual"})
    res = studio.run_track("track_x", "x")
    assert res["ok"] is False


def test_enqueue_and_run_pending(monkeypatch):
    from core import factory
    calls = []
    def fake_run(*a, **k):
        calls.append(k.get("label"))
        return {"ok": True, "project_id": "p", "status": "created", "artifacts": [], "steps": []}
    monkeypatch.setattr(factory, "run", fake_run)
    r = studio.enqueue_track("track_evergreen_main", "キュー指示A")
    assert r["ok"] is True
    r2 = studio.run_pending("track_evergreen_main")
    assert r2["produced"] >= 1
    assert len(calls) >= 1


def test_studio_status_aggregates():
    st = studio.studio_status()
    assert "accounts" in st
    assert "lines" in st
    assert "tracks" in st
    assert st["track_count"] >= 3
    assert "total_runs" in st
    # 各トラックにメタ情報が付く
    first = st["tracks"][0]
    for k in ("id", "account", "account_name", "content_line", "line_name", "template",
              "character", "active", "run_count", "by_status", "queue_length"):
        assert k in first


def test_action_interface():
    r = studio.action("status", {})
    assert r["ok"] is True and r["data"]["track_count"] >= 3
    r2 = studio.action("list_tracks", {})
    assert r2["ok"] is True
    r3 = studio.action("list_accounts", {})
    assert r3["ok"] is True
    r4 = studio.action("bogus", {})
    assert r4["ok"] is False
