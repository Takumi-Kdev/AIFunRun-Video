"""CAD（OpenSCAD/FreeCAD）とモデリング振り分けルーターのテスト。"""
from __future__ import annotations

from engines import cad
from core import model_router


# ---- OpenSCAD スクリプト生成 ----

def test_openscad_gear():
    code = cad.build_openscad("歯車のモデル")
    assert "module gear" in code or "teeth" in code
    # 有効なテキスト（.scad として保存可能）
    assert code.strip()


def test_openscad_box():
    code = cad.build_openscad("筐体を設計して")
    assert "difference()" in code
    assert "cube([w,d,h])" in code


def test_openscad_vase():
    code = cad.build_openscad("花瓶を作って")
    assert "linear_extrude" in code


def test_openscad_generic_is_valid():
    code = cad.build_openscad("何かの3Dモデル")
    assert "union(){" in code
    assert "translate" in code


def test_render_openscad_fallback(monkeypatch):
    # openscad 未導入でもスクリプトを保存し graceful な結果を返す
    monkeypatch.setattr(cad, "_which", lambda _cmd: False)
    ok, msg = cad.render_openscad(cad.build_openscad("歯車"), "/tmp/_cad_test.stl")
    assert ok is False  # 未導入ならエラー
    assert "openscad" in msg


# ---- FreeCAD スクリプト生成 ----

def test_freecad_script():
    code = cad.build_freecad("筐体", "/tmp/x.stl")
    assert "import FreeCAD" in code
    assert "Part.export" in code
    assert "/tmp/x.stl" in code


# ---- CAD tool ----

def test_cad_tool_generates_script(monkeypatch):
    monkeypatch.setattr(cad, "_which", lambda _cmd: False)
    t = cad.CadTool()
    r = t.run(action="openscad_generate", prompt="歯車", out="/tmp/_g.stl")
    assert r.ok is False  # openscad 未導入 → スクリプトは生成される
    assert r.artifacts  # .scad は必ず成果物に入る
    assert any(a.endswith(".scad") for a in r.artifacts)


def test_cad_tool_to_blender():
    t = cad.CadTool()
    r = t.run(action="to_blender", stl="/tmp/m.stl")
    assert r.ok is True
    assert "import_mesh.stl" in r.data["code"]


def test_cad_tool_requires_prompt():
    t = cad.CadTool()
    r = t.run(action="openscad_generate")
    assert r.ok is False


# ---- モデリング振り分けルーター ----

def test_router_cad():
    assert model_router.route("歯車を作って")["tool"] == "cad"
    assert model_router.route("筐体の部品")["tool"] == "cad"
    assert model_router.route("ブラケット")["tool"] == "cad"


def test_router_cad_engine():
    assert model_router.route("歯車")["engine"] == "openscad"
    assert model_router.route("アセンブリの機械")["engine"] == "freecad"


def test_router_gen3d():
    assert model_router.route("この画像から3Dモデルを作って")["tool"] == "gen3d"
    assert model_router.route("写真の実物をモデル化")["tool"] == "gen3d"


def test_router_blender():
    assert model_router.route("かわいいキャラクターのシーン")["tool"] == "blender"
    assert model_router.route("抽象アートショート")["tool"] == "blender"


def test_build_asset_cad():
    res = model_router.build_asset("歯車", tool="cad", out_dir="/tmp/_cad_build")
    assert res["tool"] == "cad"
    assert res["engine"] == "openscad"


def test_build_asset_explicit_cad_backend(monkeypatch):
    class Result:
        ok = True
        error = ""
        data = {"stl": "model.stl"}
        artifacts = ["model.stl"]

    class Registry:
        def __init__(self):
            self.calls = []

        def call(self, name, **kwargs):
            self.calls.append((name, kwargs))
            return Result()

    registry = Registry()
    monkeypatch.setattr("engines.bootstrap", lambda: registry)

    for backend, action in (("openscad", "openscad_generate"), ("freecad", "freecad_generate")):
        result = model_router.build_asset("diagnostic", tool=backend, out_dir="output/test")
        assert result["ok"] is True
        assert result["tool"] == "cad"
        assert result["engine"] == backend
        assert registry.calls[-1][1]["action"] == action
