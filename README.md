# AIFunRun-Video

**動画をゼロから創作する自律システム**（スタンドアロン版）。

Blender を主軸に、オープンソースの動画・モデリング技術を「工場の工程」として組み合わせ、
テキスト指示から動画を自律創作する。多チャンネル・多トラック管理で「何が何を動かしているか」を明確にする。

## 特徴
- **工場型オーケストレーション**: plan → assets(3D) → scene(Blender) → render → voice → background → edit
- **BlenderMCP 統合**: Blender をテキスト/コード駆動（`engines/blender`）
- **シーン演出エンジン**: プロンプトだけで多様な Blender シーンを自動生成（`engines/scene`）
- **メディア編集・合成**: FFmpeg で画像/動画編集 + Blender オーバーレイ合成（`engines/media_edit`）
- **BGM/音楽生成**: テキスト（ムード）からBGM生成・動画へ合成（`engines/music`）
- **2D画像/サムネイル**: テキストから画像・サムネ・背景を生成（`engines/imaging`）
- **字幕生成**: 音声→字幕SRT・焼き込み（faster-whisper、`engines/transcribe`）
- **多トラック動画スタジオ**: アカウント × 路線 × タイプ × キャラ を分離管理（`core/studio`）
- **MCP サーバー**: opencode / Claude Code 等のコーディングシステムから操作可能
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
python3 run.py scene "商品プロモーション"                        # Blenderシーン生成
python3 run.py tracks           # トラック/アカウント/路線一覧
python3 run.py studio-status    # 全トラック状況
python3 run.py daemon           # 自律連続生産ループ
python3 run.py check            # セットアップ検証
```

### メディア編集・合成（FFmpeg + Blender）
```bash
python3 run.py media-edit --input in.mp4 --out out.mp4 --format vertical --text "タイトル"
python3 run.py media-edit --input in.mp4 --out out.mp4 --speed 2.0          # 2倍速
python3 run.py slideshow --images a.png,b.png --out slide.mp4              # ケンバーンズ風スライド
python3 run.py composite --base base.mp4 --overlay overlay.png --out out.mp4 # Blender合成
```

### 音楽・画像・字幕（テキスト駆動・Blenderが苦手な部分を補完）
```bash
python3 run.py music --mood calm --out bgm.mp3               # BGM生成
python3 run.py music --mood upbeat --video out.mp4 --out with.mp4  # 動画へBGM合成
python3 run.py image --prompt "サイバーパンクな背景" --out img.png  # 2D画像
python3 run.py thumbnail --video out.mp4 --out th.jpg         # サムネイル
python3 run.py transcribe --media voice.wav --out sub.srt     # 音声→字幕
```

## opencode / コーディングシステムから操作（MCP）
MCP サーバーを起動し、opencode 等の MCP クライアントから動画システムを操作できます。
```bash
./run.sh mcp      # stdio MCP サーバー起動
```
`opencode.json` へ登録（例）:
```json
{ "mcp": {
    "video": { "type": "local", "command": ["python3", "run.py", "mcp"] }
  }
}
```
公開ツール: `video_factory` / `video_scene` / `video_scene_types` / `video_studio_run` /
`video_studio_status` / `video_media_edit` / `video_composite` / `video_music` /
`video_image` / `video_transcribe` / `video_check`

## 構成
```
core/     … paths/logger/state/tool_layer/llm/credentials/factory/studio/process/mcp_server
engines/  … blender/gen3d/motion/video2d/animate/scene/media_edit/tts/moderation/tk_cut
config/   … templates/・tracks/・accounts/・lines/・characters/・factory_queue/・credentials(.env)
tests/    … 動画システムのテスト
docs/     … 設計（VIDEO_FACTORY.md）
```

## ライセンス
MIT。採用/参照した外部成果物の明細は `config/THIRD_PARTY_NOTICES.md` を参照。
