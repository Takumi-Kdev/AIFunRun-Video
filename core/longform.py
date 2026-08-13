"""DeepSeekだけをAIとして使う、横型長尺作品の構成・脚本エンジン。"""
from __future__ import annotations

import json
import math
import re
from datetime import datetime, timezone

from . import llm

VISUAL_MODES = ("chapter", "kinetic", "diagram", "timeline", "list", "quote", "data", "process")


def parse_duration(instruction: str, default: int = 600) -> int:
    """日本語/英語の時分秒から8秒〜3時間へ正規化。"""
    text = instruction.lower()
    hours = re.search(r"(\d+(?:\.\d+)?)\s*(?:時間|hours?|hrs?)", text)
    minutes = re.search(r"(\d+(?:\.\d+)?)\s*(?:分|minutes?|mins?)", text)
    seconds = re.search(r"(\d+(?:\.\d+)?)\s*(?:秒|seconds?|secs?)", text)
    total = 0.0
    if hours:
        total += float(hours.group(1)) * 3600
    if minutes:
        total += float(minutes.group(1)) * 60
    if seconds:
        total += float(seconds.group(1))
    if not total:
        total = default
    return max(8, min(10_800, round(total)))


def _topic(instruction: str) -> str:
    text = re.sub(r"\d+(?:\.\d+)?\s*(?:時間|分|秒|hours?|minutes?|seconds?)", "", instruction, flags=re.I)
    text = re.sub(r"(?:横型?|横長|長尺|動画|映像|youtube|ドキュメンタリー|解説)", " ", text, flags=re.I)
    text = re.sub(r"(?:にして|として)?(?:作って|創って|制作して|作成して|紹介して)(?:ください|ほしい)?$", "", text)
    text = re.sub(r"\s*(?:を(?:\s*の)?(?:\s*で)?|の(?:\s*で)?|で)\s*$", "", text)
    return (re.sub(r"\s+", " ", text).strip(" 、。") or instruction)[:140]


def _chapter_outline(topic: str, duration: int) -> list[dict]:
    count = max(3, min(18, round(duration / 150)))
    titles = ["問い", "背景", "構造", "転換点", "実例", "深掘り", "反論", "実践", "未来", "結論"]
    chapter_duration = duration / count
    return [{
        "index": index + 1,
        "title": f"{titles[min(index, len(titles)-1)]} — {topic[:34]}",
        "purpose": "視聴者の理解を一段進める",
        "duration": round(chapter_duration, 2),
    } for index in range(count)]


def _deepseek_outline(instruction: str, topic: str, duration: int, fallback: list[dict]) -> list[dict]:
    system = (
        "あなたは長尺YouTubeの構成作家。DeepSeek以外の生成AI素材を使わず、実写素材、図解、文字、"
        "決定的CGだけで成立する構成を作る。JSONのみ: {\"chapters\":[{\"title\":...,\"purpose\":...}]}。"
        f"章数は必ず{len(fallback)}。重複せず、導入→理解→実例→反論→実践→結論の論理を持たせる。"
    )
    parsed = llm._try_json(llm.chat(system, json.dumps({"instruction": instruction, "topic": topic,
                                                         "duration_seconds": duration}, ensure_ascii=False),
                                         max_tokens=1800))
    chapters = parsed.get("chapters") if isinstance(parsed, dict) else None
    if not isinstance(chapters, list) or len(chapters) < 3:
        return fallback
    count = min(len(chapters), len(fallback))
    result = []
    for index in range(count):
        item = chapters[index] if isinstance(chapters[index], dict) else {}
        base = fallback[index]
        result.append({**base, "title": str(item.get("title") or base["title"])[:100],
                       "purpose": str(item.get("purpose") or base["purpose"])[:240]})
    return result


def _fallback_beats(topic: str, chapter: dict, count: int, duration: float) -> list[dict]:
    roles = ["chapter", "kinetic", "diagram", "timeline", "list", "quote", "process", "data"]
    per = duration / count
    beats = []
    for index in range(count):
        point = [
            f"この章では、{chapter['title']}という視点から{topic}を整理します。まず全体像を掴みましょう。",
            f"重要なのは、表面的な結果だけでなく、その結果を生み出す仕組みを見ることです。{chapter['purpose']}ための前提を確認します。",
            f"構造を分けると、原因、選択、行動、結果の四つがつながっています。一つずつ見れば複雑さは減らせます。",
            f"時間の流れで考えると、最初の小さな変化が次の判断を変え、やがて大きな差になります。ここが転換点です。",
            f"実践では、目的を一つ決め、観測できる指標を置き、小さく試し、結果から次を選ぶことが有効です。",
            f"反対の見方もあります。しかし条件を分けて考えると、対立ではなく使い分けの問題だと分かります。",
            f"ここまでを工程にすると、理解する、選ぶ、試す、測る、改善するという循環になります。",
            f"この章の要点は、{chapter['purpose']}ことです。次の章では、この理解をさらに具体的な判断へつなげます。",
        ][index % 8]
        beats.append({
            "index": index + 1, "chapter": chapter["index"], "chapter_title": chapter["title"],
            "duration": round(per, 2), "purpose": f"{chapter['purpose']} / beat {index + 1}",
            "narration": point, "on_screen_text": point.split("。")[0][:48],
            "visual_prompt": f"生成AI不使用。{topic}を{roles[index % len(roles)]}形式で図解",
            "visual_mode": roles[index % len(roles)], "camera": "deterministic 2.5D move",
            "motion": ["reveal", "track", "connect", "compare", "count", "focus"][index % 6],
            "transition": "clean cut" if index else "chapter reveal",
            "facts_required": [],
        })
    return beats


def _deepseek_beats(instruction: str, topic: str, chapter: dict, count: int) -> list[dict] | None:
    target_chars = max(90, round(chapter["duration"] * 5.2 / count))
    system = (
        "あなたは長尺日本語動画の脚本家。画像・動画生成AIは禁止。DeepSeekによる脚本と、"
        "文字・図形・表・タイムライン・手持ち素材だけで成立させる。JSONのみ: {\"beats\":[...] }。"
        f"beatsは必ず{count}件。各beatに narration,on_screen_text,visual_mode,purpose,motion,transition。"
        f"visual_modeは{','.join(VISUAL_MODES)}のみ。各narrationは約{target_chars}字で、断定的な未確認数値を作らない。"
    )
    payload = {"instruction": instruction, "topic": topic, "chapter": chapter, "beat_count": count,
               "seconds_per_beat": round(chapter["duration"] / count, 1)}
    parsed = llm._try_json(llm.chat(system, json.dumps(payload, ensure_ascii=False), max_tokens=3000))
    raw = parsed.get("beats") if isinstance(parsed, dict) else None
    if not isinstance(raw, list) or len(raw) < max(3, count // 2):
        return None
    fallback = _fallback_beats(topic, chapter, count, chapter["duration"])
    result = []
    for index in range(count):
        item = raw[index] if index < len(raw) and isinstance(raw[index], dict) else {}
        base = fallback[index]
        mode = str(item.get("visual_mode") or base["visual_mode"])
        result.append({**base,
                       "narration": str(item.get("narration") or base["narration"]),
                       "on_screen_text": str(item.get("on_screen_text") or base["on_screen_text"])[:70],
                       "visual_mode": mode if mode in VISUAL_MODES else base["visual_mode"],
                       "purpose": str(item.get("purpose") or base["purpose"]),
                       "motion": str(item.get("motion") or base["motion"]),
                       "transition": str(item.get("transition") or base["transition"])})
    return result


def create_longform_plan(instruction: str, template: dict, *, feedback: str = "") -> dict:
    """アウトライン→章ごとの脚本という複数回のDeepSeek呼出しで長尺を安定設計。"""
    duration = parse_duration(instruction, int(template.get("duration_seconds", 600)))
    topic = _topic(instruction)
    chapters = _deepseek_outline(instruction, topic, duration, _chapter_outline(topic, duration))
    shots, chapter_marks, cursor = [], [], 0.0
    for chapter in chapters:
        chapter_marks.append({"title": chapter["title"], "start": round(cursor, 3)})
        count = max(4, min(12, round(chapter["duration"] / 18)))
        beats = _deepseek_beats(instruction + (f"\n改稿: {feedback}" if feedback else ""), topic, chapter, count)
        beats = beats or _fallback_beats(topic, chapter, count, chapter["duration"])
        for beat in beats:
            beat["index"] = len(shots) + 1
            shots.append(beat)
            cursor += float(beat["duration"])
    # 浮動小数差を最後のショットへ集約する。
    if shots:
        shots[-1]["duration"] = round(float(shots[-1]["duration"]) + duration - cursor, 3)
    from .media_library import assign
    shots = assign(shots)
    now = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    return {
        "version": 2, "created_at": now, "source": "deepseek-longform" if llm._api_available() else "deterministic-longform",
        "instruction": instruction, "concept": topic, "audience": "テーマを体系的に理解したい視聴者",
        "objective": "長尺でも迷子にさせず、理解・納得・実践まで運ぶ", "platform": "YouTube",
        "format": "horizontal", "resolution": [1920, 1080], "fps": int(template.get("fps", 30)),
        "duration_seconds": duration, "style": "editorial documentary / deterministic motion design",
        "emotional_arc": ["問い", "発見", "理解", "検証", "納得", "行動"],
        "visual_bible": {"palette": ["#050816", "#23D5FF", "#8A5CFF", "#F4F7FF"],
                           "lighting": "high-contrast editorial", "composition": "16:9 information-first",
                           "continuity": "章番号、進捗線、同一色系、左上の文脈ラベルを全編で維持"},
        "audio_bible": {"voice": "system", "music": "procedural tonal bed", "pace": "chapter-aware"},
        "chapters": chapters, "chapter_marks": chapter_marks, "shots": shots,
        "metadata": llm.generate_metadata(topic, [x["narration"] for x in shots[:12]],
                                            duration_seconds=duration, format_name="長尺横動画"),
        "ai_policy": {"allowed": ["deepseek"], "forbidden": ["text-to-image", "text-to-video", "gen3d", "voice-clone"],
                      "visual_sources": ["procedural-graphics", "kinetic-type", "diagrams", "local-media", "blender-procedural"]},
        "autonomy": {"inferred": ["chapters", "retention_beats", "visual_modes", "pacing", "audio_bed", "metadata"],
                     "human_required": ["事実確認が必要な専門的主張", "外部公開の最終承認"]},
    }
