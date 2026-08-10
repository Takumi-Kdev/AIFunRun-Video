#!/usr/bin/env python3
"""AIFunRun-Video — 動画をゼロから創作するスタンドアロンCLI。

使い方:
  python run.py factory "指示文" [--template テンプレ] [--count N]
  python run.py studio <トラックID> "指示文" [--count N]
  python run.py tracks                 # トラック/アカウント/路線一覧
  python run.py studio-status          # スタジオ全トラック状況
  python run.py check                  # セットアップ検証
  python run.py daemon [--interval 60] # 自律連続生産ループ
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

    pd = sub.add_parser("daemon", help="自律生産ループ")
    pd.add_argument("--interval", type=int, default=60)

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
    elif args.cmd == "daemon":
        _daemon(args.interval)
        return 0
    else:
        p.print_help()
        return 1

    print(json.dumps(r, ensure_ascii=False, indent=2, default=str))
    return 0 if r.get("ok", False) else 1


if __name__ == "__main__":
    sys.exit(main())
