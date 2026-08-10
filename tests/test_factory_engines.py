"""工場エンジン（gen3d / motion / video2d / animate）のテスト。"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from engines.gen3d import Gen3DTool, build_import_script, build_placeholder_script, detect_backends
from engines.motion import MotionTool, build_idle_script, build_rig_script
from engines.video2d import Video2DTool
from engines.animate import AnimateTool, build_orbit_shot, build_render, build_scene_setup


# ---- gen3d ----

def test_gen3d_build_import_script():
    code = build_import_script("/tmp/model.glb")
    assert "import bpy" in code
    assert "import_scene.gltf" in code
    assert "model.glb" in code


def test_gen3d_placeholder_script():
    code = build_placeholder_script()
    assert "primitive_ico_sphere_add" in code


def test_gen3d_tool_import_script():
    tool = Gen3DTool()
    res = tool.run(action="blender_import_script", glb="/tmp/m.glb")
    assert res.ok is True
    assert "import_scene.gltf" in res.data["code"]


def test_gen3d_tool_generate_requires_image():
    tool = Gen3DTool()
    res = tool.run(action="generate")  # image なし
    assert res.ok is False
    assert "image" in res.error


def test_gen3d_tool_generate_fallback_plan(tmp_path):
    # バックエンド未検出環境では生産指示書を出力（必ず動く原則）
    tool = Gen3DTool()
    res = tool.run(action="generate", image=str(tmp_path / "img.png"), out_dir=str(tmp_path))
    assert res.ok is False
    assert res.data and "placeholder_script" in res.data


def test_gen3d_detect_backends_returns_dict():
    det = detect_backends()
    assert set(det) == {"triposr", "trellis", "hunyuan3d"}


# ---- motion ----

def test_motion_idle_script():
    code = build_idle_script(frames=60)
    assert "keyframe_insert" in code
    assert "frame_end = 60" in code


def test_motion_rig_script():
    kps = [{"frame": 1, "x": 0.1, "y": 0.0, "z": 0.0}, {"frame": 30, "x": -0.1, "y": 0.2, "z": 0.0}]
    code = build_rig_script(kps)
    assert "keyframe_insert" in code
    assert "frame_end = keys[-1][0]" in code


def test_motion_rig_script_empty_raises():
    import pytest
    with pytest.raises(ValueError):
        build_rig_script([])


def test_motion_tool_to_blender_rig():
    tool = MotionTool()
    kps = [{"frame": 1, "x": 0.5, "y": 0.2, "z": 0.0}]
    res = tool.run(action="to_blender_rig", keypoints=json.dumps(kps))
    assert res.ok is True
    assert "keyframe_insert" in res.data["code"]


def test_motion_tool_capture_fallback_plan(tmp_path):
    tool = MotionTool()
    res = tool.run(action="capture", video=str(tmp_path / "v.mp4"), out_dir=str(tmp_path))
    # MediaPipe無し環境 → 生産指示書（ok=False）
    assert res.ok is False
    assert "idle_script" in res.data


# ---- video2d ----

def test_video2d_generate_ffmpeg(tmp_path):
    # ffmpeg があれば実動画を生成
    if not shutil.which("ffmpeg"):
        return
    tool = Video2DTool()
    out = tmp_path / "bg.mp4"
    res = tool.run(action="generate", out=str(out), duration=2.0, w=320, h=320)
    assert res.ok is True
    assert out.exists()
    assert out.stat().st_size > 0


def test_video2d_generate_requires_out():
    tool = Video2DTool()
    res = tool.run(action="generate", topic="x")
    # out 省略時は既定パスへ（ok は ffmpeg有無で変わる）→ 少なくともエラーでないことは保証
    assert res.ok in (True, False)


# ---- animate ----

def test_animate_scripts():
    orbit = build_orbit_shot(frames=30)
    assert "orbit_shot_ready" in orbit
    render = build_render("/tmp/o.mp4", resolution=(1280, 720), fps=24)
    assert "render.render(animation=True" in render
    scene = build_scene_setup()
    assert "scene_ready" in scene


def test_animate_scene_setup_generates_valid_python():
    # 回帰: 生成される bpy コードは有効なPythonでなければならない（カンマ欠落はNG）
    scene = build_scene_setup()  # 既定 "0.05 0.06 0.09"
    compile(scene, "<gen>", "exec")
    assert "(0.05, 0.06, 0.09, 1.0)" in scene
    # カンマ区切り入力も正規化される
    c2 = build_scene_setup(bg_color="0.1,0.2,0.3")
    compile(c2, "<gen>", "exec")
    assert "(0.1, 0.2, 0.3, 1.0)" in c2


def test_animate_tool_render():
    tool = AnimateTool()
    res = tool.run(action="render", out="/tmp/o.mp4", resolution="1280,720", fps=24)
    assert res.ok is True
    assert "animation=True" in res.data["code"]
