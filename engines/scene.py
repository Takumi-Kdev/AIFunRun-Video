"""シーン演出エンジン（プロンプト→多様なBlenderシーンを自動生成・プロシージャルモデリング）。

プロンプトだけで「面白い・多様な」動画を作るため、Blender の手続き的モデリング
（プリミティブ + マテリアル + ライト + カメラアニメ + オブジェクトアニメ）を
自然言語から自動構成する bpy コードを生成する。

- classify(prompt)  : プロンプト → シーンタイプ（キーワード分類）
- build_scene(...)  : シーンタイプ + プロンプト由来シードで、決定的に多様なシーンを生成
- types()           : 利用可能なシーンタイプ一覧

シーンタイプ:
  - abstract_3d      : 浮遊プリミティブ群（回転/フロート）+ オービットカメラ
  - low_poly_world   : 地面 + 散在する低ポリ地形オブジェクト + スカイ
  - product_showcase : 中央オブジェクトをペデスタル上で回転 + 三点照明 + ドリーカメラ
  - tech_abstract    : 暗背景に発光風オブジェクト群（テクノロジー感）

生成する bpy コードは有効な Python として検証され、Blender でそのままレンダーできる。
（GPU/外部3D生成が無くても、Blender があればプロンプトだけで実動画を作れる）
"""
from __future__ import annotations

import hashlib
import random
from typing import Callable

from core.tool_layer import Tool, ToolResult

# プロンプト → シーンタイプのキーワード分類
_CLASSIFY_RULES: list[tuple[str, list[str]]] = [
    ("product_showcase", ["商品", "プロダクト", "showcase", "製品", "紹介", "promo", "広告", "cm", "ミニマル商品"]),
    ("tech_abstract", ["tech", "テック", "テクノ", "hud", "デジタル", "ai感", "ハイテク", "energy", "エネルギ", "vision", "ビジョン"]),
    ("low_poly_world", ["low poly", "ローポリ", "ワールド", "世界", "風景", "scene", "シーン", "島", "街", "自然", "森", "おとぎ話", "landscape", "world"]),
    # 既定は abstract_3d
]
DEFAULT_TYPE = "abstract_3d"

_PRIMITIVES = ["primitive_ico_sphere", "primitive_cube", "primitive_torus",
               "primitive_cylinder", "primitive_cone", "primitive_uv_sphere"]


def _seedval(prompt: str, seed: int | None = None) -> int:
    if seed is not None:
        return int(seed)
    return int(hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:8], 16)


def classify(prompt: str) -> str:
    t = prompt.lower()
    for stype, keys in _CLASSIFY_RULES:
        if any(k in t for k in keys):
            return stype
    return DEFAULT_TYPE


def types() -> list[str]:
    return ["abstract_3d", "low_poly_world", "product_showcase", "tech_abstract"]


def _render_tail(out: str, resolution: tuple[int, int], fps: int, frames: int) -> str:
    w, h = resolution
    return (
        "import os, shutil, subprocess, tempfile\n"
        "bpy.context.scene.render.resolution_x = {w}\n"
        "bpy.context.scene.render.resolution_y = {h}\n"
        "bpy.context.scene.render.fps = {fps}\n"
        "bpy.context.scene.render.image_settings.file_format = 'PNG'\n"
        f"_aifunrun_out = {repr(out)}\n"
        "_aifunrun_frames = tempfile.mkdtemp(prefix='aifunrun_blender_')\n"
        "bpy.context.scene.render.filepath = os.path.join(_aifunrun_frames, 'frame_')\n"
        "bpy.context.scene.frame_start = 1\n"
        f"bpy.context.scene.frame_end = {frames}\n"
        "bpy.ops.render.render(animation=True, write_still=False)\n"
        "_aifunrun_ffmpeg = shutil.which('ffmpeg')\n"
        "if _aifunrun_ffmpeg:\n"
        "    subprocess.run([_aifunrun_ffmpeg, '-y', '-framerate', str(bpy.context.scene.render.fps), '-i', os.path.join(_aifunrun_frames, 'frame_%04d.png'), '-c:v', 'libx264', '-pix_fmt', 'yuv420p', _aifunrun_out], check=True)\n"
        "    shutil.rmtree(_aifunrun_frames, ignore_errors=True)\n"
        "else:\n"
        "    print('ffmpeg_not_found; frames=' + _aifunrun_frames)\n"
        "print('scene_render_done')"
    ).format(w=w, h=h, fps=fps, frames=frames)


# ---- 各シーンタイプのビルダー ------------------------------------------------ #

def _build_abstract(prompt, out, resolution, fps, frames, seed) -> str:
    rng = random.Random(_seedval(prompt, seed))
    items = []
    n = rng.randint(14, 24)
    for _ in range(n):
        op = rng.choice(_PRIMITIVES)
        params = {
             "primitive_ico_sphere": f"radius={rng.uniform(0.3,0.9):.2f}",
             "primitive_cube": f"size={rng.uniform(0.5,1.4):.2f}",
             "primitive_torus": f"major_radius={rng.uniform(0.3,0.7):.2f}, minor_radius={rng.uniform(0.1,0.3):.2f}",
             "primitive_cylinder": f"radius={rng.uniform(0.3,0.7):.2f}, depth={rng.uniform(0.5,1.6):.2f}",
             "primitive_cone": f"radius1={rng.uniform(0.3,0.7):.2f}, depth={rng.uniform(0.5,1.6):.2f}",
             "primitive_uv_sphere": f"radius={rng.uniform(0.3,0.8):.2f}",
        }[op]
        loc = (round(rng.uniform(-7, 7), 2), round(rng.uniform(-7, 7), 2), round(rng.uniform(0, 7), 2))
        col = (round(rng.uniform(0.1, 1), 2), round(rng.uniform(0.1, 1), 2), round(rng.uniform(0.1, 1), 2))
        items.append((op, params, loc, col))

    lines = [
        "import bpy, math\n",
        "# --- scene: abstract_3d ---\n",
        "bpy.ops.wm.read_factory_settings(use_empty=True)\n",
        "bpy.context.scene.render.engine = 'CYCLES'\n",
        "if bpy.context.scene.world is None: bpy.context.scene.world = bpy.data.worlds.new('World')\n",
        "bpy.context.scene.world.use_nodes = True\n",
        "bg = bpy.context.scene.world.node_tree.nodes['Background']\n",
        "bg.inputs[0].default_value = (0.02, 0.02, 0.05, 1.0)\n",
        # ライト
        "bpy.ops.object.light_add(type='AREA', location=(0, -8, 8)); bpy.context.active_object.data.energy = 800\n",
        "bpy.ops.object.light_add(type='POINT', location=(6, 6, 6)); bpy.context.active_object.data.energy = 400\n",
    ]
    for op, params, loc, col in items:
        lines.append(
            f"bpy.ops.mesh.{op}_add({params}, location=({loc[0]}, {loc[1]}, {loc[2]}))\n"
            f"o = bpy.context.active_object\n"
            f"mat = bpy.data.materials.new('m')\n"
            f"mat.use_nodes = True\n"
            f"mat.node_tree.nodes['Principled BSDF'].inputs[0].default_value = ({col[0]}, {col[1]}, {col[2]}, 1.0)\n"
            f"o.data.materials.append(mat)\n"
            f"o.rotation_euler = (0, 0, {rng.uniform(0,6.28):.2f})\n"
        )
    # オブジェクト回転アニメ + カメラオービット
    lines += [
        "# 全オブジェクトをゆっくり回転\n",
        "for o in bpy.context.scene.objects:\n"
        "    if o.type == 'MESH':\n"
        "        o.rotation_mode = 'XYZ'\n"
        "        o.rotation_euler = (0, 0, 0)\n"
        "        o.keyframe_insert('rotation_euler', frame=1)\n"
        f"        o.rotation_euler = (0, 0, {3.14159:.2f})\n"
        f"        o.keyframe_insert('rotation_euler', frame={frames})\n",
        "# カメラ\n",
        "bpy.ops.object.camera_add(location=(0, 0, 0))\n",
        "cam = bpy.context.active_object\n",
        "bpy.context.scene.camera = cam\n",
        f"for f in range(1, {frames}+1):\n"
        f"    ang = 2 * math.pi * (f - 1) / {frames}\n"
        "    cam.location = (12 * math.cos(ang), 12 * math.sin(ang), 4)\n"
        "    cam.keyframe_insert('location', frame=f)\n",
    ]
    lines.append(_render_tail(out, resolution, fps, frames))
    return "".join(lines)


def _build_low_poly_world(prompt, out, resolution, fps, frames, seed) -> str:
    rng = random.Random(_seedval(prompt, seed))
    n = rng.randint(10, 16)
    items = []
    for _ in range(n):
        op = rng.choice(["primitive_cone", "primitive_cube", "primitive_ico_sphere", "primitive_cylinder"])
        params = {
             "primitive_cone": f"radius1={rng.uniform(0.4,1.0):.2f}, depth={rng.uniform(0.8,2.2):.2f}",
             "primitive_cube": f"size={rng.uniform(0.6,1.6):.2f}",
             "primitive_ico_sphere": f"radius={rng.uniform(0.3,0.8):.2f}",
             "primitive_cylinder": f"radius={rng.uniform(0.4,0.9):.2f}, depth={rng.uniform(0.6,2.0):.2f}",
        }[op]
        loc = (round(rng.uniform(-9, 9), 2), round(rng.uniform(-9, 9), 2), round(rng.uniform(0.2, 2.5), 2))
        col = (round(rng.uniform(0.2, 0.9), 2), round(rng.uniform(0.3, 0.9), 2), round(rng.uniform(0.2, 0.8), 2))
        items.append((op, params, loc, col))
    lines = [
        "import bpy, math\n",
        "# --- scene: low_poly_world ---\n",
        "bpy.ops.wm.read_factory_settings(use_empty=True)\n",
        "bpy.context.scene.render.engine = 'CYCLES'\n",
        "if bpy.context.scene.world is None: bpy.context.scene.world = bpy.data.worlds.new('World')\n",
        "bpy.context.scene.world.use_nodes = True\n",
        "bg = bpy.context.scene.world.node_tree.nodes['Background']\n",
        "bg.inputs[0].default_value = (0.55, 0.75, 1.0, 1.0)\n",
        "# 地面\n",
        "bpy.ops.mesh.primitive_plane_add(size=40, location=(0, 0, 0))\n",
        "g = bpy.context.active_object; gm = bpy.data.materials.new('g'); gm.use_nodes = True\n",
        "gm.node_tree.nodes['Principled BSDF'].inputs[0].default_value = (0.25, 0.5, 0.25, 1.0)\n",
        "g.data.materials.append(gm)\n",
        "bpy.ops.object.light_add(type='SUN', location=(8, 8, 16)); bpy.context.active_object.data.energy = 3\n",
    ]
    for op, params, loc, col in items:
        lines.append(
            f"bpy.ops.mesh.{op}_add({params}, location=({loc[0]}, {loc[1]}, {loc[2]}))\n"
            f"o = bpy.context.active_object\n"
            f"mat = bpy.data.materials.new('m')\n"
            f"mat.use_nodes = True\n"
            f"mat.node_tree.nodes['Principled BSDF'].inputs[0].default_value = ({col[0]}, {col[1]}, {col[2]}, 1.0)\n"
            f"o.data.materials.append(mat)\n"
        )
    lines += [
        "# カメラオービット\n",
        "bpy.ops.object.camera_add(location=(0, 0, 0))\n",
        "cam = bpy.context.active_object\n",
        "bpy.context.scene.camera = cam\n",
        f"for f in range(1, {frames}+1):\n"
        f"    ang = 2 * math.pi * (f - 1) / {frames}\n"
        "    cam.location = (14 * math.cos(ang), 14 * math.sin(ang), 7)\n"
        "    cam.rotation_euler = (0, 0, 0)\n"
        "    cam.keyframe_insert('location', frame=f)\n",
    ]
    lines.append(_render_tail(out, resolution, fps, frames))
    return "".join(lines)


def _build_product_showcase(prompt, out, resolution, fps, frames, seed) -> str:
    rng = random.Random(_seedval(prompt, seed))
    col = (round(rng.uniform(0.2, 0.9), 2), round(rng.uniform(0.2, 0.9), 2), round(rng.uniform(0.2, 0.9), 2))
    lines = [
        "import bpy, math\n",
        "# --- scene: product_showcase ---\n",
        "bpy.ops.wm.read_factory_settings(use_empty=True)\n",
        "bpy.context.scene.render.engine = 'CYCLES'\n",
        "if bpy.context.scene.world is None: bpy.context.scene.world = bpy.data.worlds.new('World')\n",
        "bpy.context.scene.world.use_nodes = True\n",
        "bg = bpy.context.scene.world.node_tree.nodes['Background']\n",
        "bg.inputs[0].default_value = (0.04, 0.04, 0.06, 1.0)\n",
        # ペデスタル
        "bpy.ops.mesh.primitive_cylinder_add(radius=2, depth=0.4, location=(0, 0, 0.2))\n",
        "p = bpy.context.active_object; pm = bpy.data.materials.new('p'); pm.use_nodes = True\n",
        "pm.node_tree.nodes['Principled BSDF'].inputs[0].default_value = (0.1, 0.1, 0.12, 1.0)\n",
        "p.data.materials.append(pm)\n",
        # 中央オブジェクト
        f"bpy.ops.mesh.primitive_ico_sphere_add(radius=1.2, location=(0, 0, 2.2))\n",
        "o = bpy.context.active_object\n",
        f"mat = bpy.data.materials.new('m'); mat.use_nodes = True\n",
        f"mat.node_tree.nodes['Principled BSDF'].inputs[0].default_value = ({col[0]}, {col[1]}, {col[2]}, 1.0)\n",
        "o.data.materials.append(mat)\n",
        "o.keyframe_insert('rotation_euler', frame=1)\n",
        f"o.rotation_euler = (0, 0, {3.14159*2:.2f})\n",
        f"o.keyframe_insert('rotation_euler', frame={frames})\n",
        # 三点照明
        "bpy.ops.object.light_add(type='AREA', location=(8, -6, 9)); bpy.context.active_object.data.energy = 1200\n",
        "bpy.ops.object.light_add(type='AREA', location=(-8, -4, 4)); bpy.context.active_object.data.energy = 400\n",
        "bpy.ops.object.light_add(type='AREA', location=(0, 8, 6)); bpy.context.active_object.data.energy = 500\n",
        # カメラドリー
        "bpy.ops.object.camera_add(location=(0, 0, 0))\n",
        "cam = bpy.context.active_object\n",
        "bpy.context.scene.camera = cam\n",
        f"for f in range(1, {frames}+1):\n"
        f"    t = (f - 1) / {max(frames,1)}\n"
        "    cam.location = (0, 9 - 3 * t, 3 + 1 * t)\n"
        "    cam.rotation_euler = (0, 0, 0)\n"
        "    cam.keyframe_insert('location', frame=f)\n",
    ]
    lines.append(_render_tail(out, resolution, fps, frames))
    return "".join(lines)


def _build_tech_abstract(prompt, out, resolution, fps, frames, seed) -> str:
    rng = random.Random(_seedval(prompt, seed))
    n = rng.randint(16, 26)
    lines = [
        "import bpy, math\n",
        "# --- scene: tech_abstract ---\n",
        "bpy.ops.wm.read_factory_settings(use_empty=True)\n",
        "bpy.context.scene.render.engine = 'CYCLES'\n",
        "if bpy.context.scene.world is None: bpy.context.scene.world = bpy.data.worlds.new('World')\n",
        "bpy.context.scene.world.use_nodes = True\n",
        "bg = bpy.context.scene.world.node_tree.nodes['Background']\n",
        "bg.inputs[0].default_value = (0.01, 0.01, 0.02, 1.0)\n",
        "bpy.ops.object.light_add(type='POINT', location=(0, -10, 6)); bpy.context.active_object.data.energy = 600\n",
        "bpy.ops.object.light_add(type='POINT', location=(8, 8, 4)); bpy.context.active_object.data.energy = 300\n",
    ]
    for i in range(n):
        op = rng.choice(["primitive_cube", "primitive_ico_sphere", "primitive_torus", "primitive_cylinder"])
        params = {
             "primitive_cube": f"size={rng.uniform(0.2,0.9):.2f}",
             "primitive_ico_sphere": f"radius={rng.uniform(0.2,0.7):.2f}",
             "primitive_torus": f"major_radius={rng.uniform(0.2,0.5):.2f}, minor_radius={rng.uniform(0.05,0.2):.2f}",
             "primitive_cylinder": f"radius={rng.uniform(0.2,0.5):.2f}, depth={rng.uniform(0.3,1.0):.2f}",
        }[op]
        loc = (round(rng.uniform(-8, 8), 2), round(rng.uniform(-8, 8), 2), round(rng.uniform(0, 8), 2))
        # 発光感: 高輝度カラー
        col = (round(rng.uniform(0.0, 1.0), 2), round(rng.uniform(0.3, 1.0), 2), round(rng.uniform(0.4, 1.0), 2))
        lines.append(
            f"bpy.ops.mesh.{op}_add({params}, location=({loc[0]}, {loc[1]}, {loc[2]}))\n"
            f"o = bpy.context.active_object\n"
            f"mat = bpy.data.materials.new('m'); mat.use_nodes = True\n"
            f"mat.node_tree.nodes['Principled BSDF'].inputs[0].default_value = ({col[0]}, {col[1]}, {col[2]}, 1.0)\n"
            f"o.data.materials.append(mat)\n"
        )
    lines += [
        "# カメラオービット\n",
        "bpy.ops.object.camera_add(location=(0, 0, 0))\n",
        "cam = bpy.context.active_object\n",
        "bpy.context.scene.camera = cam\n",
        f"for f in range(1, {frames}+1):\n"
        f"    ang = 2 * math.pi * (f - 1) / {frames}\n"
        "    cam.location = (11 * math.cos(ang), 11 * math.sin(ang), 4)\n"
        "    cam.keyframe_insert('location', frame=f)\n",
    ]
    lines.append(_render_tail(out, resolution, fps, frames))
    return "".join(lines)


_BUILDERS: dict[str, Callable] = {
    "abstract_3d": _build_abstract,
    "low_poly_world": _build_low_poly_world,
    "product_showcase": _build_product_showcase,
    "tech_abstract": _build_tech_abstract,
}


def build_scene(prompt: str, scene_type: str | None = None, out: str = "output/render.mp4",
                resolution: tuple[int, int] = (1920, 1080), fps: int = 30,
                frames: int = 120, seed: int | None = None) -> str:
    """プロンプトから多様なBlenderシーン（bpyコード）を生成して返す。"""
    stype = scene_type or classify(prompt)
    builder = _BUILDERS.get(stype) or _BUILDERS[DEFAULT_TYPE]
    return builder(prompt, out=out, resolution=resolution, fps=fps, frames=frames, seed=seed)


class SceneTool(Tool):
    """プロンプトから多様なBlenderシーン(bpyコード)を生成する。実行は blender execute_code。"""

    name = "scene"
    description = "プロンプト→多様なBlenderシーン生成（abstract/lowpoly/product/tech・プロシージャルモデリング）"

    def health(self) -> bool:
        return True

    def setup(self) -> ToolResult:
        return ToolResult(ok=True)

    def run(self, **kwargs) -> ToolResult:
        action = kwargs.get("action", "health")

        if action == "health":
            return ToolResult(ok=True, data={"types": types()})

        if action == "classify":
            prompt = kwargs.get("prompt", "")
            return ToolResult(ok=True, data={"scene_type": classify(prompt), "types": types()})

        if action == "types":
            return ToolResult(ok=True, data={"types": types()})

        if action == "build":
            prompt = kwargs.get("prompt", "")
            if not prompt:
                return ToolResult(ok=False, error="prompt が必要")
            stype = kwargs.get("scene_type") or classify(prompt)
            try:
                w, h = (int(x) for x in kwargs.get("resolution", "1920,1080").split(","))
            except Exception:  # noqa: BLE001
                w, h = 1920, 1080
            code = build_scene(
                prompt,
                scene_type=stype,
                out=kwargs.get("out", "output/render.mp4"),
                resolution=(w, h),
                fps=int(kwargs.get("fps", 30)),
                frames=int(kwargs.get("frames", 120)),
                seed=kwargs.get("seed"),
            )
            return ToolResult(ok=True, data={"code": code, "scene_type": stype,
                                             "frames": int(kwargs.get("frames", 120))})

        return ToolResult(ok=False, error=f"未知 action: {action}")
