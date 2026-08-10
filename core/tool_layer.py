"""Tool Layer: 全外部ツールの共通抽象化 + レジストリ。

AIProductionOS-riot の「外部ツールは必ず Tool Layer 経由」規律を Python に移植。
ツール（ffmpeg / TTS / YouTube API / Blender / Brave 等）はこの層に登録し、
call() / health() / setup() で統一呼び出し。差し替え・フォールバック・診断が容易になる。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolResult:
    ok: bool
    data: Any = None
    error: str = ""
    artifacts: list[str] = field(default_factory=list)


class Tool(ABC):
    """ツールアダプタの基底。"""

    name: str = ""
    description: str = ""

    @abstractmethod
    def health(self) -> bool:
        """このツールが今使えるか（バイナリ/認証など）。"""

    def setup(self) -> ToolResult:
        """必要なものを準備（DL/設定）。デフォルトは何もしない。"""
        return ToolResult(ok=True)

    @abstractmethod
    def run(self, **kwargs: Any) -> ToolResult:
        """ツールを実行する。"""


class ToolRegistry:
    """ツールの登録・照会・実行を一元管理。"""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> Tool:
        if not tool.name:
            raise ValueError(f"{type(tool).__name__} に name がありません")
        self._tools[tool.name] = tool
        return tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return sorted(self._tools)

    def call(self, name: str, **kwargs: Any) -> ToolResult:
        tool = self.get(name)
        if tool is None:
            return ToolResult(ok=False, error=f"未登録ツール: {name}")
        if not tool.health():
            prepared = tool.setup()
            if not prepared.ok:
                return ToolResult(ok=False, error=f"ツール準備失敗 [{name}]: {prepared.error}")
        try:
            return tool.run(**kwargs)
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=f"[{name}] {e}")

    def health_report(self) -> dict[str, bool]:
        return {n: t.health() for n, t in self._tools.items()}


# プロセス全体で共有するデフォルトレジストリ
_registry: ToolRegistry | None = None


def get_registry() -> ToolRegistry:
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
    return _registry
