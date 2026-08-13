"""LLM 層。DeepSeek（推奨）とルールベースのフォールバック。

DeepSeek キー未設定でも必ず動く（フォールバック）。SNSmarketVideo-CR-OSS の
rule-based fallback の良部品を参考にした「常に壊れない」設計。

コスト最適化:
- 結果キャッシュ（同プロンプトを再呼び出ししない）
- 月間予算ガード（cost.llm_monthly_budget 円を超えたら節約モード）
- プロンプト長の上限（トークン節約）
- コスト統計（呼び出し数/キャッシュヒット/推定費用）
"""
from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path

from .credentials import get
from .logger import write_log

_CACHE_MAX = 500
_stats = {"calls": 0, "cache_hits": 0, "skipped_budget": 0, "cost_est": 0.0}


def _cache_file() -> Path:
    from .paths import ensure_dirs
    return ensure_dirs()["state"] / "llm_cache.json"


def _load_cache() -> dict:
    p = _cache_file()
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return {}
    return {}


def _save_cache(cache: dict) -> None:
    if len(cache) > _CACHE_MAX:
        cache = dict(list(cache.items())[-_CACHE_MAX:])
    try:
        _cache_file().write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


def _cache_key(system: str, user: str, max_tokens: int) -> str:
    raw = f"deepseek-chat|{max_tokens}|{system}|{user}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _budget_exceeded() -> bool:
    """cost.llm_monthly_budget（円）を超えていればTrue（節約モード）。"""
    try:
        from .paths import load_settings
        from . import finance
        budget = float(load_settings().get("cost", {}).get("llm_monthly_budget", 0) or 0)
        if budget <= 0:
            return False
        from datetime import datetime, timezone
        month = datetime.now(timezone.utc).astimezone().strftime("%Y-%m")
        spent = sum(e["amount"] for e in finance._load_entries()
                    if e["type"] == "expense" and e["category"] == "api" and e["ts"][:7] == month)
        return spent >= budget
    except Exception:  # noqa: BLE001
        return False


def stats() -> dict:
    return dict(_stats)


def _api_available() -> bool:
    key = get("DEEPSEEK_API_KEY")
    base = get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    return bool(key) and bool(base)


def chat(system: str, user: str, max_tokens: int = 500, no_cache: bool = False) -> str | None:
    """DeepSeek へチャット。失敗・未設定なら None を返す（呼び出し側でフォールバック）。

    - 同プロンプトはキャッシュから返す（費用ゼロ）
    - 月間予算超過時は None（フォールバック利用）
    """
    key = get("DEEPSEEK_API_KEY")
    base = get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    if not key:
        return None
    if _budget_exceeded():
        _stats["skipped_budget"] += 1
        write_log("LLM月間予算超過 → ルールフォールバック使用（節約）", "WARN")
        return None

    _stats["calls"] += 1
    cache_key = _cache_key(system, user, max_tokens) if not no_cache else ""
    if cache_key:
        cache = _load_cache()
        if cache_key in cache:
            _stats["cache_hits"] += 1
            return cache[cache_key]

    # トークン節約: プロンプト長の上限（重要文脈は保つ）
    system = system[:4000] if system else system
    user = (user or "")[:3000]

    import requests

    try:
        r = requests.post(
            f"{base}/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "max_tokens": min(max_tokens, 3000),
                "temperature": 0.7,
            },
            timeout=60,
        )
        r.raise_for_status()
        data = r.json()
        content = data["choices"][0]["message"]["content"]
        _record_cost(data, min(max_tokens, 3000))
        if cache_key:
            cache = _load_cache()
            cache[cache_key] = content
            _save_cache(cache)
        return content
    except Exception as e:  # noqa: BLE001
        write_log(f"LLM呼び出し失敗 → フォールバック使用: {e}", "WARN")
        return None


def _record_cost(data: dict, max_tokens: int) -> None:
    """API 使用量を財務台帳へ自動記録（費用は見積もり）。"""
    try:
        usage = data.get("usage") or {}
        in_t = int(usage.get("prompt_tokens", 0) or 0)
        out_t = int(usage.get("completion_tokens", 0) or 0)
        if not in_t and not out_t:
            in_t = 600
            out_t = max_tokens
        # DeepSeek-chat 概算単価（円/Mトークン）
        cost = in_t * 0.00000037 + out_t * 0.00000148
        _stats["cost_est"] += cost
        if cost >= 0.001:
            from . import finance
            finance.record("expense", round(cost, 4), "api",
                           note=f"DeepSeek({in_t}in/{out_t}out)")
    except Exception:  # noqa: BLE001
        pass


def _try_json(text: str) -> dict | None:
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:  # noqa: BLE001
        # ```json ... ``` や余計な前後を除去
        start, end = text.find("{"), text.rfind("}")
        if 0 <= start < end:
            try:
                return json.loads(text[start : end + 1])
            except Exception:  # noqa: BLE001
                return None
    return None


def generate_script(topic: str, style: str = "ショート動画向け", lines: int = 5) -> list[str]:
    """トピックからテロップ/ナレーション用の脚本を生成。"""
    system = (
        "あなたはSNSマーケティングの動画脚本ライター。"
        "短文でテンポよく、視聴者を惹きつける日本語のセリフを考えてください。"
        "JSONのみで返してください: {\"script\": [\"行1\", \"行2\", ...]}"
    )
    user = f"トピック: {topic}\nスタイル: {style}\n行数: {lines}行程度"
    parsed = _try_json(chat(system, user))
    if parsed and isinstance(parsed.get("script"), list):
        return [str(s) for s in parsed["script"]][:lines]
    return _fallback_script(topic, lines)


def _fallback_script(topic: str, lines: int) -> list[str]:
    lead = random.choice(
        ["意外と知らない？", "これ知ってますか？", "いま話題です", "実はコレが重要"]
    )
    base = [f"【{topic}】", f"{lead}", "詳しく知りたい方は", "概要欄をチェック！", "フォローもよろしく"]
    base = [f"{lead}", f"「{topic}」って知ってますか？", "今日のポイントは3つ。", "最後まで見てくださいね！", "それではまた！"]
    return base[:lines]


def generate_article(topic: str) -> dict:
    """ブログ記事を生成。{'title','excerpt','sections':[{'h','p'}],'tags'}。

    DeepSeek キー無しでもテンプレートで必ず返す。
    """
    system = (
        "あなたはSEOに強い日本語ブログライター。トピックから読者に役立つ記事を作ってください。"
        'JSONのみで返してください: {"title": "...", "excerpt": "...", "sections": [{"h": "...", "p": "..."}], "tags": ["..."]}'
    )
    user = f"トピック: {topic}\nセクション数: 3〜4"
    parsed = _try_json(chat(system, user, max_tokens=800))
    if parsed and parsed.get("title") and isinstance(parsed.get("sections"), list):
        return parsed
    return {
        "title": f"{topic}｜実践ガイド",
        "excerpt": f"{topic} について、実践に役立つポイントをまとめました。",
        "sections": [
            {"h": f"{topic} とは", "p": f"{topic} の基本的な考え方と、はじめ方について解説します。"},
            {"h": "重要なポイント", "p": "小さく始めて、まず動くものを作ることが大切です。理想を追いすぎず成果を出しましょう。"},
            {"h": "次のアクション", "p": "今日からできる小さな一歩を決め、AIを使いながら継続的に改善していきます。"},
        ],
        "tags": [topic[:12], "AI", "実践"],
    }


def generate_metadata(topic: str, script: list[str], *, duration_seconds: int | None = None,
                      format_name: str | None = None) -> dict:
    """投稿用のタイトル・概要・ハッシュタグを生成。"""
    system = (
        "SNS投稿マネージャー。動画のタイトル、概要、ハッシュタグをJSONで返してください: "
        "{\"title\": \"...\", \"description\": \"...\", \"hashtags\": [\"#\", ...]}"
    )
    context = f"\n形式: {format_name}\n尺: {duration_seconds}秒" if duration_seconds else ""
    user = f"トピック: {topic}{context}\n脚本: {script}"
    parsed = _try_json(chat(system, user))
    if parsed and parsed.get("title"):
        tags = [t if t.startswith("#") else f"#{t}" for t in parsed.get("hashtags", [])[:8]]
        return {
            "title": str(parsed["title"]),
            "description": str(parsed.get("description", topic)),
            "hashtags": tags,
        }
    words = [w for w in topic.replace("#", " ").split() if w][:3] or ["AI"]
    longform = bool(duration_seconds and duration_seconds >= 240)
    tags = [f"#{w}" for w in words] + (["#長尺動画", "#YouTube"] if longform else ["#ショート動画", "#マーケティング"])
    duration_label = f"{round(duration_seconds / 60)}分で深掘り" if longform else "30秒でわかる"
    return {
        "title": f"{topic}｜{duration_label}",
        "description": f"{topic} を{'章立てで体系的に' if longform else 'コンパクトに'}解説します。{' '.join(tags)}",
        "hashtags": tags,
    }
