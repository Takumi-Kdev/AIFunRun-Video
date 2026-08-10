"""Blender シーン・カメラ・レンダー工程（工場の演出工程）。

animate は Blender(bpy) で実行する「演出スクリプト」を生成する。
実際の実行は engines.blender（BlenderMCP）の execute_code で行う。

Actions:
  - orbit_shot : カメラが対象を回るオービットショットの bpy コード
  - scene_setup: ライト/背景/シーン初期化の bpy コード
  - render     : Cycles/EEVEE でアニメをレンダリングし動画を出力する bpy コード
"""
from __future__ import annotations

import json
from pathlib import Path

from core.logger import write_log
from core.tool_layer import Tool, ToolResult

ENGINE = "CYCLES"  # EEVEE に変えれば軽量レンダー


def _norm_rgb(bg_color: str) -> str:
    """"0.05 0.06 0.09" や "0.05,0.06,0.09" を "0.05, 0.06, 0.09" に正規化（有効なbpyタプル）。"""
    parts = [p for p in bg_color.replace(",", " ").split() if p]
    return ", ".join(parts)


def build_scene_setup(engine: str = ENGINE, bg_color: str = "0.05 0.06 0.09") -> str:
    """シーン初期化（レンダーエンジン・背景・ワールド）。"""
    rgb = _norm_rgb(bg_color)
    return (
        "import bpy\n"
        "# --- animate: シーン初期化 ---\n"
        f"bpy.context.scene.render.engine = '{engine}'\n"
        "bpy.context.scene.world.use_nodes = True\n"
        "bg = bpy.context.scene.world.node_tree.nodes['Background']\n"
        f"bg.inputs[0].default_value = ({rgb}, 1.0)\n"
        "print('scene_ready')"
    )


def build_lighting() -> str:
    """基本ライト（三点照明風）を追加。"""
    return (
        "import bpy\n"
        "# --- animate: 照明 ---\n"
        "for n, loc, energy in [('key', (5, -5, 6), 1000), ('fill', (-6, -3, 4), 300), ('rim', (0, 6, 5), 500)]:\n"
        "    bpy.ops.object.light_add(type='AREA', location=loc)\n"
        "    o = bpy.context.active_object\n"
        "    o.data.energy = energy\n"
        "print('lighting_added')"
    )


def build_orbit_shot(target: str = "Cube", radius: float = 8.0, frames: int = 90) -> str:
    """カメラが target を回るオービットショット。"""
    return (
        "import bpy, math\n"
        "# --- animate: オービットショット ---\n"
        "bpy.ops.object.camera_add(location=(0, 0, 0))\n"
        f"cam = bpy.context.active_object\n"
        f"target = bpy.data.objects.get('{target}') or bpy.context.selected_objects[0]\n"
        "bpy.context.scene.camera = cam\n"
        "bpy.context.scene.frame_start = 1\n"
        f"bpy.context.scene.frame_end = {frames}\n"
        "track = cam.constraints.new(type='TRACK_TO')\n"
        "track.target = target\n"
        f"r = {radius}\n"
        "for f in range(1, " + str(frames) + "+1):\n"
        "    ang = 2 * math.pi * (f - 1) / " + str(max(frames, 1)) + "\n"
        "    cam.location = (r * math.cos(ang), r * math.sin(ang), 2)\n"
        "    cam.keyframe_insert('location', frame=f)\n"
        "print('orbit_shot_ready')"
    )


def build_render(out_video: str, resolution: tuple[int, int] = (1920, 1080),
                 fps: int = 30, samples: int = 64) -> str:
    """シーンをレンダリングして動画（ffmpeg）を出力する。"""
    w, h = resolution
    return (
        "import bpy\n"
        "# --- animate: レンダリング ---\n"
        f"bpy.context.scene.render.resolution_x = {w}\n"
        f"bpy.context.scene.render.resolution_y = {h}\n"
        f"bpy.context.scene.render.fps = {fps}\n"
        f"bpy.context.scene.cycles.samples = {samples}\n"
        "bpy.context.scene.render.image_settings.file_format = 'FFMPEG'\n"
        "bpy.context.scene.render.ffmpeg.format = 'MPEG4'\n"
        "bpy.context.scene.render.ffmpeg.codec = 'H264'\n"
        f"bpy.context.scene.render.filepath = {json.dumps(str(out_video))}\n"
        "bpy.ops.render.render(animation=True, write_still=False)\n"
        "print('render_done')"
    )


class AnimateTool(Tool):
    name = "animate"
    description = "Blender演出スクリプト生成（シーン/照明/オービット/レンダー）。実行はblender execute_code"

    def health(self) -> bool:
        return True  # スクリプト生成はローカルで可能（実行はBlender側）

    def setup(self) -> ToolResult:
        return ToolResult(ok=True)

    def run(self, **kwargs) -> ToolResult:
        action = kwargs.get("action", "health")

        if action == "health":
            return ToolResult(ok=True, data={"note": "スクリプト生成は常時可能。実行はblender execute_code"})

        if action == "scene_setup":
            return ToolResult(ok=True, data={"code": build_scene_setup(
                kwargs.get("engine", ENGINE), kwargs.get("bg_color", "0.05 0.06 0.09"))})

        if action == "lighting":
            return ToolResult(ok=True, data={"code": build_lighting()})

        if action == "orbit_shot":
            return ToolResult(ok=True, data={"code": build_orbit_shot(
                kwargs.get("target", "Cube"), float(kwargs.get("radius", 8.0)),
                int(kwargs.get("frames", 90)))})

        if action == "render":
            out = kwargs.get("out", "output/render.mp4")
            return ToolResult(ok=True, data={"code": build_render(
                out, tuple(int(x) for x in kwargs.get("resolution", "1920,1080").split(",")),
                int(kwargs.get("fps", 30)), int(kwargs.get("samples", 64)))})

        return ToolResult(ok=False, error=f"未知 action: {action}")
