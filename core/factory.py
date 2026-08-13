"""動画創作ファクトリー（多品種・連続生産オーケストレーション）。

config/templates/*.json の「生産レシピ」を読み、config/characters.json の「キャラ
カタログ」を参照しつつ、工場のステーションを順に稼働させて動画を自律創作する。

堅牢化（フル稼働でも止まらない）:
  - 各ステーションを **タイムアウト + リトライ** 付きで実行（1工程が固まっても次へ）
  - 失敗ステーションは安全にスキップ（必ず動く原則）
  - モデレーション（投稿前安全ゲート）ステップ
  - 工場の実行コストを finance に計上（GPU/API 費用の可視化）
  - run_batch: 量産モード（連続生産）
  - 実行状態を state に記録（監査・再開）

run() は「生産報告書」を返す。
"""
from __future__ import annotations

import concurrent.futures as _cf
import json
from datetime import datetime, timezone
from pathlib import Path

from . import state
from .logger import write_log
from .paths import ensure_dirs

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = ROOT / "config" / "templates"
CHARACTERS_FILE = ROOT / "config" / "characters.json"
QUEUE_FILE = ROOT / "config" / "factory_queue.json"
DEFAULT_TEMPLATE = "short_explainer"

_TEMPLATE_KEYWORDS = {
    "news_presenter": ["ニュース", "news", "キャスター", "プレゼンター", "顔出し"],
    "ai_visual": ["幻想的", "ai感", "ミュージック", "ビジュアル", "エモ", "背景"],
}

_TEMPLATE_REQUIRED = ["id", "name", "pattern", "resolution", "fps", "steps"]
_STATION_ALLOWED = ["plan", "assets", "scene", "shot", "render", "voice", "background", "edit", "moderate", "music", "quality"]


# --------------------------------------------------------------------------- #
# 設定ヘルパー
# --------------------------------------------------------------------------- #
def _settings() -> dict:
    try:
        with (ROOT / "config" / "settings.json").open(encoding="utf-8") as f:
            return json.load(f).get("factory", {})
    except Exception:  # noqa: BLE001
        return {}


def list_templates() -> list[dict]:
    if not TEMPLATE_DIR.exists():
        return []
    out = []
    for p in sorted(TEMPLATE_DIR.glob("*.json")):
        try:
            t = json.loads(p.read_text(encoding="utf-8"))
            if validate_template(t)["ok"]:
                out.append(t)
        except Exception:  # noqa: BLE001
            continue
    return out


def load_template(template_id: str) -> dict | None:
    for t in list_templates():
        if t.get("id") == template_id:
            return t
    return None


def validate_template(t: dict) -> dict:
    """テンプレートの必須項目・許容ステーションを検証。"""
    missing = [k for k in _TEMPLATE_REQUIRED if k not in t]
    if missing:
        return {"ok": False, "errors": [f"必須項目欠落: {missing}"]}
    bad = [s for s in t.get("steps", []) if s not in _STATION_ALLOWED]
    if bad:
        return {"ok": False, "errors": [f"未知ステーション: {bad}"]}
    res = t.get("resolution", [])
    if not (isinstance(res, list) and len(res) == 2 and all(isinstance(x, int) and x > 0 for x in res)):
        return {"ok": False, "errors": ["resolution は正の整数2要素のリスト"]}
    return {"ok": True, "errors": []}


def load_characters() -> dict:
    if not CHARACTERS_FILE.exists():
        return {}
    try:
        return json.loads(CHARACTERS_FILE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _resolve_character(template: dict) -> dict | None:
    cid = template.get("character")
    if not cid:
        return None
    chars = load_characters()
    return chars.get(cid, {"name": cid})


def _detect_template(instruction: str) -> str:
    t = instruction.lower()
    for tid, keys in _TEMPLATE_KEYWORDS.items():
        if any(k in t for k in keys):
            return tid
    return DEFAULT_TEMPLATE


def _now_stamp() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y%m%d_%H%M%S")


def _reg():
    from engines import bootstrap
    return bootstrap()


def _run_guarded(fn, timeout: float, retries: int):
    """fn をスレッドで timeout 上限・retries 回リトライで実行。

    戻り値: ("ok", result) | ("timeout", None) | ("error", exception)
    1工程が固まっても全体を止めないための安定化。
    """
    last = None
    for _ in range(max(retries, 0) + 1):
        ex = _cf.ThreadPoolExecutor(max_workers=1)
        fut = ex.submit(fn)
        try:
            return ("ok", fut.result(timeout=timeout))
        except TimeoutError:  # noqa: BLE001  (builtin; hangした工程は待たず次へ)
            ex.shutdown(wait=False, cancel_futures=True)
            return ("timeout", None)
        except Exception as e:  # noqa: BLE001
            last = e
            ex.shutdown(wait=False, cancel_futures=True)
    return ("error", last)


# --------------------------------------------------------------------------- #
# ステーション実装
# --------------------------------------------------------------------------- #
def _make_ref_image(path: Path) -> str | None:
    try:
        from PIL import Image
        img = Image.new("RGB", (512, 512), (40, 80, 140))
        img.save(path)
        return str(path)
    except Exception:  # noqa: BLE001
        return None


def run(instruction: str, template: str | None = None,
        out_dir: str | None = None, label: str = "") -> dict:
    """工場を1ライン稼働し、生産報告書を返す。

    out_dir: 出力先を明示（トラック等で分離）。未指定は output/factory/<ts>_<template>。
    label:   プロジェクトIDに付与する識別子（トラックID等）。状況を追いやすくする。
    """
    ensure_dirs()
    cfg = _settings()
    timeout = float(cfg.get("timeout_seconds", 90))
    retries = int(cfg.get("retries", 1))

    template = template or _detect_template(instruction)
    tmpl = load_template(template) or load_template(DEFAULT_TEMPLATE)
    if tmpl is None:
        tmpl = {"id": DEFAULT_TEMPLATE, "name": "ショート解説", "pattern": "animation",
                "resolution": [1080, 1920], "fps": 30, "steps": ["plan", "background"]}
    template_id = tmpl.get("id", DEFAULT_TEMPLATE)
    char = _resolve_character(tmpl)

    if out_dir:
        out_dir = Path(out_dir)
    else:
        out_dir = ensure_dirs()["output"] / "factory" / f"{_now_stamp()}_{template_id}"
    out_dir.mkdir(parents=True, exist_ok=True)

    prefix = f"track_{label}_" if label else "factory_"
    pid = f"{prefix}{template_id}_{_now_stamp()}"
    title = instruction[:40]
    state.new_project(pid, title, "video", instruction)

    reg = _reg()
    report: list[dict] = []
    artifacts: list[str] = []
    script: list[str] = []
    creative_plan: dict = {}
    quality: dict = {}
    res_w, res_h = tmpl.get("resolution", [1080, 1920])
    fps = tmpl.get("fps", 30)
    steps = tmpl.get("steps", ["plan"])
    moderation_ok = True

    def _add(station, ok, detail, artifact=None, tool=None, duration=None):
        row = {"station": station, "ok": ok, "detail": detail, "tool": tool}
        if duration is not None:
            row["seconds"] = round(duration, 2)
        report.append(row)
        if artifact:
            artifacts.append(str(artifact))
        write_log(f"factory[{template_id}].{station}: {'OK' if ok else 'FAIL'} {detail}")

    def _guarded_call(fn, station):
        st, val = _run_guarded(fn, timeout, retries)
        if st == "timeout":
            _add(station, False, "タイムアウト", tool="(guard)")
            return None
        if st == "error":
            _add(station, False, f"エラー: {val}", tool="(guard)")
            return None
        return val

    # ---- 企画 / 脚本 ----
    if "plan" in steps:
        from . import creative
        plan = _guarded_call(lambda: creative.create_plan(instruction, tmpl), "plan")
        if plan is not None:
            creative_plan = plan
            creative_plan["template_id"] = template_id
            creative_plan["project_id"] = pid
            script = [str(shot.get("narration", "")) for shot in plan.get("shots", []) if shot.get("narration")]
            for artifact in creative.save_plan(plan, out_dir):
                artifacts.append(artifact)
            _add("plan", True, f"作品設計 {len(script)}ショット / {plan.get('duration_seconds')}秒", tool="creative_director")
        else:
            script = [f"【{title}】"]
            _add("plan", False, "脚本生成失敗", tool="llm")

    # ---- モデレーション（安全ゲート） ----
    if "moderate" in steps:
        mod = _guarded_call(lambda: reg.call("moderation", text="\n".join(script)), "moderate")
        if mod is not None:
            ok_mod = bool(mod.ok) or bool((mod.data or {}).get("ok"))
            moderation_ok = ok_mod
            _add("moderate", ok_mod, "安全チェックOK" if ok_mod else f"NG: {mod.error}", tool="moderation")
        else:
            _add("moderate", False, "モデレーション実行不可", tool="moderation")

    # ---- 3D資産 ----
    if "assets" in steps:
        # モデリングツール振り分けルーターで最適な手法を選択（CAD/gen3d/Blender）
        try:
            from core import model_router as _mr
            r = _mr.build_asset(title, out_dir=str(out_dir / "3d"))
            tool = r.get("tool", "gen3d")
            if r.get("ok") and r.get("artifacts"):
                for a in r["artifacts"]:
                    _add("assets", True, f"3D資産[{tool}]: {a.split('/')[-1]}", artifact=a, tool=tool)
            else:
                _add("assets", False, f"3D資産[{tool}] {r.get('detail','')}", tool=tool)
        except Exception as exc:  # noqa: BLE001
            # フォールバック: gen3d 直接（従来経路）
            ref_img = _make_ref_image(out_dir / "ref.png")
            res = _guarded_call(lambda: reg.call("gen3d", action="generate", image=ref_img or "",
                                                 topic=title, out_dir=str(out_dir / "3d")), "assets")
            if res is not None and res.ok:
                _add("assets", True, f"3D資産: {res.data.get('glb')}", tool="gen3d")
            elif res is not None:
                placeholder = res.data.get("placeholder_script") if res.data else None
                if placeholder:
                    sf = out_dir / "gen3d_placeholder.py"
                    sf.write_text(placeholder, encoding="utf-8")
                    _add("assets", False, f"3D資産フォールバック: {res.error}", artifact=sf, tool="gen3d")
                else:
                    _add("assets", False, f"3D資産なし: {res.error}", tool="gen3d")
            write_log(f"[{pid}] model_router失敗→gen3dフォールバック: {exc}", "WARN")

    # ---- シーン・照明（プロンプト→多様なBlenderシーン） ----
    if "scene" in steps:
        code, tool, detail = None, "scene", "シーン生成不可"
        try:
            from engines import scene as scene_mod
            stype = scene_mod.classify(title)
            st, val = _run_guarded(
                lambda: reg.call("scene", action="build", prompt=title, scene_type=stype,
                                 out=str(out_dir / "render.mp4"), resolution=f"{res_w},{res_h}",
                                 fps=fps, frames=120),
                timeout, retries)
            if st == "ok" and val.ok and val.data.get("code"):
                code = val.data["code"]
                detail = f"シーン生成: {val.data.get('scene_type', stype)}"
        except Exception:  # noqa: BLE001
            code = None
        if not code:
            # フォールバック: 基本シーン+照明
            def _fb_scene():
                s = reg.call("animate", action="scene_setup")
                l = reg.call("animate", action="lighting")
                return s.data.get("code", "") + "\n" + l.data.get("code", "")
            st2, val2 = _run_guarded(_fb_scene, timeout, retries)
            if st2 == "ok" and val2:
                code, tool = val2, "animate"
                detail = "シーン/照明(フォールバック)"
        if code:
            sf = out_dir / "scene.py"
            sf.write_text(code, encoding="utf-8")
            _add("scene", True, detail, artifact=sf, tool=tool)
        else:
            _add("scene", False, detail, tool=tool)

    # ---- 演出（オービット） ----
    if "shot" in steps:
        shot = _guarded_call(lambda: reg.call("animate", action="orbit_shot", target="Asset", frames=90), "shot")
        if shot is not None and shot.ok:
            sf = out_dir / "shot.py"
            sf.write_text(shot.data.get("code", ""), encoding="utf-8")
            _add("shot", True, "オービットショット", artifact=sf, tool="animate")
        else:
            _add("shot", False, f"ショット生成失敗: {shot.error if shot else 'guard'}", tool="animate")

    # ---- レンダー ----
    if "render" in steps:
        def _render():
            rv = out_dir / "render.mp4"
            return reg.call("animate", action="render", out=str(rv),
                            resolution=f"{res_w},{res_h}", fps=fps)
        r = _guarded_call(_render, "render")
        if r is not None and r.ok:
            sf = out_dir / "render.py"
            sf.write_text(r.data.get("code", ""), encoding="utf-8")
            _add("render", True, "レンダースクリプト", artifact=sf, tool="animate")
        else:
            _add("render", False, f"レンダー生成失敗: {r.error if r else 'guard'}", tool="animate")

    # ---- 音声 ----
    voice_path = None
    if "voice" in steps:
        def _voice():
            return reg.call("tts", text="\n".join(script), out=str(out_dir / "voice.wav"))
        v = _guarded_call(_voice, "voice")
        if v is not None and v.ok and v.artifacts:
            voice_path = v.artifacts[0]
            _add("voice", True, "音声合成", artifact=voice_path, tool="tts")
        else:
            _add("voice", False, f"音声なし: {v.error if v else 'guard'}", tool="tts")

    # ---- 背景 / 映像クリップ ----
    bg_video = None
    if "background" in steps:
        def _bg():
            return reg.call("video2d", action="generate", topic=title,
                            out=str(out_dir / "background.mp4"), duration=10.0, w=res_w, h=res_h)
        b = _guarded_call(_bg, "background")
        if b is not None and b.ok and b.artifacts:
            bg_video = Path(b.artifacts[0])
            _add("background", True, "背景映像生成", artifact=bg_video, tool="video2d")
        else:
            _add("background", False, f"背景なし: {b.error if b else 'guard'}", tool="video2d")

    # ---- 編集 / 作品構成 ----
    if "edit" in steps and (creative_plan or bg_video is not None):
        def _edit():
            if creative_plan:
                return reg.call("composer", action="compose", plan=creative_plan,
                                out_dir=str(out_dir), voice=voice_path)
            eo = ensure_dirs()["output"] / "factory" / f"{_now_stamp()}_{template_id}_edit"
            return reg.call("video_edit", edit_action="workflow", input=str(bg_video), out_dir=str(eo))
        e = _guarded_call(_edit, "edit")
        if e is not None and e.ok:
            for a in e.artifacts:
                artifacts.append(a)
            quality = (e.data or {}).get("quality", {}) if isinstance(e.data, dict) else {}
            _add("edit", True, "ショット・字幕・音声・BGMを一本の作品へ統合", tool="composer" if creative_plan else "video_edit")
        else:
            _add("edit", False, f"編集不可: {e.error if e else 'guard'}", tool="composer" if creative_plan else "video_edit")

    # ---- BGM 合成（Blenderで作れない音楽を付与） ----
    if "music" in steps:
        cand = [a for a in artifacts if a.endswith(".mp4")]
        composed = next((a for a in reversed(cand) if Path(a).name == "final.mp4"), None)
        if composed:
            _add("music", True, "作品構成工程で音響設計・BGMを統合済み", artifact=composed, tool="composer")
        elif cand:
            base = cand[-1]
            bgm = out_dir / "bgm.mp3"
            final = out_dir / "final_with_bgm.mp4"
            mood = "upbeat" if template_id in ("short_explainer",) else "epic"
            try:
                st_m, _ = _run_guarded(
                    lambda: reg.call("music", action="generate", mood=mood, out=str(bgm)), timeout, retries)
                st_b, val_b = _run_guarded(
                    lambda: reg.call("music", action="add_bgm", video=base, music=str(bgm),
                                     out=str(final), volume=0.35), timeout, retries)
                if st_b == "ok" and val_b.ok and final.exists():
                    artifacts.append(str(final))
                    _add("music", True, "BGM合成", artifact=final, tool="music")
                else:
                    _add("music", False, "BGM合成不可", tool="music")
            except Exception as exc:  # noqa: BLE001
                _add("music", False, f"BGM失敗: {exc}", tool="music")

    # ---- 品質監督 ----
    if "quality" in steps:
        final_video = next((Path(a) for a in reversed(artifacts) if str(a).endswith(".mp4") and Path(a).exists()), None)
        if final_video:
            try:
                from engines.composer import inspect_video
                quality = inspect_video(final_video, expected=(res_w, res_h),
                                        target_duration=float(creative_plan.get("duration_seconds", 0) or 0))
                qf = out_dir / "quality_report.json"
                qf.write_text(json.dumps(quality, ensure_ascii=False, indent=2), encoding="utf-8")
                _add("quality", bool(quality.get("playable")) and quality.get("score", 0) >= 80,
                     f"品質スコア {quality.get('score', 0)}/100", artifact=qf, tool="ffprobe")
            except Exception as exc:  # noqa: BLE001
                _add("quality", False, f"品質解析失敗: {exc}", tool="ffprobe")
        else:
            _add("quality", False, "再生可能な動画成果物がありません", tool="ffprobe")

    # ---- script 保存 ----
    script_file = out_dir / "script.txt"
    script_file.write_text("\n".join(script), encoding="utf-8")
    artifacts.append(str(script_file))

    playable = bool(quality.get("playable")) if "quality" in steps else any(str(a).endswith(".mp4") for a in artifacts)
    ok = playable or len(artifacts) > 0
    status = ("needs_review" if playable and (not moderation_ok or quality.get("score", 100) < 80)
              else ("created" if playable else "draft"))

    # 状態記録（監査・再開用）
    st = state.load()
    if pid in st.get("projects", {}):
        st["projects"][pid]["status"] = status
        st["projects"][pid]["artifacts"] = artifacts
        st["projects"][pid]["steps"] = [r["station"] for r in report]
        st["projects"][pid]["template"] = template_id
        st["projects"][pid]["pattern"] = tmpl.get("pattern")
        st["projects"][pid]["character"] = (char or {}).get("name")
        st["projects"][pid]["updated_at"] = state._now_iso()
        state.record_event(st, "project.upsert", st["projects"][pid])

    # コスト計上（GPU/API 費用の可視化）
    if cfg.get("record_cost", True):
        try:
            from . import finance
            finance.record("expense", float(cfg.get("cost_per_run", 0.5)), "factory",
                           f"工場生産: {template_id} [{title}]")
        except Exception as e:  # noqa: BLE001
            write_log(f"factory コスト計上失敗: {e}", "WARN")

    return {
        "ok": ok,
        "status": status,
        "artifacts": artifacts,
        "detail": f"工場稼働: {tmpl.get('name')} / {len(report)}ステーション",
        "template": template_id,
        "pattern": tmpl.get("pattern"),
        "character": (char or {}).get("name"),
        "script": script,
        "creative_plan": creative_plan,
        "quality": quality,
        "production_ready": playable and moderation_ok and quality.get("score", 100) >= 80,
        "steps": report,
        "project_id": pid,
    }


def run_batch(count: int, instruction: str, template: str | None = None) -> dict:
    """量産モード: 指定件数の動画を連続生産し、各生産報告をまとめて返す。"""
    n = max(int(count), 1)
    reports = [run(instruction, template) for _ in range(n)]
    ok_count = sum(1 for r in reports if r.get("ok"))
    return {
        "ok": ok_count > 0,
        "count": n,
        "succeeded": ok_count,
        "failed": n - ok_count,
        "reports": [{"template": r.get("template"), "status": r.get("status"),
                     "artifacts": r.get("artifacts"), "steps": len(r.get("steps", []))} for r in reports],
    }


def run_pending(limit: int = 10) -> dict:
    """永続キューの未処理作品だけを創作する（daemon用、再起動しても重複しない）。"""
    done_file = ensure_dirs()["state"] / "factory_done.json"
    try:
        queue = json.loads(QUEUE_FILE.read_text(encoding="utf-8")) if QUEUE_FILE.exists() else []
    except (OSError, ValueError):
        queue = []
    try:
        done = json.loads(done_file.read_text(encoding="utf-8")) if done_file.exists() else {}
    except (OSError, ValueError):
        done = {}
    reports = []
    for item in [x for x in queue if str(x.get("id", "")) not in done][:max(1, int(limit))]:
        item_id = str(item.get("id") or f"queue_{len(done) + 1}")
        result = run(str(item.get("instruction", "")), str(item.get("template") or "") or None, label="queue")
        done[item_id] = {"status": result.get("status"), "project_id": result.get("project_id"), "at": state._now_iso()}
        reports.append({"id": item_id, "ok": result.get("ok"), "status": result.get("status"),
                        "project_id": result.get("project_id")})
        done_file.write_text(json.dumps(done, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "processed": len(reports), "succeeded": sum(bool(x["ok"]) for x in reports), "reports": reports}


def status() -> dict:
    """最近の工場生産の概要（state の factory_* プロジェクトから）。"""
    st = state.load()
    projects = st.get("projects", {})
    fp = {k: v for k, v in projects.items() if k.startswith("factory_")}
    statuses: dict[str, int] = {}
    templates: dict[str, int] = {}
    for v in fp.values():
        statuses[v.get("status", "?")] = statuses.get(v.get("status", "?"), 0) + 1
        t = v.get("template", "?")
        templates[t] = templates.get(t, 0) + 1
    recent = sorted(fp.items(), key=lambda kv: kv[1].get("updated_at", ""), reverse=True)[:10]
    return {
        "total_runs": len(fp),
        "by_status": statuses,
        "by_template": templates,
        "recent": [{"id": k, "status": v.get("status"), "template": v.get("template"),
                    "artifacts": len(v.get("artifacts", []))} for k, v in recent],
    }


def action(name: str, args: dict) -> dict:
    """システムIF（core/systems から呼ばれる）。"""
    if name == "run":
        return {"ok": True, "data": run(str(args.get("instruction", "")), str(args.get("template") or None) or None)}
    if name == "batch":
        return {"ok": True, "data": run_batch(int(args.get("count", 1)), str(args.get("instruction", "")),
                                              str(args.get("template") or None) or None)}
    if name == "list":
        return {"ok": True, "data": list_templates()}
    if name == "status":
        return {"ok": True, "data": status()}
    if name == "run_pending":
        return {"ok": True, "data": run_pending(int(args.get("limit", 10)))}
    if name == "characters":
        return {"ok": True, "data": load_characters()}
    if name == "validate":
        t = args.get("template")
        if isinstance(t, dict):
            return {"ok": True, "data": validate_template(t)}
        tpl = load_template(str(t)) if isinstance(t, str) else None
        return {"ok": True, "data": validate_template(tpl) if tpl else {"ok": False, "errors": ["template無し"]}}
    return {"ok": False, "error": f"factory.action 不明: {name}"}
