"""BlenderMCP 連携ツールのテスト（モックBlenderサーバーで検証）。

Blender は開発PCに無いため、実ソケットではなくスレッドのモックサーバーを立て、
BlenderMCP の JSON プロトコルを再現してクライアント/ツールを検証する。
"""
from __future__ import annotations

import json
import socket
import threading
import time

from engines.blender import BlenderMCPClient, BlenderTool


def _start_mock_server(handler):
    """モックBlenderMCPサーバー。handler(cmd: dict) -> dict が応答を返す。"""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", 0))
    server.listen(5)
    port = server.getsockname()[1]

    def _loop():
        while True:
            try:
                conn, _ = server.accept()
            except OSError:
                break
            with conn:
                data = conn.recv(8192)
                try:
                    cmd = json.loads(data.decode("utf-8"))
                    resp = handler(cmd)
                except Exception as e:  # noqa: BLE001
                    resp = {"status": "error", "message": str(e)}
                conn.sendall(json.dumps(resp).encode("utf-8"))
            break  # 1コマンド受信で切断

    t = threading.Thread(target=_loop, daemon=True)
    t.start()
    return server, port


def _stop_server(server):
    try:
        server.close()
    except Exception:  # noqa: BLE001
        pass


def _scene_handler(cmd):
    if cmd.get("type") == "get_scene_info":
        return {"status": "success", "result": {"name": "Scene", "object_count": 2,
                                                "objects": [{"name": "Cube", "type": "MESH"}], "materials_count": 1}}
    if cmd.get("type") == "get_object_info":
        return {"status": "success", "result": {"name": cmd.get("params", {}).get("name"), "type": "MESH"}}
    if cmd.get("type") == "execute_code":
        code = cmd.get("params", {}).get("code", "")
        return {"status": "success", "result": {"executed": True, "result": f"ran:{len(code)}"}}
    return {"status": "error", "message": f"unknown:{cmd.get('type')}"}


def test_client_get_scene_info():
    server, port = _start_mock_server(_scene_handler)
    try:
        client = BlenderMCPClient(host="127.0.0.1", port=port)
        info = client.get_scene_info()
        assert info["object_count"] == 2
        assert info["objects"][0]["name"] == "Cube"
    finally:
        _stop_server(server)


def test_client_execute_code():
    server, port = _start_mock_server(_scene_handler)
    try:
        client = BlenderMCPClient(host="127.0.0.1", port=port)
        result = client.execute_code("import bpy; print(bpy.app.version)")
        assert result["executed"] is True
        assert "ran:" in result["result"]
    finally:
        _stop_server(server)


def test_client_unreachable_health_false():
    # 誰もいないポートに対して接続失敗 → health_check は False
    client = BlenderMCPClient(host="127.0.0.1", port=1, timeout=0.5)
    assert client.health_check() is False


def test_tool_get_scene_info():
    server, port = _start_mock_server(_scene_handler)
    try:
        tool = BlenderTool(client=BlenderMCPClient(host="127.0.0.1", port=port))
        res = tool.run(action="get_scene_info")
        assert res.ok is True
        assert res.data["object_count"] == 2
    finally:
        _stop_server(server)


def test_tool_execute_code_requires_approve():
    server, port = _start_mock_server(_scene_handler)
    try:
        tool = BlenderTool(client=BlenderMCPClient(host="127.0.0.1", port=port))
        # approve なし → 却下（安全）
        res = tool.run(action="execute_code", code="print('x')")
        assert res.ok is False
        assert "approve" in res.error
        # approve あり → 実行
        res2 = tool.run(action="execute_code", code="print('x')", approve=True)
        assert res2.ok is True
        assert res2.data["executed"] is True
    finally:
        _stop_server(server)


def test_tool_unknown_action():
    server, port = _start_mock_server(_scene_handler)
    try:
        tool = BlenderTool(client=BlenderMCPClient(host="127.0.0.1", port=port))
        res = tool.run(action="not_a_real_action")
        assert res.ok is False
        assert "未知" in res.error
    finally:
        _stop_server(server)


def test_tool_health_when_server_down():
    tool = BlenderTool(client=BlenderMCPClient(host="127.0.0.1", port=1, timeout=0.5))
    res = tool.run(action="health")
    assert res.data["connected"] is False
