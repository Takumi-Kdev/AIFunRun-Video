# THIRD_PARTY_NOTICES — 採用/参照した外部成果物

このプロジェクトは、以下のオープンソース成果物のコード・アルゴリズムを
参照・移植しています。ライセンスは各成果物の LICENSE に従います。

## OpenClaw (openclaw/openclaw)
- **Version**: 2026.7.2（調査時）
- **License**: MIT License (Copyright (c) 2026 OpenClaw Foundation)
- **参照ソース**: /home/claude/refs/openclaw（リポジトリ clone・コミットしない）
- **移植した機構**:
  - `src/process/exec-runner.ts` + `exec-termination.ts` + `kill-tree.ts`
    → `core/process.py`（堅牢外部プロセス実行）
  - `packages/retry/src/index.ts`
    → `core/retry.py`（指数バックオフ + リトライ）
  - `src/agents/tool-loop-detection.ts`
    → `core/loop_detection.py`（ループ/no-progress 検知 + サーキットブレーカ）
- **利用形態**: TypeScript 実装のアルゴリズム・設計を Python へ移植。MIT の許諾範囲内。

## その他
- BlenderMCP (ahujasid/blender-mcp) — MIT — engines/blender.py がソケットプロトコルを実装
- TRELLIS (Microsoft) — MIT — engines/gen3d.py がバックエンド呼び出しを実装
- TripoSR (Tripo AI + Stability AI) — MIT — engines/gen3d.py がバックエンド呼び出しを実装
- MediaPipe (Google) — Apache 2.0 — engines/motion.py がバックエンド呼び出しを実装
- TK-CutExpress (Takumi-Kdev) — MIT — engines/tk_cut.py が連携
