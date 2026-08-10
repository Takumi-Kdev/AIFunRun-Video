"""BlenderMCP 連携ツール（動画創作ファクトリーのシーン・レンダー工程）。

BlenderMCP (`ahujasid/blender-mcp`・MIT) は、Blender 内のアドオンが TCP ソケット
サーバーを立て、MCP 経由で LLM が Blender をテキスト/コード駆動できるようにする。

プロトコル（ソケット・JSON）:
  → 送信: {"type": "<コマンド>", "params": {...}}
  ← 受信: {"status": "success", "result": ...}
           {"status": "error", "message": "..."}

本アダプタ:
  - BlenderMCP のソケットプロトコルを Python クライアントとして実装
  - 読み取り系（シーン/オブジェクト情報）は即実行
  - execute_code（任意コード実行）は危険なため approve=True 必須（承認制）
  - Blender 未接続でも安全に「要セットアップ」を返す（必ず動く原則）
  - 接続先は env BLENDER_HOST / BLENDER_PORT で変更可能（メインPCのリモート実行用）
"""
from __future__ import annotations

import json
import os
import socket

from core.logger import write_log
from core.tool_layer import Tool, ToolResult

DEFAULT_HOST = "localhost"
DEFAULT_PORT = 9876

# 危険な任意コード実行以外は、読み取り専用で自由に使える
READ_ACTIONS = ("get_scene_info", "get_object_info", "get_viewport_screenshot")


def _resolve_host() -> str:
    return os.getenv("BLENDER_HOST", DEFAULT_HOST)


def _resolve_port() -> int:
    try:
        return int(os.getenv("BLENDER_PORT", str(DEFAULT_PORT)))
    except ValueError:
        return DEFAULT_PORT


class BlenderMCPClient:
    """BlenderMCP ソケットサーバーへの TCP クライアント（JSON プロトコル）。"""

    def __init__(self, host: str | None = None, port: int | None = None, timeout: float = 15.0):
        self.host = host or _resolve_host()
        self.port = int(port) if port else _resolve_port()
        self.timeout = timeout

    def send(self, command: dict) -> dict:
        """1コマンド送信し、完全な JSON 応答を返す。応答が揃うまで受信を続ける。"""
        with socket.create_connection((self.host, self.port), timeout=self.timeout) as sock:
            sock.settimeout(self.timeout)
            sock.sendall(json.dumps(command).encode("utf-8"))
            data = b""
            while True:
                chunk = sock.recv(8192)
                if not chunk:
                    break
                data += chunk
                try:
                    return json.loads(data.decode("utf-8"))
                except json.JSONDecodeError:
                    # まだJSONが完結していない → 続きを待つ
                    continue
        raise ConnectionError("BlenderMCP 応答が読み取れませんでした")

    def call(self, cmd_type: str, params: dict | None = None) -> dict:
        """コマンド実行。成功なら result、失敗なら例外。"""
        resp = self.send({"type": cmd_type, "params": params or {}})
        if resp.get("status") == "success":
            return resp.get("result")
        raise RuntimeError(resp.get("message", f"unknown error: {cmd_type}"))

    def get_scene_info(self) -> dict:
        return self.call("get_scene_info")

    def get_object_info(self, name: str) -> dict:
        return self.call("get_object_info", {"name": name})

    def execute_code(self, code: str) -> dict:
        return self.call("execute_code", {"code": code})

    def health_check(self) -> bool:
        try:
            self.get_scene_info()
            return True
        except Exception:  # noqa: BLE001
            return False


class BlenderTool(Tool):
    name = "blender"
    description = "BlenderMCP 経由で Blender をテキスト/コード駆動（シーン情報・オブジェクト・コード実行）"

    def __init__(self, client: BlenderMCPClient | None = None):
        self._client = client or BlenderMCPClient()

    def health(self) -> bool:
        return self._client.health_check()

    def setup(self) -> ToolResult:
        if self.health():
            return ToolResult(ok=True)
        return ToolResult(
            ok=False,
            error=(
                "BlenderMCP 未接続。Blender で addon.py を有効化し MCPサーバを起動してください "
                f"({_resolve_host()}:{_resolve_port()})"
            ),
        )

    def run(self, **kwargs) -> ToolResult:
        action = kwargs.get("action", "health")

        if action == "health":
            ok = self.health()
            return ToolResult(ok=ok, data={"connected": ok, "host": self._client.host, "port": self._client.port})

        if action == "get_scene_info":
            try:
                return ToolResult(ok=True, data=self._client.get_scene_info())
            except Exception as e:  # noqa: BLE001
                return ToolResult(ok=False, error=f"Blender get_scene_info: {e}")

        if action == "get_object_info":
            obj_name = kwargs.get("object_name", "")
            if not obj_name:
                return ToolResult(ok=False, error="object_name が必要")
            try:
                return ToolResult(ok=True, data=self._client.get_object_info(obj_name))
            except Exception as e:  # noqa: BLE001
                return ToolResult(ok=False, error=f"Blender get_object_info: {e}")

        if action == "get_viewport_screenshot":
            filepath = kwargs.get("filepath", "")
            try:
                data = self._client.call("get_viewport_screenshot", {
                    "filepath": filepath, "format": kwargs.get("format", "png"),
                })
                artifacts = [filepath] if filepath else []
                return ToolResult(ok=True, data=data, artifacts=artifacts)
            except Exception as e:  # noqa: BLE001
                return ToolResult(ok=False, error=f"Blender screenshot: {e}")

        if action == "execute_code":
            code = kwargs.get("code", "")
            if not code:
                return ToolResult(ok=False, error="code が必要")
            if not kwargs.get("approve"):
                return ToolResult(ok=False, error="execute_code は approve=True が必要（任意コード実行のため承認必須）")
            try:
                return ToolResult(ok=True, data=self._client.execute_code(code))
            except Exception as e:  # noqa: BLE001
                return ToolResult(ok=False, error=f"Blender execute_code: {e}")

        return ToolResult(ok=False, error=f"未知 action: {action}")


def exec_approved(payload: dict) -> dict:
    """承認後の execute_code 実行（approval executor 用）。payload: {"code": ...}"""
    code = (payload or {}).get("code", "")
    if not code:
        return {"error": "code が必要"}
    try:
        result = BlenderMCPClient().execute_code(code)
        return {"ok": True, "result": result}
    except Exception as e:  # noqa: BLE001
        write_log(f"Blender execute_code(承認後) 失敗: {e}", "ERROR")
        return {"error": str(e)}
