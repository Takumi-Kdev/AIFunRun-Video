"""シーン演出エンジン（engines/scene）のテスト。"""
from __future__ import annotations

from engines import scene


def test_types():
    assert set(scene.types()) == {"abstract_3d", "low_poly_world", "product_showcase", "tech_abstract"}


def test_classify():
    assert scene.classify("商品を紹介するプロモーション動画") == "product_showcase"
    assert scene.classify("テクノロジーとAI感のあるハイテク映像") == "tech_abstract"
    assert scene.classify("ローポリの世界と風景") == "low_poly_world"
    assert scene.classify("なんか抽象的なショート") == "abstract_3d"


def test_build_scene_generates_valid_python():
    for t in scene.types():
        code = scene.build_scene("テスト", scene_type=t)
        compile(code, f"<{t}>", "exec")  # 生成bpyコードが有効なPythonであること
        assert "scene_render_done" in code
        assert "bpy.ops.render.render(animation=True" in code


def test_build_scene_uses_valid_blender_operators():
    # 回帰: 生成コードのメッシュ生成は実在する primitive_*_add オペレータでなければならない
    import re
    valid = re.compile(r"bpy\.ops\.mesh\.primitive_[a-z_]+_add")
    for t in scene.types():
        code = scene.build_scene("テスト", scene_type=t)
        for op in re.findall(r"bpy\.ops\.mesh\.\w+_add", code):
            assert valid.match(op), f"{t}: 不正なBlenderオペレータ {op}"
        # プリミティブが実際に生成されている
        assert "primitive_" in code


def test_build_scene_variety_by_prompt():
    # 異なるプロンプト → 異なるシード → 異なる配置（多様性）
    a = scene.build_scene("面白い抽象ショート動画", scene_type="abstract_3d")
    b = scene.build_scene("全く違う抽象動画", scene_type="abstract_3d")
    assert a != b


def test_build_scene_deterministic_same_prompt():
    a = scene.build_scene("同じプロンプト", scene_type="abstract_3d", seed=42)
    b = scene.build_scene("同じプロンプト", scene_type="abstract_3d", seed=42)
    assert a == b


def test_scene_tool_build():
    from core.tool_layer import ToolResult
    t = scene.SceneTool()
    r = t.run(action="build", prompt="商品プロモーション", scene_type="product_showcase")
    assert r.ok is True
    compile(r.data["code"], "<gen>", "exec")
    assert r.data["scene_type"] == "product_showcase"
    assert "frames" in r.data


def test_scene_tool_classify():
    t = scene.SceneTool()
    r = t.run(action="classify", prompt="AI感のあるテック映像")
    assert r.ok is True
    assert r.data["scene_type"] == "tech_abstract"


def test_scene_tool_requires_prompt():
    t = scene.SceneTool()
    r = t.run(action="build")  # prompt なし
    assert r.ok is False


def test_scene_tool_unknown_action():
    t = scene.SceneTool()
    r = t.run(action="nope")
    assert r.ok is False
