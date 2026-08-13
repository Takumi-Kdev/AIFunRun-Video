"""AIFunRun-Video MCP サーバー: コーディングシステム（opencode / Claude Code / Codex）から
動画創作システムを操作できるようにする。

  起動:  python3 -m core.mcp_server      （stdio サーバー）

外部エージェントは MCP クライアントとして接続し、以下を呼べる:
  - video_factory     : プロンプトから動画を工場で生成
  - video_scene       : プロンプトから Blender シーン生成
  - video_scene_types : シーンタイプ一覧
  - video_studio_run  : トラック指定で生成
  - video_studio_status: 全トラック状況
  - video_media_edit  : FFmpeg で画像/動画を編集
  - video_composite   : Blender オーバーレイ合成
  - video_check       : セットアップ検証
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import CallToolRequestParams, CallToolResult, ListToolsRequest, ListToolsResult, TextContent, Tool

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

_TOOLS: dict[str, dict] = {}


def _tool(name: str, description: str, schema: dict) -> None:
    _TOOLS[name] = {"description": description, "schema": schema}


def _define_tools() -> None:
    _tool("video_create", "一文の意図から企画・絵コンテ・音声・編集・品質検査まで行い完成動画を自律創作",
          {"type": "object", "properties": {"instruction": {"type": "string"}, "template": {"type": "string"}},
           "required": ["instruction"]})
    _tool("video_brief", "動画をレンダーせず、意図からAI作品設計と全ショットを提案",
          {"type": "object", "properties": {"instruction": {"type": "string"}, "template": {"type": "string"}},
           "required": ["instruction"]})
    _tool("video_revise", "既存creative_plan.jsonへ自然言語で追加指示し動画を再創作",
          {"type": "object", "properties": {"plan": {"type": "string"}, "feedback": {"type": "string"}},
           "required": ["plan", "feedback"]})
    _tool("video_factory", "プロンプトから動画を生成（工場型・シーン/音声/編集）",
          {"type": "object", "properties": {"instruction": {"type": "string"}, "template": {"type": "string"}},
           "required": ["instruction"]})
    _tool("video_scene", "プロンプトから Blender シーン(bpyコード)を生成",
          {"type": "object", "properties": {"prompt": {"type": "string"}, "scene_type": {"type": "string"}},
           "required": ["prompt"]})
    _tool("video_scene_types", "シーンタイプ一覧", {"type": "object", "properties": {}})
    _tool("video_studio_run", "トラック指定で動画を生成（アカウント×路線分離）",
          {"type": "object", "properties": {"track": {"type": "string"}, "instruction": {"type": "string"}},
           "required": ["track", "instruction"]})
    _tool("video_studio_status", "全トラックの状況", {"type": "object", "properties": {}})
    _tool("video_media_edit", "FFmpeg で画像/動画を編集（形式/速度/トリム/字幕/テキスト/音声）",
          {"type": "object", "properties": {
              "input": {"type": "string"}, "out": {"type": "string"}, "format": {"type": "string"},
              "speed": {"type": "number"}, "text": {"type": "string"}, "audio": {"type": "string"}},
           "required": ["input", "out"]})
    _tool("video_composite", "ベース映像に Blender RGBA オーバーレイを合成",
          {"type": "object", "properties": {"base": {"type": "string"}, "overlay": {"type": "string"}, "out": {"type": "string"}},
           "required": ["base", "overlay", "out"]})
    _tool("video_music", "テキスト(ムード)からBGM生成・動画へ合成",
          {"type": "object", "properties": {"mood": {"type": "string"}, "out": {"type": "string"},
           "video": {"type": "string"}}})
    _tool("video_image", "テキストから2D画像/サムネイル/背景を生成",
          {"type": "object", "properties": {"action": {"type": "string"}, "prompt": {"type": "string"},
           "video": {"type": "string"}, "out": {"type": "string"}, "title": {"type": "string"}},
           "required": ["action"]})
    _tool("video_transcribe", "音声→字幕SRT生成・字幕焼き込み",
          {"type": "object", "properties": {"media": {"type": "string"}, "video": {"type": "string"},
           "srt": {"type": "string"}, "out": {"type": "string"}, "action": {"type": "string"}},
           "required": ["action"]})
    _tool("video_model", "プロンプトから最適なモデリング手法(CAD/OpenSCAD/FreeCAD/gen3d/Blender)を選択し3D生成",
          {"type": "object", "properties": {"prompt": {"type": "string"}, "tool": {"type": "string"}},
           "required": ["prompt"]})
    _tool("video_check", "セットアップ検証", {"type": "object", "properties": {}})


def _call_tool(name: str, arguments: dict) -> dict:
    from engines import bootstrap
    reg = bootstrap()

    if name in ("video_create", "video_factory"):
        from core import factory
        return factory.run(str(arguments.get("instruction", "")),
                           str(arguments.get("template") or None) or None)
    if name == "video_brief":
        from core import creative, factory
        instruction = str(arguments.get("instruction", ""))
        selected = str(arguments.get("template") or "") or factory._detect_template(instruction)
        tmpl = factory.load_template(selected) or factory.load_template(factory.DEFAULT_TEMPLATE) or {}
        plan = creative.create_plan(instruction, tmpl)
        plan["template_id"] = selected
        return {"ok": True, "data": plan}
    if name == "video_revise":
        from pathlib import Path
        from core import factory
        path = Path(str(arguments.get("plan", "")))
        if not path.exists():
            return {"ok": False, "error": f"作品設計が見つかりません: {path}"}
        plan = json.loads(path.read_text(encoding="utf-8"))
        instruction = f"{plan.get('instruction', plan.get('concept', '動画'))}\n追加の演出指示: {arguments.get('feedback', '')}"
        return factory.run(instruction, str(plan.get("template_id") or "") or None, label="revision")
    if name == "video_scene":
        from engines import scene
        prompt = str(arguments.get("prompt", ""))
        stype = str(arguments.get("scene_type") or "") or scene.classify(prompt)
        code = scene.build_scene(prompt, scene_type=stype)
        return {"ok": True, "data": {"scene_type": stype, "code": code}}
    if name == "video_scene_types":
        from engines import scene
        return {"ok": True, "data": {"types": scene.types()}}
    if name == "video_studio_run":
        from core import studio
        return studio.run_track(str(arguments.get("track", "")), str(arguments.get("instruction", "")))
    if name == "video_studio_status":
        from core import studio
        return {"ok": True, "data": studio.studio_status()}
    if name == "video_media_edit":
        res = reg.call("media_edit", action="edit", input=str(arguments.get("input", "")),
                       out=str(arguments.get("out", "")), format=arguments.get("format"),
                       speed=float(arguments.get("speed", 1.0)), text=arguments.get("text"),
                       audio=arguments.get("audio"))
        return {"ok": res.ok, "data": res.data, "error": res.error}
    if name == "video_composite":
        res = reg.call("media_edit", action="composite", base=str(arguments.get("base", "")),
                       overlay=str(arguments.get("overlay", "")), out=str(arguments.get("out", "")))
        return {"ok": res.ok, "data": res.data, "error": res.error}
    if name == "video_music":
        if arguments.get("video"):
            mres = reg.call("music", action="generate", mood=str(arguments.get("mood", "calm")),
                            out=str(arguments.get("out", "output/bgm.mp3")))
            if mres.ok and arguments.get("video"):
                add = reg.call("music", action="add_bgm", video=str(arguments.get("video")),
                               music=str(arguments.get("out", "output/bgm.mp3")),
                               out="output/final_with_bgm.mp4", volume=0.35)
                return {"ok": add.ok, "data": add.data, "error": add.error}
            return {"ok": mres.ok, "data": mres.data, "error": mres.error}
        mres = reg.call("music", action="generate", mood=str(arguments.get("mood", "calm")),
                        out=str(arguments.get("out", "output/bgm.mp3")))
        return {"ok": mres.ok, "data": mres.data, "error": mres.error}
    if name == "video_image":
        action = str(arguments.get("action", "generate"))
        res = reg.call("imaging", action=action, prompt=str(arguments.get("prompt", "")),
                       video=str(arguments.get("video", "")), out=str(arguments.get("out", "output/image.png")),
                       title=str(arguments.get("title", "")))
        return {"ok": res.ok, "data": res.data, "error": res.error}
    if name == "video_transcribe":
        action = str(arguments.get("action", "transcribe"))
        res = reg.call("transcribe", action=action, media=str(arguments.get("media", "")),
                       video=str(arguments.get("video", "")), srt=str(arguments.get("srt", "")),
                       out=str(arguments.get("out", "output/subtitle.srt")))
        return {"ok": res.ok, "data": res.data, "error": res.error}
    if name == "video_model":
        from core import model_router
        prompt = str(arguments.get("prompt", ""))
        tool = str(arguments.get("tool", "") or "") or None
        routed = model_router.route(prompt)
        result = model_router.build_asset(prompt, tool=tool)
        return {"ok": result["ok"], "data": {"routed": routed, "result": result}}
    if name == "video_check":
        import subprocess
        r = subprocess.run([sys.executable, os.path.join(ROOT, "run.py"), "check"],
                           capture_output=True, text=True, timeout=60)
        return {"ok": r.returncode == 0, "data": {"output": (r.stdout + r.stderr)[-1500:]}}
    return {"ok": False, "error": f"未知ツール: {name}"}


server = Server("aifunrun-video")


async def _on_list_tools(request: ListToolsRequest) -> ListToolsResult:
    return ListToolsResult(tools=[Tool(name=n, description=d["description"], inputSchema=d["schema"])
                                  for n, d in _TOOLS.items()])


async def _on_call_tool(_ctx, request: CallToolRequestParams) -> CallToolResult:
    try:
        result = _call_tool(request.name, request.arguments or {})
        return CallToolResult(content=[TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))])
    except Exception as e:  # noqa: BLE001
        return CallToolResult(isError=True, content=[TextContent(type="text",
                              text=json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))])


async def run_server() -> None:
    _define_tools()
    server.add_request_handler("tools/list", ListToolsRequest, _on_list_tools)
    server.add_request_handler("tools/call", CallToolRequestParams, _on_call_tool)
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


def main() -> None:
    import asyncio
    asyncio.run(run_server())


if __name__ == "__main__":
    main()
