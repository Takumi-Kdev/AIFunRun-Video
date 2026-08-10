# AIFunRun-Video

**動画をゼロから創作する自律システム**（スタンドアロン版）。

Blender を主軸に、オープンソースの動画・モデリング技術を「工場の工程」として組み合わせ、
テキスト指示から動画を自律創作する。多チャンネル・多トラック管理で「何が何を動かしているか」を明確にする。

## 特徴
- **工場型オーケストレーション**: plan → assets(3D) → scene(Blender) → render → voice → background → edit
- **BlenderMCP 統合**: Blender をテキスト/コード駆動（`engines/blender`）
- **多トラック動画スタジオ**: アカウント × 路線 × タイプ × キャラ を分離管理（`core/studio`）
- **堅牢**: タイムアウト/リトライ付き工程実行・モデレーション安全ゲート
- **フォールバック**: GPU/外部ツールが無くても ffmpeg で実動画を生成（必ず動く）

## セットアップ
```bash
bash setup.sh                 # venv + 依存 + .env + 検証（ffmpeg が必要）
```

## 使い方
```bash
python3 run.py factory "AIの基本を解説するショート動画"          # 工場で生成
python3 run.py factory "幻想的なショート" --template ai_visual   # テンプレ指定
python3 run.py studio track_evergreen_main "永遠路線の解説動画"   # トラック指定
python3 run.py tracks           # トラック/アカウント/路線一覧
python3 run.py studio-status    # 全トラック状況
python3 run.py daemon           # 自律連続生産ループ
python3 run.py check            # セットアップ検証
```

## 構成
```
core/     … paths/logger/state/tool_layer/llm/credentials/factory/studio
engines/  … blender/gen3d/motion/video2d/animate/tts/moderation/tk_cut
config/   … templates/・tracks/・accounts/・lines/・characters/・factory_queue/・credentials(.env)
tests/    … 動画システムのテスト
docs/     … 設計（VIDEO_FACTORY.md）
```

## ライセンス
MIT。採用/参照した外部成果物の明細は `config/THIRD_PARTY_NOTICES.md` を参照。
