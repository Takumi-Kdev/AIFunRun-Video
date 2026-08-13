"""モデリングツール振り分けルーター（使い分けの呼び出しを正確に）。

プロンプトから、最適な3Dモデリング手法を正確に選んで呼ぶ。
  - CAD（OpenSCAD/FreeCAD）: 精密・パラメトリック・工業的形状（歯車/筐体/ブラケット等）
  - gen3d（TripoSR/TRELLIS）: 画像/実物 → 3D
  - Blender（シーン演出）   : 有機・キャラクター・シーン・アニメーション

route(prompt) で判定 → build_asset(prompt) で該当エンジンを呼ぶ。
"""
from __future__ import annotations

import shutil
from pathlib import Path

CAD_KEYS = [
    "歯車", "ギア", "gear", "cog", "筐体", "箱", "ブラケット", "box", "case", "bracket",
    "enclosure", "花瓶", "vase", "ノブ", "knob", "取手", "handle", "精密", "部品", "パーツ",
    "工業", "機械", "gearbox", "bracket", "治具", "ジグ",
]
GEN3D_KEYS = ["画像", "写真", "実物", "photo", "image", "スキャン", "リアルな物", "リファレンス", "reference"]
CAD_FREECAD_KEYS = ["アセンブリ", "assembly", "ソリッド", "solid", "機械機構", "mechanism", "複合"]


def route(prompt: str) -> dict:
    """プロンプト → 最適なモデリング手法を判定。"""
    t = prompt.lower()
    if any(k in t for k in CAD_KEYS):
        engine = "freecad" if any(k in t for k in CAD_FREECAD_KEYS) else "openscad"
        return {"tool": "cad", "engine": engine, "reason": "パラメトリック/精密・工業的形状"}
    if any(k in t for k in GEN3D_KEYS):
        return {"tool": "gen3d", "engine": None, "reason": "画像/実物から3D再構成"}
    return {"tool": "blender", "engine": None, "reason": "有機・キャラクター・シーン・アニメーション"}


def build_asset(prompt: str, tool: str | None = None, out_dir: str = "output/cad") -> dict:
    """判定に基づき、最適なモデリングエンジンを呼んで3D資産を生成する。"""
    if tool is None:
        r = route(prompt)
    elif tool in ("openscad", "freecad"):
        r = {"tool": "cad", "engine": tool, "reason": "明示指定"}
    else:
        r = {"tool": tool, "engine": None, "reason": "明示指定"}
    from engines import bootstrap
    reg = bootstrap()

    if r["tool"] == "cad":
        engine = r.get("engine") or "openscad"
        action = "openscad_generate" if engine == "openscad" else "freecad_generate"
        res = reg.call("cad", action=action, prompt=prompt, out=f"{out_dir}/cad.stl")
        return {
            "ok": bool(res.ok), "tool": "cad", "engine": engine,
            "detail": (res.error or res.data.get("stl", "スクリプト生成")),
            "artifacts": res.artifacts,
        }
    if r["tool"] == "gen3d":
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        # 画像未指定時はフォールバック（gen3d は画像前提）。プレースホルダ/計画を返す。
        res = reg.call("gen3d", action="generate", image="", topic=prompt, out_dir=out_dir)
        return {
            "ok": bool(res.ok), "tool": "gen3d", "engine": None,
            "detail": (res.error or "3D再構成"), "artifacts": res.artifacts,
        }
    # Blender: プロシージャルシーンを実際の .blend 資産として保存する。
    target = Path(out_dir)
    target.mkdir(parents=True, exist_ok=True)
    script_path = target / "blender_asset.py"
    blend_path = (target / "asset.blend").resolve()
    from engines import scene as scene_engine

    code = scene_engine.build_scene(prompt, out=str((target / "preview.mp4").resolve()))
    # 資産工程ではシーン構築だけを行う。末尾の動画レンダーは後続stationが担当する。
    code = code.rsplit("bpy.context.scene.render.resolution_x", 1)[0]
    code += f"\nimport bpy\nbpy.ops.wm.save_as_mainfile(filepath={str(blend_path)!r})\n"
    script_path.write_text(code, encoding="utf-8")
    blender = shutil.which("blender")
    if not blender:
        return {
            "ok": False, "tool": "blender", "engine": None,
            "detail": "Blender CLI未検出（生成スクリプトは保存済み）",
            "artifacts": [str(script_path)],
        }
    from core import process

    result = process.run_command(
        [blender, "--background", "--python", str(script_path.resolve())],
        timeout_ms=180000, max_output_bytes=300_000, kill_process_tree=True,
    )
    ok = result.ok and blend_path.exists()
    artifacts = [str(script_path)] + ([str(blend_path)] if blend_path.exists() else [])
    return {
        "ok": ok, "tool": "blender", "engine": None,
        "detail": str(blend_path) if ok else (result.error or "Blender資産生成失敗"),
        "artifacts": artifacts,
    }
