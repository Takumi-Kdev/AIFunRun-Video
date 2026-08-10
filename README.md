# AIFunRun-Video

**動画をゼロから創作する自律システム**（スタンドアロン版）。

Blender（3D）＋ FFmpeg（編集）＋ BGM生成 ＋ 2D画像/サムネ ＋ 字幕生成 を、**テキストモーダルAI
（プロンプト）だけで操作**できる統合クリエイティブシステム。opencode 等のコーディングシステムからも
MCP 経由で操作できます。

---

## 1. 概要

- **工場型オーケストレーション**: plan → 3D資産 → Blenderシーン → レンダー → 音声 → 背景 → 編集 → BGM
- **BlenderMCP 統合**: Blender をテキスト/コード駆動
- **シーン演出エンジン**: プロンプトだけで多様な Blender シーンを自動生成
- **BGM/画像/字幕**: Blender が苦手な分野をテキスト駆動で補完
- **多トラック動画スタジオ**: アカウント × 路線 × タイプ を分離管理
- **MCP サーバー**: opencode / Claude Code 等から操作可能
- **フォールバック**: GPU/外部ツールが無くても ffmpeg で実動画を生成（必ず動く）

---

## 2. システム要件（外部コンポーネント）

| コンポーネント | 必須 | 用途 | OS対応 |
|---|---|---|---|
| **Python 3.8+**（推奨 3.10〜3.12） | ✅ | 本体 | Linux / macOS / Windows |
| **Git** | ✅ | リポジトリ取得 | Linux / macOS / Windows |
| **ffmpeg** | ✅ | 動画/音声の生成・編集・合成 | Linux / macOS / Windows |
| **pip パッケージ** | ✅ | requests / mcp / pytest / pillow | （setup で自動） |
| **Blender 3.0+** | 任意 | 3Dシーン・モデリング・レンダー | 全OS |
| **BlenderMCP アドオン** | 任意 | Blender をテキスト/LLM駆動 | 全OS |
| **faster-whisper** | 任意 | 音声→字幕生成 | 全OS（pip） |
| **GPU 3D生成**（TripoSR/TRELLIS/Hunyuan3D） | 任意 | テキスト→3D資産（GPUメインPC） | Linux/Windows |
| **TTS**（Piper/espeak-ng） | 任意 | ナレーション音声 | 全OS |

> 必須は **Python + Git + ffmpeg + pip パッケージ** だけ。あとは任意で、無くても実動画は作れます。

---

## 3. クイックスタート（最速）

### Linux / macOS
```bash
git clone https://github.com/Takumi-Kdev/AIFunRun-Video.git
cd AIFunRun-Video
bash setup.sh          # 依存 + venv + pip + .env + 検証 を一括
python3 run.py factory "AIの基本を解説するショート動画"   # 動画を生成
```

### Windows（PowerShell）
```powershell
git clone https://github.com/Takumi-Kdev/AIFunRun-Video.git
cd AIFunRun-Video
powershell -ExecutionPolicy Bypass -File setup.ps1
.\.venv\Scripts\python run.py factory "AIの基本を解説するショート動画"
```

---

## 4. インストール手順（OS別・詳細）

### 4-A. Linux（Ubuntu/Debian 例）

**Python / Git / ffmpeg**
```bash
sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip git ffmpeg
# 確認
python3 --version && git --version && ffmpeg -version | head -1
```

**セットアップ**
```bash
bash setup.sh
```

> Fedora: `sudo dnf install -y python3 python3-pip git ffmpeg`
> Arch: `sudo pacman -Sy --noconfirm python python-pip git ffmpeg`
> または自動: `bash scripts/install_deps.sh`

### 4-B. macOS

**Homebrew 導入**（未導入なら）:
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

**Python / Git / ffmpeg**
```bash
brew install python git ffmpeg
```

**セットアップ**
```bash
bash setup.sh
```
> または自動: `bash scripts/install_deps.sh`

### 4-C. Windows

**Python / Git / ffmpeg（winget）** — PowerShell で:
```powershell
winget install --id Python.Python.3.12 -e
winget install --id Git.Git -e
winget install --id Gyan.FFmpeg -e
```
> インストール後 **ターミナルを開き直す**（PATH反映）。または:
> `powershell -ExecutionPolicy Bypass -File scripts/install_deps.ps1`

**セットアップ**
```powershell
powershell -ExecutionPolicy Bypass -File setup.ps1
```
> Python のインストール時「Add python.exe to PATH」に必ずチェック。

---

## 5. 任意の高度コンポーネント（必要に応じて）

これらの追加で、より高度な動画生成が可能になります。**無くても基本動作します**。

### 5-1. Blender + BlenderMCP（3Dシーン・レンダー）
- **Blender 3.0+**
  - Linux: `sudo apt install blender` または snap/flatpak
  - macOS: `brew install --cask blender`
  - Windows: `winget install --id BlenderFoundation.Blender -e`
- **BlenderMCP アドオン**（Blender をテキスト駆動）
  ```bash
  # リポジトリから addon.py を取得して Blender へ導入
  curl -O https://raw.githubusercontent.com/ahujasid/blender-mcp/main/addon.py
  # Blender: Edit > Preferences > Add-ons > Install で addon.py を選択 → 有効化
  ```
  - 有効化後、3D View サイドバーの「BlenderMCP」→「Connect to Claude」で起動
  - 接続: 既定 `localhost:9876`（環境変数 `BLENDER_HOST` / `BLENDER_PORT` で変更可）

### 5-2. faster-whisper（音声→字幕）
```bash
pip install faster-whisper   # CPUで動作
```
→ `python3 run.py transcribe --media voice.wav --out sub.srt`

### 5-3. GPU 3D 生成（テキスト→3D資産、GPUメインPC向け）
| バックエンド | 導入 | 備考 |
|---|---|---|
| **TripoSR** | `pip install torch tsr` | 画像→3D 高速（6GB VRAM） |
| **TRELLIS** | `pip install torch trellis`（要CUDA） | 画像/テキスト→3D（16GB VRAM） |
| **Hunyuan3D** | `pip install hy3dgen` | 画像→textured 3D |

→ `engines/gen3d.py` が自動検出して使用。

### 5-4. TTS（ナレーション音声）
- **Piper**（Neural TTS・日本語可）: https://github.com/rhasspy/piper
- **espeak-ng**（軽量）: `brew install espeak-ng` / `sudo apt install espeak-ng`

### 5-5. opencode（コーディングエージェント）
```bash
# 任意のコードエージェント（opencode / Claude Code / Codex）
npm install -g opencode
```
→ 下記セクション 7 で MCP 接続。

---

## 6. 使い方

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
python3 run.py media-edit --input in.mp4 --out out.mp4 --speed 2.0
python3 run.py slideshow --images a.png,b.png --out slide.mp4
python3 run.py composite --base base.mp4 --overlay overlay.png --out out.mp4
```

### 音楽・画像・字幕（Blenderが苦手な分野）
```bash
python3 run.py music --mood calm --out bgm.mp3
python3 run.py music --mood upbeat --video out.mp4 --out with.mp4
python3 run.py image --prompt "サイバーパンクな背景" --out img.png
python3 run.py thumbnail --video out.mp4 --out th.jpg
python3 run.py transcribe --media voice.wav --out sub.srt
```

---

## 7. コーディングシステム（opencode等）から操作（MCP）

MCP サーバーを起動し、opencode / Claude Code 等から動画システムを操作できます。

```bash
./run.sh mcp      # stdio MCP サーバー起動
```

**opencode.json へ登録**:
```json
{ "mcp": {
    "video": { "type": "local", "command": ["python3", "run.py", "mcp"] }
  }
}
```

**公開ツール**: `video_factory` / `video_scene` / `video_scene_types` / `video_studio_run` /
`video_studio_status` / `video_media_edit` / `video_composite` / `video_music` /
`video_image` / `video_transcribe` / `video_check`

---

## 8. AIコーディングシステムにセットアップさせる方法

この README は、各OSの依存（Python/Git/ffmpeg）から導入まで**コマンドが完結**しています。
コーディングエージェント（opencode / Claude Code / Codex）に以下のように指示すれば、
エージェントがこの README を読み、環境に応じたセットアップを実行します。

```
このリポジトリの README.md を読み、現在のOSに合わせて
必要な外部依存（Python / Git / ffmpeg）と pip パッケージを全て導入し、
システムをセットアップして動作確認（run.py check が成功）まで完了してください。
```

エージェントは各 OS のコマンド（セクション 4）を選択して実行し、
最後に `run.py check`（セクション 6）で検証します。

---

## 9. トラブルシューティング

| 症状 | 対処 |
|---|---|
| `ffmpeg が見つかりません` | セクション 4 で ffmpeg を導入（必須） |
| `python3 が見つかりません` | セクション 4 で Python を導入（Windows は PATH 確認） |
| Blender に接続できない | セクション 5-1 で BlenderMCP アドオン有効化・ポート確認 |
| 字幕が作れない | セクション 5-2 で faster-whisper 導入 |
| 3D資産が作れない | セクション 5-3 で GPU 3D生成ツール導入（または ffmpeg フォールバック） |
| opencode から接続できない | セクション 7 の opencode.json 設定・`./run.sh mcp` 起動確認 |

---

## 10. 構成

```
core/     … paths/logger/state/tool_layer/llm/credentials/factory/studio/process/mcp_server
engines/  … blender/gen3d/motion/video2d/animate/scene/media_edit/music/imaging/transcribe/tts/moderation/tk_cut
config/   … templates/・tracks/・accounts/・lines/・characters/・factory_queue/・credentials(.env)
scripts/  … install_deps.sh(Linux/mac)・install_deps.ps1(Windows)・setup_check
tests/    … 動画システムのテスト（76件）
docs/     … 設計（VIDEO_FACTORY.md）
setup.sh / setup.ps1   … ワンショットセットアップ
run.py / run.sh        … CLI / MCP / 自律ループ
```

## ライセンス
MIT。採用/参照した外部成果物の明細は `config/THIRD_PARTY_NOTICES.md` を参照。
