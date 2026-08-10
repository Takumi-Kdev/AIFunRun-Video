"""3D資産生成ツール（動画創作ファクトリーの資産工程）。

画像/テキスト → 3Dモデル（GLB/OBJ）を生成し、Blender にインポートできるようにする。

バックエンド（優先順・いずれもメインPCで使用）:
  1. TripoSR  (`tsr`,  MIT)        : 画像→3D 高速 (要 ~6GB VRAM)
  2. TRELLIS  (`trellis`, MIT)     : 画像/テキスト→3D (要 ~16GB VRAM)
  3. Hunyuan3D (`hy3dgen`, Tencent): 画像→textured 3D (Blenderアドオン+API有)

本アダプタ:
  - バックエンド検出（import で確認）
  - generate: バックエンドがあれば実際に3D生成。無ければ「生産指示 + Blenderインポート準備」を出力（必ず動く原則）
  - blender_import_script: GLBパス → Blender(bpy) インポートコード文字列を生成
"""
from __future__ import annotations

import importlib
import json
from datetime import datetime, timezone
from pathlib import Path

from core.logger import write_log
from core.tool_layer import Tool, ToolResult

BACKENDS = ["tsr", "trellis", "hy3dgen"]


def _module(name: str):
    try:
        return importlib.import_module(name)
    except Exception:  # noqa: BLE001
        return None


def detect_backends() -> dict:
    """利用可能な3Dバックエンドを検出。"""
    return {
        "triposr": _module("tsr") is not None,
        "trellis": _module("trellis") is not None,
        "hunyuan3d": _module("hy3dgen") is not None,
    }


def build_import_script(glb_path: str, target_name: str | None = None) -> str:
    """GLBパス → Blender(bpy) でインポートするコード文字列。

    BlenderMCP の execute_code でそのまま実行できる（namespace に bpy がある）。
    """
    safe = json.dumps(glb_path)
    name = target_name or "Asset"
    return (
        "import bpy\n"
        "# --- gen3d: 3D資産をBlenderへインポート ---\n"
        f"bpy.ops.wm.read_factory_settings(use_empty=True)\n"
        f"bpy.ops.import_scene.gltf(filepath={safe})\n"
        "# インポートしたオブジェクトをまとめて原点へ\n"
        "bpy.ops.object.select_all(action='SELECT')\n"
        "bpy.context.view_layer.objects.active = bpy.context.selected_objects[0]\n"
        f"obj = bpy.context.active_object or bpy.data.objects['{name}']\n"
        "bpy.ops.object.origin_set(type='ORIGIN_CENTER_OF_MASS', center='BOUNDS')\n"
        "obj.location = (0, 0, 0)\n"
        "print('imported_3d_asset')"
    )


def build_placeholder_script(asset_type: str = "low_poly") -> str:
    """バックエンド無しでも Blender に最小シーンを作るコード（プレースホルダ資産）。"""
    return (
        "import bpy\n"
        "# --- gen3d: プレースホルダ資産（実バックエンド未接続） ---\n"
        "bpy.ops.wm.read_factory_settings(use_empty=True)\n"
        "bpy.ops.mesh.primitive_ico_sphere_add(radius=0.6, location=(0, 0, 0))\n"
        "mat = bpy.data.materials.new('AssetMat')\n"
        "mat.diffuse_color = (0.2, 0.6, 0.9, 1.0)\n"
        "bpy.context.active_object.data.materials.append(mat)\n"
        "print('placeholder_asset_created')"
    )


def _write_plan(out_dir: Path, topic: str, reason: str) -> Path:
    """実バックエンドが無い時の生産指示ファイルを出力。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")
    plan = out_dir / "gen3d_plan.md"
    plan.write_text(
        f"# gen3d 生産指示\n\n"
        f"対象: {topic}\n日時: {ts}\n理由: {reason}\n\n"
        "バックエンド（TripoSR / TRELLIS / Hunyuan3D）をメインPCで有効にすると、"
        "画像/テキストから GLB を自動生成し Blender へインポートできます。\n\n"
        "生成後は build_import_script() が返す bpy コードを blender execute_code で実行してください。\n",
        encoding="utf-8",
    )
    return plan


class Gen3DTool(Tool):
    name = "gen3d"
    description = "画像/テキスト→3D資産生成（TripoSR/TRELLIS/Hunyuan3D）とBlenderインポートコード生成"

    def health(self) -> bool:
        return any(detect_backends().values())

    def setup(self) -> ToolResult:
        return ToolResult(ok=True, data=detect_backends())

    def run(self, **kwargs) -> ToolResult:
        action = kwargs.get("action", "health")

        if action == "health":
            det = detect_backends()
            return ToolResult(ok=any(det.values()), data=det)

        if action == "blender_import_script":
            glb = kwargs.get("glb", "")
            if not glb:
                return ToolResult(ok=False, error="glb パスが必要")
            script = build_import_script(glb, kwargs.get("name"))
            return ToolResult(ok=True, data={"code": script})

        if action == "generate":
            image = kwargs.get("image", "")
            topic = kwargs.get("topic", "3D資産")
            out = kwargs.get("out_dir", "")
            if not image:
                return ToolResult(ok=False, error="image パスが必要")
            out_dir = Path(out) if out else Path("output/3d")
            det = detect_backends()
            try:
                if det.get("triposr"):
                    path = _generate_triposr(image, out_dir)
                elif det.get("trellis"):
                    path = _generate_trellis(image, out_dir)
                elif det.get("hunyuan3d"):
                    path = _generate_hunyuan(image, out_dir)
                else:
                    plan = _write_plan(out_dir, topic, "3Dバックエンド未検出（要メインPC）")
                    return ToolResult(
                        ok=False,
                        data={"plan": str(plan), "placeholder_script": build_placeholder_script()},
                        error=f"3Dバックエンドなし。生産指示書を出力: {plan}",
                        artifacts=[str(plan)],
                    )
                return ToolResult(ok=True, data={"glb": str(path)}, artifacts=[str(path)])
            except Exception as e:  # noqa: BLE001
                plan = _write_plan(out_dir, topic, f"生成失敗: {e}")
                return ToolResult(ok=False, data={"plan": str(plan)}, error=f"3D生成失敗: {e}",
                                  artifacts=[str(plan)])

        return ToolResult(ok=False, error=f"未知 action: {action}")


def _generate_triposr(image: str, out_dir: Path) -> Path:
    # TripoSR: tsr.pipeline 経由で画像→メッシュ
    from tsr.basics import load_image  # type: ignore  # noqa: F401
    from tsr.pipeline import TSR  # type: ignore
    tsr = TSR.from_pretrained("stabilityai/TripoSR")
    out_dir.mkdir(parents=True, exist_ok=True)
    model = tsr(image)
    path = out_dir / "asset.obj"
    model.save(path)  # type: ignore[attr-defined]
    return path


def _generate_trellis(image: str, out_dir: Path) -> Path:
    from trellis.pipelines import TrellisImageTo3DPipeline  # type: ignore
    import imageio  # noqa: F401
    from PIL import Image
    pipeline = TrellisImageTo3DPipeline.from_pretrained("microsoft/TRELLIS-image-large")
    outputs = pipeline.run(Image.open(image))
    out_dir.mkdir(parents=True, exist_ok=True)
    glb = out_dir / "asset.glb"
    from trellis.utils import postprocessing_utils  # type: ignore
    out = postprocessing_utils.to_glb(outputs["gaussian"][0], outputs["mesh"][0])
    out.export(str(glb))
    return glb


def _generate_hunyuan(image: str, out_dir: Path) -> Path:
    from hy3dgen.shapegen import Hunyuan3DDiTFlowMatchingPipeline  # type: ignore
    pipeline = Hunyuan3DDiTFlowMatchingPipeline.from_pretrained("tencent/Hunyuan3D-2mini")
    out_dir.mkdir(parents=True, exist_ok=True)
    mesh = pipeline(image=image)[0]
    path = out_dir / "asset.glb"
    mesh.export(str(path))  # type: ignore[attr-defined]
    return path
