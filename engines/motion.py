"""モーション・アニメーション生成ツール（工場のキャラ/動き工程）。

MediaPipe（Apache2.0）の pose/face/hands でモーションキャプチャを行い、
結果を Blender リグ（Armature）のキーフレームへ変換する bpy コードを生成する。
バックエンドが無い場合も、手続き的（プロシージャル）アニメーションの bpy コードを
生成できるため「必ず動く」（実在する動きを作れる）。

Actions:
  - health         : バックエンド検出（mediapipe + opencv）
  - capture        : 映像→ポーズ骨格キーポイント (JSON)
  - to_blender_rig : キーポイント→ Armature 骨のキーフレーム bpy コード
  - procedural_idle: バックエンド無しでも動く簡易アイドルアニメ bpy コード
"""
from __future__ import annotations

import importlib
import json
from datetime import datetime, timezone
from pathlib import Path

from core.logger import write_log
from core.tool_layer import Tool, ToolResult

# 一般的な Armature ボーン名（簡易リグ用）
_BONE = "bone_rotation"


def _module(name: str):
    try:
        return importlib.import_module(name)
    except Exception:  # noqa: BLE001
        return None


def detect_backends() -> dict:
    return {
        "mediapipe": _module("mediapipe") is not None,
        "opencv": _module("cv2") is not None,
    }


def build_idle_script(bone: str = _BONE, frames: int = 90) -> str:
    """バックエンド無しでも動く、ボーンを揺らす簡易アイドルアニメの bpy コード。"""
    return (
        "import bpy, math\n"
        f"# --- motion: プロシージャル・アイドルアニメ ---\n"
        f"arm = bpy.data.objects.get('Armature') or bpy.context.active_object\n"
        "bpy.context.view_layer.objects.active = arm\n"
        "bpy.ops.object.mode_set(mode='POSE')\n"
        "bpy.context.scene.frame_start = 1\n"
        f"bpy.context.scene.frame_end = {frames}\n"
        # ボーンが無ければ作成する
        "if arm.pose is None or not arm.pose.bones:\n"
        "    bpy.ops.object.mode_set(mode='OBJECT')\n"
        "    bpy.ops.object.armature_add(location=(0,0,0))\n"
        "    bpy.context.view_layer.objects.active = arm\n"
        "    bpy.ops.object.mode_set(mode='POSE')\n"
        # キーフレームを打つ
        "arm.pose.bones[0].rotation_mode = 'XYZ'\n"
        f"arm.pose.bones[0].rotation_euler = (0, 0, math.radians(10))\n"
        f"arm.pose.bones[0].keyframe_insert('rotation_euler', frame=1)\n"
        f"arm.pose.bones[0].rotation_euler = (0, 0, math.radians(-10))\n"
        f"arm.pose.bones[0].keyframe_insert('rotation_euler', frame={frames // 2})\n"
        f"arm.pose.bones[0].rotation_euler = (0, 0, math.radians(10))\n"
        f"arm.pose.bones[0].keyframe_insert('rotation_euler', frame={frames})\n"
        "print('idle_animation_created')"
    )


def build_rig_script(keypoints: list[dict], bone: str = _BONE) -> str:
    """MediaPipe キーポイント → Armature 骨の回転キーフレーム bpy コード。

    keypoints: [{"frame": int, "x": float, "y": float, "z": float}, ...]
    簡易実装として、キーポイントの移動量をボーンの rotation へマッピングする。
    """
    if not keypoints:
        raise ValueError("keypoints が空")
    frames = []
    for kp in keypoints:
        f = int(kp.get("frame", 1))
        # x/y/z の微小変位を回転(radian)に変換
        rx = float(kp.get("x", 0.0)) * 0.01
        ry = float(kp.get("y", 0.0)) * 0.01
        rz = float(kp.get("z", 0.0)) * 0.01
        frames.append(f"({f}, {rx:.5f}, {ry:.5f}, {rz:.5f})")
    key_lines = ",\n    ".join(frames)
    return (
        "import bpy\n"
        f"# --- motion: モーションキャプチャ→リグ ---\n"
        f"arm = bpy.data.objects.get('Armature') or bpy.context.active_object\n"
        "bpy.context.view_layer.objects.active = arm\n"
        "bpy.ops.object.mode_set(mode='POSE')\n"
        "pose = arm.pose.bones[0]\n"
        "pose.rotation_mode = 'XYZ'\n"
        "# (frame, rx, ry, rz)\n"
        f"keys = [\n    {key_lines},\n]\n"
        "for f, rx, ry, rz in keys:\n"
        "    pose.rotation_euler = (rx, ry, rz)\n"
        "    pose.keyframe_insert('rotation_euler', frame=f)\n"
        "bpy.context.scene.frame_start = keys[0][0]\n"
        "bpy.context.scene.frame_end = keys[-1][0]\n"
        "print('rig_animation_created')"
    )


def _write_plan(out_dir: Path, topic: str, reason: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")
    plan = out_dir / "motion_plan.md"
    plan.write_text(
        f"# motion 生産指示\n\n対象: {topic}\n日時: {ts}\n理由: {reason}\n\n"
        "MediaPipe (mediapipe+opencv) をメインPCで有効にすると、動画から骨格を"
        "キャプチャして Blender リグへ自動変換できます。\n"
        "未接続時は procedural_idle の bpy コードを blender execute_code で実行すると"
        "手続き的アニメが作れます。\n",
        encoding="utf-8",
    )
    return plan


class MotionTool(Tool):
    name = "motion"
    description = "モーションキャプチャ/アニメ生成（MediaPipe→リグ変換・手続きアニメ）"

    def health(self) -> bool:
        det = detect_backends()
        return bool(det.get("mediapipe") and det.get("opencv"))

    def setup(self) -> ToolResult:
        return ToolResult(ok=True, data=detect_backends())

    def run(self, **kwargs) -> ToolResult:
        action = kwargs.get("action", "health")

        if action == "health":
            det = detect_backends()
            return ToolResult(ok=bool(det.get("mediapipe") and det.get("opencv")), data=det)

        if action == "procedural_idle":
            code = build_idle_script(kwargs.get("bone", _BONE), int(kwargs.get("frames", 90)))
            return ToolResult(ok=True, data={"code": code})

        if action == "to_blender_rig":
            raw = kwargs.get("keypoints", "[]")
            try:
                keypoints = json.loads(raw) if isinstance(raw, str) else raw
            except json.JSONDecodeError as e:
                return ToolResult(ok=False, error=f"keypoints が不正: {e}")
            if not keypoints:
                return ToolResult(ok=False, error="keypoints が空")
            code = build_rig_script(keypoints, kwargs.get("bone", _BONE))
            return ToolResult(ok=True, data={"code": code, "frame_count": len(keypoints)})

        if action == "capture":
            video = kwargs.get("video", "")
            if not video:
                return ToolResult(ok=False, error="video パスが必要")
            det = detect_backends()
            if not (det.get("mediapipe") and det.get("opencv")):
                plan = _write_plan(Path(kwargs.get("out_dir", "output/motion")), "motion",
                                   "MediaPipe未検出（要メインPC）")
                return ToolResult(ok=False, data={"plan": str(plan),
                                                  "idle_script": build_idle_script()},
                                  error="MediaPipe未検出", artifacts=[str(plan)])
            try:
                keypoints = _capture_mediapipe(video)
                out_dir = Path(kwargs.get("out_dir", "output/motion"))
                out_dir.mkdir(parents=True, exist_ok=True)
                out_json = out_dir / "pose_keypoints.json"
                out_json.write_text(json.dumps(keypoints, ensure_ascii=False), encoding="utf-8")
                return ToolResult(ok=True, data={"keypoints": str(out_json), "count": len(keypoints)},
                                  artifacts=[str(out_json)])
            except Exception as e:  # noqa: BLE001
                return ToolResult(ok=False, error=f"capture 失敗: {e}")

        return ToolResult(ok=False, error=f"未知 action: {action}")


def _capture_mediapipe(video: str) -> list[dict]:
    """MediaPipe Pose で動画の骨格キーポイントを抽出（簡易・数フレーム）。"""
    import cv2  # type: ignore
    import mediapipe as mp  # type: ignore
    cap = cv2.VideoCapture(video)
    pose = mp.solutions.pose.Pose()
    out: list[dict] = []
    frame_idx = 0
    while cap.isOpened():
        ok, frame = cap.read()
        if not ok or frame is None:
            break
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        res = pose.process(rgb)
        if res.pose_landmarks:
            lm = res.pose_landmarks.landmark[0]
            out.append({"frame": frame_idx, "x": lm.x, "y": lm.y, "z": lm.z})
        frame_idx += 1
        if frame_idx > 60:
            break
    cap.release()
    return out
