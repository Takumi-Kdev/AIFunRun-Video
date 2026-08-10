"""統合エンジン層（AIFunRun-Video スタンドアロン版）。

動画創作ファクトリーが使うツールのみ登録する:
  - blender   : BlenderMCP（Blender をテキスト/コード駆動）
  - gen3d     : 3D資産生成（TripoSR/TRELLIS/Hunyuan3D）
  - motion    : モーションキャプチャ/リグ変換
  - video2d   : テキスト→映像（ffmpeg フォールバックで実動画）
  - animate   : シーン/カメラ/レンダーの bpy スクリプト生成
  - tts       : 音声合成（Piper/espeak）
  - moderation: 投稿前の安全ゲート
  - video_edit: TK-CutExpress 連携（編集工程）
"""
from __future__ import annotations

from core import tool_layer
from core.tool_layer import Tool, ToolResult
from core.logger import write_log
from core import tts as tts_engine


class TTSTool(Tool):
    """テキスト→音声（Piper/espeak フォールバック）。"""

    name = "tts"
    description = "テキストを音声合成する（Piper/espeak）"

    def health(self) -> bool:
        return any(tts_engine.available().values())

    def setup(self) -> ToolResult:
        return ToolResult(ok=False, error="TTS バックエンドが利用不可") if not self.health() else ToolResult(ok=True)

    def run(self, **kwargs):
        text = kwargs.get("text", "")
        out = kwargs.get("out")
        path = tts_engine.synthesize(text, __import__("pathlib").Path(out)) if text else None
        if not path:
            return ToolResult(ok=False, error="TTS 失敗（バックエンドなし）")
        return ToolResult(ok=True, artifacts=[str(path)], data=str(path))


def register_all(registry: tool_layer.ToolRegistry) -> None:
    from .blender import BlenderTool
    from .gen3d import Gen3DTool
    from .motion import MotionTool
    from .video2d import Video2DTool
    from .animate import AnimateTool
    from .moderation import ModerationTool
    from .tk_cut import TKCutExpressTool
    from .scene import SceneTool
    from .media_edit import MediaEditTool
    registry.register(TTSTool())
    registry.register(BlenderTool())
    registry.register(Gen3DTool())
    registry.register(MotionTool())
    registry.register(Video2DTool())
    registry.register(AnimateTool())
    registry.register(ModerationTool())
    registry.register(TKCutExpressTool())
    registry.register(SceneTool())
    registry.register(MediaEditTool())
    write_log(f"エンジン登録: {registry.names()}", "INFO")


def bootstrap() -> tool_layer.ToolRegistry:
    """共有レジストリへエンジンを登録し、返す。"""
    reg = tool_layer.get_registry()
    expected = {"tts", "blender", "gen3d", "motion", "video2d", "animate", "moderation", "video_edit", "scene", "media_edit"}
    if expected.issubset(reg.names()):
        return reg
    register_all(reg)
    return reg
