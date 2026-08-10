# 動画創作ファクトリー設計（VIDEO_FACTORY）

> Blender を主軸に、オープンソースの動画・モデリングシステムを「工程（ステーション）」として
> 組み合わせ、多様なジャンル・パターンの動画を連続生産（工場型）するための設計書。
>
> 調査日: 2026-08-07 / 状態: 設計確定・実装前（開発本PC・運用はGPU搭載メインPC）

## 1. 前提（ユーザー要件の確定）

- **開発は本PC、実際の運用は GPU 搭載メインPC** → GPU前提でツール選定。
- **Blender を主軸**。Blender 自体は改変せず、標準の Python API（bpy）と **BlenderMCP** でテキスト/LLM駆動。
- **編集は既存システム**（TK-CutExpress / `core` の `video_edit`）を工場の最終工程に使う。
- **目的は SNS マーケティングで収益**。多様なジャンル・パターン（人間らしい／アニメーション／AI感）を
  並走対応する。単一ブランドに縛られない「多品種工場」。
- **キャラは差し替え可能スロット**（後でブランド決定）。リグ資産は複数用意し再利用。
- **メインPC: VRAM 12〜16GB** → 3D生成・モーション・リップ・軽量T2Vはローカル可、重いT2Vは将来クラウドAPI。

## 2. 検証済みオープンソース（ライセンス・VRAM・連携方法）

| 工程 | ツール | ライセンス | 要VRAM | Blender/システム連携 |
|---|---|---|---|---|
| Blender接続 | **BlenderMCP** (`ahujasid/blender-mcp`) | MIT | - | MCP + TCPソケット。LLMがテキストでオブジェクト/マテリアル/シーン/任意Python実行。PolyHaven/Sketchfab/Hunyuan3D/Hyper3D対応。リモートホスト可 |
| 3D資産生成 | **TRELLIS** (Microsoft) | MIT | ~16GB(境界) | 出力GLB/OBJ → Blenderインポート |
| 3D資産生成 | **TripoSR** (Tripo+Stability) | MIT | ~6GB | 画像→3D、高速。GLB/OBJ出力 |
| 3D資産生成 | **Hunyuan3D-2** (Tencent) | Tencent独自(商用要確認) | 6GB(shape)/16GB(tex) | 公式Blenderアドオン + APIサーバあり。ミニモデル推奨 |
| モーション | **MediaPipe** | Apache 2.0 | 軽量 | pose/face/hands 骨格→リグへマッピング |
| リップ | **Wav2Lip** | Apache 2.0 | ~2GB | ナレーションに合わせ口を動かす |
| レンダー | **Blender Cycles / EEVEE** | GPL(Blender内蔵) | GPU | フレーム出力 |
| T2V(軽量) | **LTX-Video / CogVideoX-2B / Wan2.1軽量系** | Apache 2.0 | 12GB前後で可 | 背景・カットの映像生成 |
| T2V(重い) | **Wan 2.1 14B 級** | Apache 2.0 | 大(要クラウド) | 将来API |
| 画像 | **FLUX.1-schnell** | Apache 2.0 | 可 | 静止画/サムネ/背景 |
| 音声 | **Kokoro-82M** / **Chatterbox** | Apache 2.0 / MIT | CPU | ナレーション |
| 字幕 | **faster-whisper** | MIT（導入済み） | CPU | 自動字幕・多言語 |
| 編集 | **TK-CutExpress（既存 video_edit）** | - | CPU | カット・字幕・縦横変換・ワークフロー |

> ライセンス注意: **Hunyuan3D は Tencent 独自ライセンス**（商用要確認）。Wav2Lip は Apache だが派生利用規約を要確認。
> BlenderMCP の `execute_blender_code` は任意Python実行＝強力だが危険。`core/sandbox.py` の承認制と併用する。

## 3. アーキテクチャ：多品種工場

```
  「◯◯ジャンルで作って」
         │
   core/director.py（工場の司令塔）: 企画→工程リスト→各Tool呼び出し→結合→投稿
         │  生産レシピ（テンプレート）を選択・切替
         ▼
   config/templates/  … ジャンル×形式×スタイルの「レシピ」を集約
   ┌─────────┬──────────┬──────────┬──────────┬────────┬────────┐
   ▼         ▼          ▼          ▼          ▼        ▼        ▼
 [3D資産]  [モーション] [リップ]   [シーン]   [レンダー][2D/CG]  [音声/編集]
 gen3d     motion      animate    blender    blender  video2d  tts/
 TRELLIS   MediaPipe   Wav2Lip   (BlenderMCP) (Cycles) (T2V)    tk_cut
 TripoSR   →Rigify                シーン・     GPU      背景・CG faster-whisper
 Hunyuan3D                         カメラ・                         YouTube(承認)
                                   ライト
```

### 工場のステーション（各OSSが1工程を担う）
| # | 工程 | 担当 |
|---|---|---|
| 1 | 3D資産生成（モデリング） | TRELLIS / TripoSR / Hunyuan3D → GLB/OBJ → Blender |
| 2 | キャラ・モーション | MediaPipe（モーションキャプチャ）+ Rigify（リグ） |
| 3 | 顔・リップ | Wav2Lip |
| 4 | シーン・カメラ | BlenderMCP（LLMがテキストで配置・照明・カメラ・アニメ） |
| 5 | レンダリング | Blender Cycles / EEVEE（メインPC GPU） |
| 6 | 2D/CG背景・カット | Wan / LTX / CogVideoX（T2V） |
| 7 | 音声 | Kokoro-82M / Chatterbox |
| 8 | 編集・字幕 | TK-CutExpress（既存 video_edit）+ faster-whisper |
| 9 | 投稿・分析 | YouTube 等（承認後に投稿・KPI収集） |

## 4. パターン（目標に応じた工場の切り替え）

| パターン | 主な稼働ステーション | 動画の例 |
|---|---|---|
| A. 人間らしい | モーション(2)+リップ(3)+シーン(4)+音声(7) | キャラが話す解説・顔出し風 |
| B. アニメーション | 3D生成(1)+モーション(2)+シーン(4)+レンダー(5) | モデリングしたキャラの3DCGアニメ |
| C. AI感・幻想的 | 2D/CG背景(6)+音声(7)+編集(8) | 生成映像のショート・ミュージック系 |

## 5. テンプレート方式（多ジャンル対応の要）

- `config/templates/` に「生産レシピ」を置く。テンプレート＝
  パターン / 形式(縦横) / キャラ(リグ資産) / 声 / 字幕 / 背景 / BGM などを定義。
- 例:
  - `ショート解説`: パターン=アニメ, 縦9:16, マスコットA, Kokoro, 字幕あり
  - `ニュース風`: パターン=人間らしい, 横16:9, ヒューマンB, Chatterbox
  - `幻想的ショート`: パターン=AI感, 縦, キャラなし, T2V背景, BGM重視
- 新しいジャンルで勝つ時はテンプレート1枚追加するだけ。既存のリグ・資産・音声を再利用できる。

## 6. 既存システムへの組み込み（DEV_STANDARD 準拠）

新規追加は `engines/` に Tool アダプタを追加し、`core/director.py` の video モードを多段工場化する。

| アダプタ | 役割 | 内部で呼ぶOSS |
|---|---|---|
| `blender` | LLM指示→BlenderMCPのソケットプロトコル | BlenderMCP |
| `gen3d` | テキスト/画像→3D資産(GLB) | TRELLIS / TripoSR / Hunyuan3D |
| `motion` | モーションキャプチャ/生成→リグ用データ | MediaPipe |
| `animate` | リグ・カメラに動きを適用しレンダー | Blender(bpy) |
| `video2d` | 背景/カットのT2V | Wan / LTX / CogVideoX |

実装手順:
1. `engines/__init__.py` の `register_all()` に登録。
2. `core/mcp_server.py` の `_tool()` で公開 → チャット/MCP/外部エージェントから日本語指示で呼べる。
3. `core/director.py` を「企画→工程リスト→各Tool→結合→投稿」の多段工場ループへ拡張。
4. `tests/test_<name>.py` + `check_systems` を通す。投稿は approval。

## 7. 実装ロードマップ

| フェーズ | 内容 | 効果 | コスト |
|---|---|---|---|
| F0 | BlenderMCPを検証・本システムへ接続（最小Blender操作） | テキストでBlender動く実証 | 無料 || F1 | `gen3d`（画像→3D: TripoSR）+ `blender` でシーン配置 | 3D資産から動画 | GPU(メインPC) |
| F2 | `motion`（MediaPipe）でキャラを動かす | アニメーション動画 | GPU |
| F3 | `video2d`（T2V背景）+ 音声/字幕/編集 | 3パターン全部対応 | GPU/API一部 |
| F4 | 全パターンを director で自動選択する工場完成 | 連続生産・量×質 | - |

## 8. 注意点

- **商用ライセンス**は各OSSを都度確認（特に Hunyuan3D、Wav2Lip、Chatterbox）。
- **VRAM**はメインPC 12〜16GB前提。重いT2VはクラウドAPIへ。
- **BlenderMCP の任意Python実行**は `core/sandbox.py` の承認制と併用し安全に。
- 声/顔クローン系は本人許諾必須。生成AI動画のプラットフォーム規約を確認。
- 目的は「作ること」でなく「SNSで稼ぐこと」。テンプレートを収益に紐づけて選定する。

## 9. 実装状況

### F0 完了（2026-08-07）: BlenderMCP 統合の土台
- `engines/blender.py` 追加: `BlenderMCPClient`（TCPソケット+JSON プロトコル）と `BlenderTool`。
  - 読み取り系: `health` / `get_scene_info` / `get_object_info` / `get_viewport_screenshot`
  - `execute_code`（任意コード実行）は `approve=True` 必須（危険なため承認制）
  - 接続先は `BLENDER_HOST` / `BLENDER_PORT`（メインPCリモート実行用）
- `engines/__init__.py` に `blender` Tool を登録（bootstrap で使える）
- `core/mcp_server.py` に `blender` MCP ツールを公開。`execute_code` は approval キュー経由。
- `tests/test_blender.py`: モックBlenderサーバーで 7 テスト追加（全通過）。
- 状態: 開発PCは Blender 未接続（要セットアップ表示は正常）。運用PCで BlenderMCP 起動後に接続可能。

### F1〜F4 完了（2026-08-07）: 工場エンジン + オーケストレーション
追加エンジン（すべて Tool Layer 登録・MCP/チャットから呼べる・フォールバック対応）:
- `engines/gen3d.py`（`gen3d`）: 画像/テキスト→3D（TripoSR/TRELLIS/Hunyuan3D）。GLB→Blenderインポートbpyコード生成、未接続時はプレースホルダ/生産指示書。
- `engines/motion.py`（`motion`）: MediaPipe→リグ変換 bpy コード、プロシージャルアイドルアニメ。
- `engines/video2d.py`（`video2d`）: テキスト→映像（T2V）。ffmpegフォールバックで**実動画ファイル**を生成。
- `engines/animate.py`（`animate`）: シーン/照明/オービット/レンダーの bpy スクリプト生成。
- `core/factory.py` + `config/templates/*.json`: **多品種・連続生産の工場オーケストレーション**。
  - テンプレート: `short_explainer` / `news_presenter` / `ai_visual`
  - ステーション: plan→assets→scene→render→voice→background→edit を順に稼働し「生産報告書」を返す。
  - 各ステーション失敗も安全に次へ（必ず動く原則）。
- 呼び出し:
  - チャット: 「工場で◯◯動画を作って」（brain の `factory` 意図）
  - MCP: `factory_run` / `factory_list` / `blender` / `gen3d` / `motion` / `video2d` / `animate`
  - 設定 `settings.factory.video_enabled=true` で `director` の動画生成が工場モードへ切替（メインPC向けデフォルトオン推奨）。
- テスト: `tests/test_factory_engines.py`(22) + `tests/test_factory.py`(6) + `tests/test_blender.py`(7)。全通過。
- 検証: 工場稼働で `background.mp4`（実動画）・`render.py`/`scene.py`/`shot.py`（Blender用）・`script.txt`・編集成果物（highlight/transcript）を生成確認。

### F5 完了（2026-08-07）: 堅牢化・網羅強化（フル稼働安定化）
- **`core/factory.py` 堅牢化**:
  - 各ステーションを **タイムアウト + リトライ** 付きで実行（`_run_guarded`）。1工程が固まっても全体を止めない。
  - テンプレート検証 `validate_template`（必須項目・ステーション・resolution の検査）。
  - **量産モード `run_batch(count, ...)`**（連続生産）。
  - **`status()`**（state の factory_* から件数・テンプレート別・最近の実行を集計）。
  - **キャラカタログ** `config/characters.json` 参照（再利用リグ/声スロット）。
  - **モデレーション安全ゲート**（moderate ステップ）→ NG時は status=needs_review。
  - **コスト計上**（finance へ GPU/API 費用を記録）。
  - 実行状態を state に記録（監査・再開）。
- **`tasks/factory_task.py`**: 自律・連続生産タスク。`config/factory_queue.json` のキューを
  未処理分だけ順に生産し `state/factory_done.json` に記録。有効化は `settings.factory.production_enabled`。
- **`config/factory_queue.json`**: 生産指示キューのサンプル。
- **呼び出し追加**:
  - チャット: 「工場の状況を教えて」「工場で3本量産して」
  - MCP: `factory_batch` / `factory_status` / `factory_characters` / `factory_list`
- **`config/settings.json` factory 拡張**: video_enabled / production_enabled / batch /
  timeout_seconds / retries / record_cost / cost_per_run。
- テスト: `tests/test_factory_hardening.py`（9件・フェイクレジストリで高速）。計104件通過。
- 検証: 自動生産タスクがキュー2件を処理し done に記録することを実証。

## 10. 動画スタジオ（多チャンネル・多トラック管理）

「何が何を動かしているか分からなくなる」問題を解決するため、制作ライン（=トラック）を
**アカウント × 路線 × 動画タイプ × キャラ** の単位で分離管理する。

- **分離**: 各トラックは独立した出力ディレクトリ（`output/tracks/<id>/`）・state名前空間
  （`state["tracks"][id]`）・生産キューを持つ。
- **一元**: メイン指示システムは `studio_status()` で全トラックの状況・最終実行・件数・
  アカウント/路線サマリを一覧確認できる。

### 構成
- `config/accounts.json` — SNSアカウント（acct_main/acct_buzz/acct_edu）
- `config/lines.json` — コンテンツ路線（evergreen/viral/news）
- `config/tracks/*.json` — トラック定義（分離の単位）
- `core/studio.py` — オーケストレータ（run_track / enqueue / run_pending / studio_status）
- `systems/studio.py` — DEV_STANDARD 準拠システムIF
- `tasks/studio_task.py` — スケジューラ用自動生産（auto_produce なトラックのキューを処理）

### 呼び出し
- チャット: 「スタジオの状況を全部教えて」/「スタジオで track_evergreen_main で作って」
- MCP: `studio_status` / `studio_run` / `studio_enqueue` / `studio_list`
- システム: `studio`（status / run / enqueue / run_pending / list_*）

### サンプルトラック
| id | アカウント | 路線 | タイプ | キャラ |
|---|---|---|---|---|
| track_evergreen_main | acct_main(YouTube) | evergreen(永遠) | short_explainer | mascot |
| track_viral_buzz | acct_buzz(TikTok) | viral(バズ) | ai_visual | none |
| track_news_edu | acct_edu(YouTube) | news(情報) | news_presenter | human_avatar |

## 11. 汎用ワークスペース管理（全業務システムの分割管理）

動画スタジオの「トラック分離」を**全業務システム**（media/email/business/fx/resale/
ec/sales/ads等）に一般化した層。

- **分離**: システムごと × ワークスペースごとに、state名前空間（`state["workspaces"][sys][ws]`）・
  ジョブ履歴・生産キュー・出力ディレクトリ（`output/workspaces/<sys>/<ws>/`）を独立管理。
- **一元**: `workspace_status()` で全システム×全ワークスペースの状況を一覧返す（メインから全業務を確認）。
- **汎用**: システム内部を書き換えず、実行をワークスペースへ記録・分離。

### 構成
- `config/workspaces.json` — システムごとのワークスペース定義（10システム・19WSサンプル）
- `core/workspaces.py` — 汎用マネージャ（list/create/invoke/enqueue/run_pending/workspace_status）
- `systems/workspaces.py` — DEV_STANDARD 準拠システムIF
- `tasks/workspace_task.py` — スケジューラで未処理ジョブを自動処理

### 呼び出し
- チャット: 「全部の業務の状況を一覧で教えて」/「ワークスペースを分けて管理して」
- MCP: `ws_status` / `ws_list` / `ws_invoke` / `ws_enqueue`
- システム: `workspaces`（status / list / create / invoke / enqueue / run_pending）
