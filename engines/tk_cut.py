"""TK-CutExpress 連携ツール（動画編集の強化）。

TK-CutExpress（Takumi-Kdev/TK-CutExpress・MIT）:
  video_analyzer.action(name, args) 統一IF / REST API(8787) / opencut-cli(Rust合成)
  音声認識・シーン検出・OCR・内容解析・SRT字幕・ハイライト短編・字幕焼き込み・
  縦型変換・無音除去・シーン分割・一括ワークフロー

本アダプタ:
  - モジュールが使えれば直接 action() を呼ぶ（システムPythonに editable install 済み）
  - 無ければ REST API(8787) にフォールバック
  - どちらも無ければ安全に「要セットアップ」を返す（必ず動く原則）
"""
from __future__ import annotations

import shutil
from pathlib import Path

from core.logger import write_log
from core.tool_layer import Tool, ToolResult

ACTIONS = ["transcribe", "scenes", "ocr", "analyze", "srt", "cut", "short",
           "subtitle", "trim", "reformat", "scene_split", "batch", "workflow"]


def _module_ok() -> bool:
    try:
        import video_analyzer  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False


def _server_ok(host: str = "127.0.0.1", port: int = 8787) -> bool:
    try:
        import urllib.request
        with urllib.request.urlopen(f"http://{host}:{port}/health", timeout=2) as r:
            return r.status == 200
    except Exception:  # noqa: BLE001
        return False


def _collect_artifacts(out_dir: str) -> list[str]:
    if not out_dir:
        return []
    p = Path(out_dir)
    if not p.exists():
        return []
    exts = (".mp4", ".srt", ".json", ".vtt", ".ass")
    files = sorted((f for f in p.rglob("*") if f.suffix in exts), key=lambda f: f.stat().st_mtime, reverse=True)
    return [str(f) for f in files[:20]]


class TKCutExpressTool(Tool):
    name = "video_edit"
    description = "TK-CutExpress 動画編集（解析/字幕/ショート/カット/縦型/ワークフロー）"

    def health(self) -> bool:
        return _module_ok() or _server_ok()

    def setup(self) -> ToolResult:
        if self.health():
            return ToolResult(ok=True)
        return ToolResult(ok=False, error=(
            "TK-CutExpress 未導入: pip install -e <TK-CutExpress> または "
            "python3 install.py（ffmpeg必須）。REST API を使うなら tkce-server --port 8787"))

    def run(self, **kwargs):
        act = str(kwargs.get("edit_action") or kwargs.get("action") or "workflow")
        if act not in ACTIONS:
            return ToolResult(ok=False, error=f"不明な編集アクション: {act}")
        inp = str(kwargs.get("input") or kwargs.get("file") or "")
        if not inp or not Path(inp).exists():
            return ToolResult(ok=False, error=f"入力動画が見つかりません: {inp}")
        out_dir = str(kwargs.get("out_dir") or "")
        payload = {"input": inp}
        if out_dir:
            payload["out_dir"] = out_dir
        for k in ("target", "model_size", "device", "keyframes", "work_dir"):
            if kwargs.get(k):
                payload[k] = kwargs[k]

        if _module_ok():
            try:
                import video_analyzer
                res = video_analyzer.action(act, payload)
                if isinstance(res, dict):
                    ok = bool(res["ok"]) if "ok" in res else not bool(res.get("error"))
                    detail = str(res.get("error") or {k: v for k, v in res.items() if k != "ok"})[:300]
                else:
                    ok = bool(res)
                    detail = str(res)[:300]
                artifacts = _collect_artifacts(out_dir)
                write_log(f"TK-CutExpress({act}): ok={ok} artifacts={len(artifacts)}")
                return ToolResult(ok=ok, data={"action": act, "detail": detail[:300]},
                                  artifacts=artifacts)
            except Exception as e:  # noqa: BLE001
                write_log(f"TK-CutExpress モジュール失敗 → REST試行: {e}", "WARN")
        # REST フォールバック
        if _server_ok():
            try:
                import json, urllib.request
                req = urllib.request.Request(
                    f"http://127.0.0.1:8787/api/{act}",
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=600) as r:
                    res = json.loads(r.read().decode("utf-8", "ignore"))
                ok = bool(res.get("ok", True))
                artifacts = _collect_artifacts(out_dir)
                return ToolResult(ok=ok, data={"action": act, "via": "rest", "detail": str(res)[:300]},
                                  artifacts=artifacts)
            except Exception as e:  # noqa: BLE001
                return ToolResult(ok=False, error=f"TK-CutExpress 実行失敗: {e}")
        return ToolResult(ok=False, error="TK-CutExpress が利用できません（モジュール/REST 両方なし）")
