#!/usr/bin/env python3
"""AIFunRun-Video — 動画をゼロから創作するスタンドアロンCLI。

使い方:
  python run.py factory "指示文" [--template テンプレ] [--count N]
  python run.py studio <トラックID> "指示文" [--count N]
  python run.py tracks                 # トラック/アカウント/路線一覧
  python run.py studio-status          # スタジオ全トラック状況
  python run.py check                  # セットアップ検証
  python run.py daemon [--interval 60] # 自律連続生産ループ
  python run.py media-edit --input X --out Y [--format vertical] [--text '...']
  python run.py composite --base B --overlay O --out Z
  python run.py slideshow --images a.png b.png --out S.mp4
  python run.py mcp                       # MCPサーバー起動（opencode等から接続）
  python run.py music --mood calm --out bgm.mp3 [--video X]   # BGM生成/動画へ合成
  python run.py image --prompt '...' --out img.png            # テキスト→画像
  python run.py thumbnail --video X --out t.jpg               # 動画からサムネ
  python run.py transcribe --media X --out s.srt              # 音声→字幕
  python run.py model '歯車の3Dモデルを作って'                # 最適モデリング手法を選択し3D生成
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def _factory(instruction: str, template: str | None, count: int) -> dict:
    from core import factory
    if count > 1:
        return factory.run_batch(count, instruction, template)
    return factory.run(instruction, template)


def _studio_status() -> dict:
    from core import studio
    return studio.studio_status()


def _studio_run(track: str, instruction: str, count: int) -> dict:
    from core import studio
    return studio.run_track(track, instruction, count)


def _tracks() -> dict:
    from core import studio
    return {"tracks": studio.list_tracks(), "accounts": studio.list_accounts(), "lines": studio.list_lines()}


def _check() -> int:
    import importlib, pkgutil, shutil
    errs = []
    mods = []
    for pkg in (__import__("core"), __import__("engines")):
        for m in pkgutil.walk_packages(pkg.__path__, pkg.__name__ + "."):
            mods.append(m.name)
    for m in mods:
        try:
            importlib.import_module(m)
        except Exception as e:  # noqa: BLE001
            errs.append(f"{m}: {type(e).__name__} {e}")
    print("モジュール import:", "NG" if errs else "OK", f"({len(mods)}個)")
    for e in errs:
        print("  -", e)
    print("ffmpeg:", "あり" if shutil.which("ffmpeg") else "なし（動画生成に必須）")
    from core import factory, studio
    print(f"テンプレート: {len(factory.list_templates())}種 / トラック: {len(studio.list_tracks())}")
    return 1 if errs else 0


def _daemon(interval: int) -> None:
    from core import studio, factory
    print(f"自律生産ループ開始（interval={interval}s, Ctrl+Cで停止）")
    while True:
        try:
            r = studio.run_pending()
            if r.get("produced", 0):
                print(f"スタジオ自動生産: {r['produced']}件")
            cfg = factory._settings()
            if cfg.get("production_enabled"):
                from core import factory as f
                f.action("run_pending", {})  # factory キュー（config/factory_queue.json）
        except KeyboardInterrupt:
            print("停止")
            break
        except Exception as e:  # noqa: BLE001
            print(f"ループ異常（継続）: {e}")
        time.sleep(interval)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="AIFunRun-Video 動画創作CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    pf = sub.add_parser("factory", help="工場で動画生成")
    pf.add_argument("instruction")
    pf.add_argument("--template")
    pf.add_argument("--count", type=int, default=1)

    ps = sub.add_parser("studio", help="トラック指定で動画生成")
    ps.add_argument("track")
    ps.add_argument("instruction")
    ps.add_argument("--count", type=int, default=1)

    sub.add_parser("tracks", help="トラック一覧")
    sub.add_parser("studio-status", help="スタジオ状況")
    sub.add_parser("check", help="セットアップ検証")

    psc = sub.add_parser("scene", help="プロンプトからBlenderシーンを生成")
    psc.add_argument("prompt")
    psc.add_argument("--type", help="シーンタイプ（abstract_3d/low_poly_world/product_showcase/tech_abstract）")
    psc.add_argument("--out", default="output/render.mp4")

    pd = sub.add_parser("daemon", help="自律生産ループ")
    pd.add_argument("--interval", type=int, default=60)

    sub.add_parser("mcp", help="MCPサーバー起動（opencode等から操作）")

    pe = sub.add_parser("media-edit", help="FFmpegで画像/動画編集")
    pe.add_argument("--input", required=True)
    pe.add_argument("--out", required=True)
    pe.add_argument("--format", help="vertical/horizontal/square")
    pe.add_argument("--speed", type=float, default=1.0)
    pe.add_argument("--text", help="焼き込みテキスト")
    pe.add_argument("--audio")

    pc = sub.add_parser("composite", help="ベース映像にBlenderオーバーレイを合成")
    pc.add_argument("--base", required=True)
    pc.add_argument("--overlay", required=True)
    pc.add_argument("--out", required=True)

    ps2 = sub.add_parser("slideshow", help="画像→スライドショー動画")
    ps2.add_argument("--images", required=True, help="カンマ区切り画像パス")
    ps2.add_argument("--out", required=True)
    ps2.add_argument("--format", default="vertical")

    pm = sub.add_parser("music", help="BGM生成/動画へ合成")
    pm.add_argument("--mood", default="calm")
    pm.add_argument("--out", default="output/bgm.mp3")
    pm.add_argument("--video", help="指定するとこの動画にBGMを合成")

    pi = sub.add_parser("image", help="テキスト→2D画像")
    pi.add_argument("--prompt", required=True)
    pi.add_argument("--out", default="output/image.png")

    pth = sub.add_parser("thumbnail", help="動画からサムネイル抽出")
    pth.add_argument("--video", required=True)
    pth.add_argument("--out", default="output/thumb.jpg")

    ptr = sub.add_parser("transcribe", help="音声→字幕SRT")
    ptr.add_argument("--media", required=True)
    ptr.add_argument("--out", default="output/subtitle.srt")

    pmd = sub.add_parser("model", help="プロンプト→最適モデリング手法で3D生成")
    pmd.add_argument("prompt")
    pmd.add_argument("--tool", help="強制指定: cad/openscad/freecad/gen3d/blender")

    args = p.parse_args(argv)

    if args.cmd == "factory":
        r = _factory(args.instruction, args.template, args.count)
    elif args.cmd == "studio":
        r = _studio_run(args.track, args.instruction, args.count)
    elif args.cmd == "tracks":
        r = _tracks()
    elif args.cmd == "studio-status":
        r = _studio_status()
    elif args.cmd == "check":
        return _check()
    elif args.cmd == "scene":
        from engines import scene
        stype = args.type or scene.classify(args.prompt)
        code = scene.build_scene(args.prompt, scene_type=stype, out=args.out)
        # 生成したbpyコードを scene_<type>.py として保存（Blenderで実行する用）
        outdir = Path(args.out).parent
        outdir.mkdir(parents=True, exist_ok=True)
        code_path = outdir / f"scene_{stype}.py"
        code_path.write_text(code, encoding="utf-8")
        print(json.dumps({"ok": True, "scene_type": stype, "code_path": str(code_path),
                          "frames": 120}, ensure_ascii=False, indent=2))
        return 0
    elif args.cmd == "daemon":
        _daemon(args.interval)
        return 0
    elif args.cmd == "mcp":
        from core import mcp_server
        mcp_server.main()
        return 0
    elif args.cmd == "media-edit":
        from engines import media_edit
        ok, msg = media_edit.edit_media(args.input, args.out, fmt=args.format,
                                        speed=args.speed, burn_text=args.text, audio=args.audio)
        print(json.dumps({"ok": ok, "output": msg}, ensure_ascii=False))
        return 0 if ok else 1
    elif args.cmd == "composite":
        from engines import media_edit
        ok, msg = media_edit.composite(args.base, args.overlay, args.out)
        print(json.dumps({"ok": ok, "output": msg}, ensure_ascii=False))
        return 0 if ok else 1
    elif args.cmd == "slideshow":
        from engines import media_edit
        images = [i.strip() for i in args.images.split(",") if i.strip()]
        ok, msg = media_edit.image_to_video(images, args.out, fmt=args.format)
        print(json.dumps({"ok": ok, "output": msg}, ensure_ascii=False))
        return 0 if ok else 1
    elif args.cmd == "music":
        from engines import music
        if args.video:
            gok, gmsg = music.generate(args.mood, "output/_bgm.mp3")
            if gok:
                ok, msg = music.add_bgm(args.video, "output/_bgm.mp3", args.out, 0.35)
                import os
                try: os.remove("output/_bgm.mp3")
                except OSError: pass
            else:
                ok, msg = False, gmsg
        else:
            ok, msg = music.generate(args.mood, args.out)
        print(json.dumps({"ok": ok, "output": msg}, ensure_ascii=False))
        return 0 if ok else 1
    elif args.cmd == "image":
        from engines import imaging
        ok, msg = imaging.procedural_image(args.prompt, args.out)
        print(json.dumps({"ok": ok, "output": msg}, ensure_ascii=False))
        return 0 if ok else 1
    elif args.cmd == "thumbnail":
        from engines import imaging
        ok, msg = imaging.extract_thumbnail(args.video, args.out)
        print(json.dumps({"ok": ok, "output": msg}, ensure_ascii=False))
        return 0 if ok else 1
    elif args.cmd == "transcribe":
        from engines import transcribe
        ok, msg = transcribe.transcribe(args.media, args.out)
        print(json.dumps({"ok": ok, "output": msg}, ensure_ascii=False))
        return 0 if ok else 1
    elif args.cmd == "model":
        from core import model_router
        routed = model_router.route(args.prompt)
        res = model_router.build_asset(args.prompt, tool=args.tool)
        print(json.dumps({"routed": routed, "result": {"ok": res["ok"], "tool": res.get("tool"),
                                                        "detail": res.get("detail"),
                                                        "artifacts": res.get("artifacts", [])}},
                          ensure_ascii=False, indent=2, default=str))
        return 0 if res["ok"] else 1
    else:
        p.print_help()
        return 1

    print(json.dumps(r, ensure_ascii=False, indent=2, default=str))
    return 0 if r.get("ok", False) else 1


if __name__ == "__main__":
    sys.exit(main())
