"""意図から動画作品の設計図を作る AI クリエイティブ・ディレクター。

利用者が決めるのは原則「作りたい動画」だけ。尺、構成、フック、視覚言語、
音響、CTA、ショット割りはこの層が補完し、全エンジンが共有するCreativePlanへ落とす。
"""
from __future__ import annotations

import json
import re
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from . import llm


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _duration(text: str, template: dict) -> int:
    if template.get("id") == "longform_documentary" or any(k in text.lower() for k in ("長尺", "長編", "long-form", "longform")):
        from .longform import parse_duration
        return parse_duration(text, int(template.get("duration_seconds", 600)))
    match = re.search(r"(\d{1,3})\s*秒", text)
    if match:
        return max(8, min(180, int(match.group(1))))
    if template.get("resolution", [1080, 1920])[0] > template.get("resolution", [1080, 1920])[1]:
        return 45
    return 24


def _platform(text: str, vertical: bool) -> str:
    lowered = text.lower()
    if "tiktok" in lowered or "ティックトック" in lowered:
        return "TikTok"
    if "instagram" in lowered or "リール" in lowered:
        return "Instagram Reels"
    if "youtube" in lowered:
        return "YouTube Shorts" if vertical else "YouTube"
    return "Short-form SNS" if vertical else "YouTube"


def _topic(text: str) -> str:
    cleaned = re.sub(r"(?:動画|ショート|映像)を?(?:作って|創って|制作して|生成して)", "", text)
    cleaned = re.sub(r"\d+\s*秒(?:程度|前後)?の?", "", cleaned)
    cleaned = re.sub(r"(?:縦型|横型|スクエア)(?:ショート|動画)?", "", cleaned)
    cleaned = re.sub(r"(?:を|について)?(?:紹介|解説)(?:します|する)?$", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" 、。『』\"'")
    return (cleaned or text.strip() or "伝えたいテーマ")[:120]


def _fallback_plan(instruction: str, template: dict) -> dict:
    topic = _topic(instruction)
    width, height = template.get("resolution", [1080, 1920])
    vertical = height >= width
    duration = _duration(instruction, template)
    shot_count = max(4, min(8, round(duration / 4)))
    beat_duration = round(duration / shot_count, 2)
    narratives = [
        f"今回は「{topic}」を{int(duration)}秒で解説します。",
        "結論から言うと、大切なのは小さく始めることです。",
        "1つ目、目的を1行に絞ります。",
        "2つ目、毎日1つだけ実行します。",
        "3つ目、数字を見て改善を繰り返します。",
        f"この3ステップで「{topic}」は確実に前に進みます。",
        "詳しい手順は次回の動画で解説します。",
        "フォローして次の動画をお待ちください。",
    ]
    purposes = ["pattern_interrupt", "promise", "context", "proof", "turn", "payoff", "cta", "afterglow"]
    cameras = ["macro push-in", "slow orbit", "parallax drift", "top-down reveal", "dolly through", "locked hero", "pull-back", "fade to symbol"]
    motions = ["pulse", "orbit", "rise", "split", "flow", "focus", "converge", "breathe"]
    shots = []
    for index in range(shot_count):
        narration = narratives[index]
        shots.append({
            "index": index + 1,
            "duration": beat_duration if index < shot_count - 1 else round(duration - beat_duration * (shot_count - 1), 2),
            "purpose": purposes[index],
            "narration": narration,
            "on_screen_text": narration.replace("。", "")[:34],
            "visual_prompt": f"{topic}、{template.get('pattern', 'cinematic')}、象徴的で一貫した世界、shot {index + 1}",
            "camera": cameras[index],
            "motion": motions[index],
            "transition": "hard cut" if index < 2 else ("match dissolve" if index < shot_count - 1 else "fade out"),
        })
    return {
        "version": 1,
        "created_at": _now(),
        "source": "autonomous-fallback",
        "instruction": instruction,
        "concept": topic,
        "audience": "このテーマに関心はあるが、まだ行動していない視聴者",
        "objective": "冒頭2秒で注意を止め、価値を一つ伝え、次の行動へ導く",
        "platform": _platform(instruction, vertical),
        "format": "vertical" if vertical else "horizontal",
        "resolution": [width, height],
        "fps": int(template.get("fps", 30)),
        "duration_seconds": duration,
        "style": template.get("name", "cinematic editorial"),
        "emotional_arc": ["違和感", "好奇心", "理解", "高揚", "決意"],
        "visual_bible": {
            "palette": ["#050816", "#23D5FF", "#8A5CFF", "#F4F7FF"],
            "lighting": "deep contrast, cyan-violet motivated light",
            "composition": "large focal subject, generous negative space, editorial typography",
            "continuity": f"全ショットに『{topic[:24]}』を象徴する同一の光源と軌道モチーフを残す",
        },
        "audio_bible": {"voice": template.get("voice", "auto"), "music": "cinematic pulse", "pace": "fast-open, calm-middle, decisive-close"},
        "shots": shots,
        "metadata": llm.generate_metadata(topic, [x["narration"] for x in shots]),
        "autonomy": {
            "inferred": ["platform", "duration", "audience", "shot_count", "visual_language", "music", "cta"],
            "human_required": ["外部公開の最終承認のみ"],
        },
    }


def _normalize(candidate: dict, fallback: dict) -> dict:
    plan = deepcopy(fallback)
    for key in ("concept", "audience", "objective", "style", "emotional_arc", "visual_bible", "audio_bible", "metadata"):
        if candidate.get(key):
            plan[key] = candidate[key]
    shots = candidate.get("shots")
    if isinstance(shots, list) and 3 <= len(shots) <= 12:
        normalized = []
        default_duration = plan["duration_seconds"] / len(shots)
        for index, shot in enumerate(shots):
            if not isinstance(shot, dict):
                continue
            base = fallback["shots"][min(index, len(fallback["shots"]) - 1)]
            normalized.append({key: shot.get(key, base.get(key)) for key in (
                "index", "duration", "purpose", "narration", "on_screen_text",
                "visual_prompt", "camera", "motion", "transition"
            )})
            normalized[-1]["index"] = index + 1
            normalized[-1]["duration"] = max(1.0, float(normalized[-1].get("duration") or default_duration))
        if len(normalized) >= 3:
            total = sum(x["duration"] for x in normalized) or 1
            scale = plan["duration_seconds"] / total
            for shot in normalized:
                shot["duration"] = round(shot["duration"] * scale, 2)
            plan["shots"] = normalized
    plan["source"] = "deepseek-director"
    return plan


def create_plan(instruction: str, template: dict, *, feedback: str = "") -> dict:
    """一行の意図から、制作可能な動画設計図を作る。API無しでも完結する。"""
    if template.get("id") == "longform_documentary" or template.get("format") == "longform":
        from .longform import create_longform_plan
        return create_longform_plan(instruction, template, feedback=feedback)
    fallback = _fallback_plan(instruction, template)
    system = (
        "あなたは映像作家、SNSストラテジスト、編集監督を兼ねる。入力から完成映像を設計する。"
        "不足条件は質問せず合理的に補完し、人間の作業を最小化する。抽象語だけでなく撮影可能なショットにする。"
        "JSONのみ。必須キー: concept,audience,objective,style,emotional_arc,visual_bible,audio_bible,shots,metadata。"
        "shotsは3〜12件で各要素に duration,purpose,narration,on_screen_text,visual_prompt,camera,motion,transition。"
    )
    user = json.dumps({
        "instruction": instruction,
        "feedback": feedback,
        "fixed": {key: fallback[key] for key in ("platform", "format", "resolution", "fps", "duration_seconds")},
        "template": template,
    }, ensure_ascii=False)
    parsed = llm._try_json(llm.chat(system, user, max_tokens=1200, no_cache=bool(feedback)))
    return _normalize(parsed, fallback) if isinstance(parsed, dict) else fallback


def revise_plan(plan: dict, feedback: str) -> dict:
    """自然言語の追加指示から同じ作品設計を改稿する。"""
    template = {
        "name": plan.get("style", "cinematic"), "pattern": "revision",
        "resolution": plan.get("resolution", [1080, 1920]), "fps": plan.get("fps", 30),
        "voice": (plan.get("audio_bible") or {}).get("voice", "auto"),
    }
    instruction = f"{plan.get('instruction', plan.get('concept', ''))}\n改稿指示: {feedback}"
    revised = create_plan(instruction, template, feedback=feedback)
    revised["revision_of"] = plan.get("project_id") or plan.get("created_at")
    return revised


def save_plan(plan: dict, out_dir: Path) -> list[str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "creative_plan.json"
    md_path = out_dir / "storyboard.md"
    json_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    rows = [
        f"# {plan.get('concept', 'Creative Plan')}", "",
        f"- 目的: {plan.get('objective', '')}", f"- 視聴者: {plan.get('audience', '')}",
        f"- 配信先: {plan.get('platform', '')}", f"- 尺: {plan.get('duration_seconds', 0)}秒", "", "## Storyboard", "",
    ]
    for shot in plan.get("shots", []):
        rows += [f"### {shot.get('index')}. {shot.get('purpose')}",
                 f"- Voice: {shot.get('narration')}", f"- Visual: {shot.get('visual_prompt')}",
                 f"- Camera/Motion: {shot.get('camera')} / {shot.get('motion')}", ""]
    md_path.write_text("\n".join(rows), encoding="utf-8")
    return [str(json_path), str(md_path)]
