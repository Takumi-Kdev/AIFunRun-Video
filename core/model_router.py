"""モデリングツール振り分けルーター（使い分けの呼び出しを正確に）。

プロンプトから、最適な3Dモデリング手法を正確に選んで呼ぶ。
  - CAD（OpenSCAD/FreeCAD）: 精密・パラメトリック・工業的形状（歯車/筐体/ブラケット等）
  - gen3d（TripoSR/TRELLIS）: 画像/実物 → 3D
  - Blender（シーン演出）   : 有機・キャラクター・シーン・アニメーション

route(prompt) で判定 → build_asset(prompt) で該当エンジンを呼ぶ。
"""
from __future__ import annotations

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
    r = route(prompt) if tool is None else {"tool": tool, "engine": None, "reason": "明示指定"}
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
        from pathlib import Path
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        # 画像未指定時はフォールバック（gen3d は画像前提）。プレースホルダ/計画を返す。
        res = reg.call("gen3d", action="generate", image="", topic=prompt, out_dir=out_dir)
        return {
            "ok": bool(res.ok), "tool": "gen3d", "engine": None,
            "detail": (res.error or "3D再構成"), "artifacts": res.artifacts,
        }
    # Blender: シーン演出は scene 工程で生成（ここでは準備を返す）
    return {"ok": True, "tool": "blender", "engine": None,
            "detail": "Blenderシーン生成（scene工程）", "artifacts": []}
