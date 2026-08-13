# 長尺・横動画制作

## 目的

AIFunRun-Video の長尺モードは、動画を一括生成する機能ではなく、一つのテーマを章・論点・
視覚表現・ナレーションへ分解し、ローカルの編集工程で一本の作品に組み上げる制作系です。
標準は 1920×1080 / 30 fps / 10分、上限は3時間です。

## AI利用方針

生成AIとして利用するのは DeepSeek API だけです。DeepSeek は次だけを担当します。

- 全体アウトラインと章の目的
- 章ごとの論点、ナレーション、画面文字、視覚演出の指示
- フック、感情曲線、CTA、Visual/Audio Bible

画像生成、動画生成、生成3D、音声クローンは長尺モードでは実行しません。映像と音声は、
ローカル素材、決定的な FFmpeg 演出、OS/Piper/espeak の通常読み上げ、ローカルBGMで制作します。
DeepSeek 未設定時は決定的プランナーへ退避するため、API障害でも制作工程自体は停止しません。

## 実行

```powershell
.\.venv\Scripts\python run.py longform "テーマ" --minutes 10
```

自然文でも「10分の横動画」「長尺」「YouTube 解説」などを含めると長尺テンプレートを自動選択します。
レンダー前に企画だけ確認する場合は次を使います。

```powershell
.\.venv\Scripts\python run.py brief "AIエージェントの現在地を30分の横動画で解説"
```

MCP クライアントからは `video_longform` を呼び、`instruction` と `minutes` を渡します。

## ローカル素材

写真、図版、B-roll、収録映像を `assets/library/` に入れます。対応拡張子は PNG/JPEG/WebP と
MP4/MOV/MKV/WebM です。意味のある英語または日本語のファイル名にすると、ショットの検索語と
照合して自動採用します。素材が一致しないショットは次の決定的な演出へ切り替わります。

- chapter / kinetic / diagram / timeline
- list / quote / data / process

## 長尺向けの耐障害性

- 台本を小さなチャンクへ分割して TTS を実行し、WAV をローカル結合
- ショット単位の MP4 キャッシュにより中断後の再開が可能
- 尺に比例して工場監視と FFmpeg 結合の制限時間を延長し、短尺用タイムアウトによる誤停止を回避
- `render_state.json` に完了ショットと最終状態を保存
- `chapters.ffmeta` を生成し、最終 MP4 へ章マーカーを埋め込み
- ffprobe で映像、音声、解像度、尺を機械検査
- 外部 CLI の不正な文字列を置換して読み取りスレッド停止を防止

## 成果物

- `creative_plan.json`: 章、ショット、AI方針、制作設計
- `storyboard.md`: 全ショットの人間向け一覧
- `_clips/`: 再開可能なショットキャッシュ
- `chapters.ffmeta`: 章情報
- `voice.wav` / `subtitles.srt` / `score.mp3`: 音声素材
- `visual_master.mp4` / `final.mp4`: 映像マスターと完成作品
- `quality_report.json` / `render_state.json`: 品質と進行状態
