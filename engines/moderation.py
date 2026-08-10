"""モデレーション: 投稿前の安全チェック（日本語/英語NG語・パターン）。

SNSmarketVideo-CR-OSS の moderation をクロスプラットフォームに整理し、
Tool Layer アダプタとして登録する。投稿前に必ず通すことでアカウントBANを防ぐ。
"""
from __future__ import annotations

import re

from core.tool_layer import Tool, ToolResult

NG_WORDS_JP = [
    "www", "掲示板誹謗", "中傷", "爆破", "自殺", "裏技で稼ぐ", "確実に儲かる", "即金",
    "無料で稼げる", "誰でもできる簡単副業", "絶対勝てる", "FX必勝",
]
NG_WORDS_EN = [
    "scam", "get rich quick", "guaranteed profit", "killing", "suicide",
    "bomb", "sexual", "porn", "hate", "spam", "fake news",
]
NG_PATTERNS = [
    r"\b\d+%? off\b",        # 過剰な割引
    r"特典.*期間限定",        # 過激な急かし
    r"免責なし|リスク無し",
]


def check_text(text: str) -> dict:
    """与えられた文を検査。{'ok': bool, 'hits': [理由]} を返す。"""
    t = text.lower()
    t_nospace = re.sub(r"\s+", "", t)
    hits: list[str] = []
    for w in NG_WORDS_JP:
        if w in t_nospace or w in t:
            hits.append(f"NG語(JP): {w}")
    for w in NG_WORDS_EN:
        if w in t_nospace:
            hits.append(f"NG語(EN): {w}")
    for p in NG_PATTERNS:
        if re.search(p, t):
            hits.append(f"NGパターン: {p}")
    return {"ok": len(hits) == 0, "hits": hits}


class ModerationTool(Tool):
    name = "moderation"
    description = "投稿前の安全・モデレーションチェック"

    def health(self) -> bool:
        return True

    def run(self, **kwargs):
        text = kwargs.get("text", "")
        check = check_text(text)
        if check["ok"]:
            return ToolResult(ok=True, data={"ok": True}, artifacts=[], error="")
        return ToolResult(
            ok=False,
            data={"ok": False, "hits": check["hits"]},
            error="モデレーションNG: " + "、".join(check["hits"][:5]),
        )
