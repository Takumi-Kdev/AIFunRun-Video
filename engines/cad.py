"""CAD/パラメトリックモデリングエンジン（OpenSCAD / FreeCAD をテキスト駆動）。

Blender が苦手な「精密・パラメトリック・工業的」な形状（歯車/筐体/ブラケット/
花瓶/ノブ等）を、テキスト（プロンプト）から生成する。

  - openscad_generate : プロンプト → OpenSCAD スクリプト(.scad) → レンダーで STL
  - freecad_generate  : プロンプト → FreeCAD Python スクリプト → レンダーで STL
  - to_blender        : STL → Blender へインポートする bpy コード（シーン合成用）

バックエンド: openscad / freecad(freecadcmd) があれば実際に STL を生成。
無ければ有効なスクリプトを保存し、導入環境でレンダーできるよう生産指示を返す（必ず動く）。
"""
from __future__ import annotations

import random
from pathlib import Path

from core.logger import write_log
from core.tool_layer import Tool, ToolResult
from core import process


def _seed(prompt: str) -> int:
    import hashlib
    return int(hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:8], 16)


def _which(cmd: str) -> bool:
    import shutil
    return shutil.which(cmd) is not None


def detect_backends() -> dict:
    return {"openscad": _which("openscad"), "freecad": _which("freecad") or _which("freecadcmd")}


# ---- OpenSCAD スクリプト生成 ------------------------------------------------ #

def _openscad_gear() -> str:
    return (
        "$fn=48;\n"
        "teeth=12; mod=2; h=5; r=teeth*mod/2;\n"
        "union(){\n"
        "  cylinder(h=h, r=r, $fn=teeth);\n"
        "  for(i=[0:teeth-1]) rotate([0,0,i*360/teeth]) translate([r,0,0]) "
        "scale([1.3,0.8,1]) cube([mod*1.2,mod,h], center=true);\n"
        "}\n"
        "difference(){\n"
        "  cylinder(h=h, r=r+mod*0.6, $fn=teeth);\n"
        "  cylinder(h=h+2, r=mod*1.4, center=true);\n"
        "}\n"
    )


def _openscad_box() -> str:
    return (
        "$fn=32;\n"
        "w=40; d=30; h=20; th=2;\n"
        "difference(){\n"
        "  cube([w,d,h]);\n"
        "  translate([th,th,th]) cube([w-2*th, d-2*th, h]);\n"
        "  for(x=[th+3, w-th-3]) for(y=[th+3, d-th-3]) translate([x,y,0]) "
        "cylinder(h=h+2, r=1.5, center=true);\n"
        "}\n"
    )


def _openscad_vase() -> str:
    return (
        "$fn=64;\n"
        "h=60; r=22; th=3;\n"
        "difference(){\n"
        "  linear_extrude(h=h) circle(r=r);\n"
        "  translate([0,0,th]) linear_extrude(h=h-th) circle(r=r-th);\n"
        "}\n"
    )


def _openscad_knob() -> str:
    return (
        "$fn=48;\n"
        "minkowski(){\n"
        "  cylinder(h=12, r=16);\n"
        "  sphere(r=3);\n"
        "}\n"
        "translate([0,0,12]) cylinder(h=8, r=3, $fn=32);\n"
    )


def _openscad_generic(prompt: str) -> str:
    rng = random.Random(_seed(prompt))
    lines = ["$fn=48;", "union(){"]
    for i in range(rng.randint(3, 6)):
        kind = rng.choice(["cube", "sphere", "cylinder"])
        x, y, z = (round(rng.uniform(-20, 20), 1) for _ in range(3))
        if kind == "cube":
            lines.append(f"  translate([{x},{y},{z}]) cube({rng.randint(5,16)});")
        elif kind == "sphere":
            lines.append(f"  translate([{x},{y},{z}]) sphere(r={rng.randint(3,10)});")
        else:
            lines.append(f"  translate([{x},{y},{z}]) cylinder(h={rng.randint(4,14)}, r={rng.randint(3,8)});")
    lines.append("}")
    return "\n".join(lines)


def build_openscad(prompt: str) -> str:
    t = prompt.lower()
    if any(k in t for k in ["歯車", "ギア", "gear", "cog"]):
        return _openscad_gear()
    if any(k in t for k in ["筐体", "ボックス", "箱", "ブラケット", "box", "case", "bracket", "enclosure"]):
        return _openscad_box()
    if any(k in t for k in ["花瓶", "vase"]):
        return _openscad_vase()
    if any(k in t for k in ["ノブ", "取手", "knob", "handle"]):
        return _openscad_knob()
    return _openscad_generic(prompt)


def render_openscad(scad: str, out_stl: str) -> tuple[bool, str]:
    """openscad CLI で STL を生成。"""
    scad_path = Path(out_stl).with_suffix(".scad")
    scad_path.parent.mkdir(parents=True, exist_ok=True)
    scad_path.write_text(scad, encoding="utf-8")
    if not _which("openscad"):
        return False, f"openscad 未導入。スクリプト: {scad_path}（導入後: openscad -o {out_stl} {scad_path}）"
    r = process.run_command(["openscad", "-o", out_stl, str(scad_path)],
                            timeout_ms=120000, max_output_bytes=100_000, kill_process_tree=True)
    return (True, out_stl) if r.ok and Path(out_stl).exists() else (False, r.error or "OpenSCAD レンダー失敗")


# ---- FreeCAD スクリプト生成 -------------------------------------------------- #

def build_freecad(prompt: str, out_stl: str) -> str:
    """FreeCAD でパラメトリックソリッドを作り STL へエクスポートする Python スクリプト。"""
    t = prompt.lower()
    if any(k in t for k in ["筐体", "箱", "box", "case", "enclosure"]):
        body = (
            "import FreeCAD as App, Part\n"
            "doc = App.newDocument()\n"
            "b = Part.makeBox(40,30,20)\n"
            "holes = Part.makeCylinder(1.5, 26).translate(App.Vector(6,6,0))\n"
            "s = b.cut(holes)\n"
            "Part.show(s)\n"
            f"Part.export([s], {str(out_stl)!r})\n"
        )
    else:
        body = (
            "import FreeCAD as App, Part\n"
            "doc = App.newDocument()\n"
            "c = Part.makeCylinder(18, 30)\n"
            "hole = Part.makeCylinder(6, 32).translate(App.Vector(0,0,-1))\n"
            "s = c.cut(hole)\n"
            "Part.show(s)\n"
            f"Part.export([s], {str(out_stl)!r})\n"
        )
    return body


def render_freecad(py_script: str, out_stl: str) -> tuple[bool, str]:
    """freecadcmd でスクリプトを実行し STL を生成。"""
    py_path = Path(out_stl).with_suffix(".py")
    py_path.parent.mkdir(parents=True, exist_ok=True)
    py_path.write_text(py_script, encoding="utf-8")
    cmd = "freecadcmd" if _which("freecadcmd") else ("freecad" if _which("freecad") else "")
    if not cmd:
        return False, f"FreeCAD 未導入。スクリプト: {py_path}（導入後: {cmd or 'freecadcmd'} {py_path}）"
    r = process.run_command([cmd, str(py_path)], timeout_ms=180000, max_output_bytes=100_000, kill_process_tree=True)
    return (True, out_stl) if r.ok and Path(out_stl).exists() else (False, r.error or "FreeCAD レンダー失敗")


def stl_to_blender_script(stl_path: str) -> str:
    """STL → Blender へインポートする bpy コード（シーン合成用）。"""
    return (
        "import bpy\n"
        "# --- CAD: STL を Blender へインポート ---\n"
        "bpy.ops.wm.read_factory_settings(use_empty=True)\n"
        f"bpy.ops.import_mesh.stl(filepath={str(stl_path)!r})\n"
        "bpy.ops.object.origin_set(type='ORIGIN_CENTER_OF_MASS', center='BOUNDS')\n"
        "o = bpy.context.active_object; o.location = (0, 0, 0)\n"
        "print('cad_stl_imported')"
    )


class CadTool(Tool):
    name = "cad"
    description = "OpenSCAD/FreeCADでパラメトリックCADモデル生成（精密・工業的形状）→ STL → Blender合成"

    def health(self) -> bool:
        return any(detect_backends().values())

    def setup(self) -> ToolResult:
        return ToolResult(ok=True, data=detect_backends())

    def run(self, **kwargs) -> ToolResult:
        action = kwargs.get("action", "health")

        if action == "health":
            det = detect_backends()
            return ToolResult(ok=any(det.values()), data=det)

        if action == "openscad_generate":
            prompt = kwargs.get("prompt", "")
            out = kwargs.get("out", "output/cad/model.stl")
            if not prompt:
                return ToolResult(ok=False, error="prompt が必要")
            scad = build_openscad(prompt)
            ok, msg = render_openscad(scad, out)
            artifacts = [str(Path(out).with_suffix(".scad"))]
            if ok:
                artifacts.append(out)
            return ToolResult(ok=ok, data={"scad": scad, "stl": msg if ok else ""},
                              artifacts=artifacts, error="" if ok else msg)

        if action == "freecad_generate":
            prompt = kwargs.get("prompt", "")
            out = kwargs.get("out", "output/cad/model.stl")
            if not prompt:
                return ToolResult(ok=False, error="prompt が必要")
            py = build_freecad(prompt, out)
            ok, msg = render_freecad(py, out)
            artifacts = [str(Path(out).with_suffix(".py"))]
            if ok:
                artifacts.append(out)
            return ToolResult(ok=ok, data={"py": py, "stl": msg if ok else ""},
                              artifacts=artifacts, error="" if ok else msg)

        if action == "to_blender":
            stl = kwargs.get("stl", "")
            if not stl:
                return ToolResult(ok=False, error="stl が必要")
            return ToolResult(ok=True, data={"code": stl_to_blender_script(stl)})

        return ToolResult(ok=False, error=f"未知 action: {action}")
