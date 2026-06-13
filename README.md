![OnGen - MML/ABC audio generator](images/title.png)

# OnGen — MML/ABC 音源合成ツール

**OnGen** は、NumPy / SciPy ベースのチップチューン風音源合成 CLI です。MML・ABC 記譜から WAV / MP3 / OGG ファイルを生成します。Phaser 等のブラウザゲーム向けに MP3 + OGG の一括出力にも対応しています。

`sfx_generator.py` は、別プロジェクトへ単体で持ち込み、効果音・BGM生成ツールとして利用できる構成を維持します。LLMエージェント向けの利用手順は `.rulesync/skills/audio-generation/SKILL.md`、プロジェクト目標とMML対応計画は `_workingspace/plans/` にあります。

正式名称は `OnGen` です。CLIファイル名 `sfx_generator.py` と既存ディレクトリ名 `ongen/` は互換性のため維持します。

## dna_kernel / Rulesync

このプロジェクトには [kavao/dna_kernel](https://github.com/kavao/dna_kernel) の運用構成を取り込んでいます。`.rulesync/` がルールとスキルの正本で、生成された `AGENTS.md`、`CLAUDE.md`、`.claude/`、`.cursor/`、`.codex/`、`.agents/` はGit管理外です。

```bash
# 初期ディレクトリ確認
python init.py

# 生成内容を確認してから各LLMツール向け設定を生成
npx rulesync generate --dry-run
npx rulesync generate

# 今回の作業を月次査証ログへ追記
python tools/kernel/workspace_audit_log.py append "Implemented ..."

# 査証ログを検証
python tools/kernel/workspace_audit_log.py verify --strict
```

音源生成スキルの正本は `.rulesync/skills/audio-generation/SKILL.md` です。別プロジェクトで利用する場合は、最低限 `sfx_generator.py` とこのスキルを持ち込み、NumPy・SciPyを依存関係へ追加します。

## セットアップ

```bash
pip install -r requirements.txt
```

MP3 / OGG 出力には **ffmpeg** が別途必要です（[ffmpeg 公式](https://ffmpeg.org/download.html) からインストールし、PATH に追加）。変換は ffmpeg を直接呼び出す方式です（Python 3.13+ でも動作）。

```bash
ffmpeg -version   # 動作確認
```

## 基本的な使い方

### プリセット効果音（いちばん手軽）

```bash
python sfx_generator.py --preset jump
python sfx_generator.py --preset jump -o jump          # → output/jump.wav
python sfx_generator.py --list-presets
```

生成ファイルは既定で `output/` フォルダに保存されます（フォルダは自動作成）。

| プリセット | 用途・音作り |
|-----------|-------------|
| `jump` | 矩形波の上昇音 |
| `coin` | 簡易FMによる明るいコイン取得音 |
| `hit` | ピンクノイズ＋ハイパスの短い打撃音 |
| `explosion` | ブラウンノイズ＋ローパスの爆発音 |
| `laser` | FM＋LFOによる下降レーザー |
| `powerup` | 矩形波の段階的な上昇音 |
| `select` | 控えめなUI選択音 |
| `confirm` | 簡易FMによるUI決定音 |
| `damage` | ローパスされた下降ダメージ音 |
| `victory` | 短い勝利ファンファーレ |

全プリセットをWAV・MP3・OGGで生成する例:

```powershell
python sfx_generator.py --preset jump -o output/presets/jump --output-format all
python sfx_generator.py --preset coin -o output/presets/coin --output-format all
python sfx_generator.py --preset hit -o output/presets/hit --output-format all
python sfx_generator.py --preset explosion -o output/presets/explosion --output-format all
python sfx_generator.py --preset laser -o output/presets/laser --output-format all
python sfx_generator.py --preset powerup -o output/presets/powerup --output-format all
python sfx_generator.py --preset select -o output/presets/select --output-format all
python sfx_generator.py --preset confirm -o output/presets/confirm --output-format all
python sfx_generator.py --preset damage -o output/presets/damage --output-format all
python sfx_generator.py --preset victory -o output/presets/victory --output-format all
```

### 収録曲を鳴らす

チューリップ:

```bash
# WAV を生成
python sfx_generator.py --input-file scores/tulip.abc --format abc --style sine -o tulip

# WAV / MP3 / OGG をまとめて生成
python sfx_generator.py --input-file scores/tulip.abc --format abc --style sine -o tulip --output-format all
```

きらきら星:

```bash
# WAV を生成
python sfx_generator.py --input-file scores/twinkle_twinkle.abc --format abc --style sine -o twinkle_twinkle

# チップチューン風の矩形波で生成
python sfx_generator.py --input-file scores/twinkle_twinkle.abc --format abc --style square -o twinkle_twinkle_chip
```

アメリカ国歌「星条旗」検証済み冒頭サンプル:

```bash
# 柔らかい正弦波で生成
python sfx_generator.py --input-file scores/star_spangled_banner_sample.abc --format abc --style sine -o star_spangled_banner_sample

# WAV / MP3 / OGG をまとめて生成
python sfx_generator.py --input-file scores/star_spangled_banner_sample.abc --format abc --style triangle -o star_spangled_banner_sample --output-format all
```

米空軍バンド公開のサービス版楽譜を基準に、C調へ移調した冒頭「O say can you see, by the dawn's early light」部分です。3/4拍子、四分音符=87、弱起・付点音符・F#を含みます。

アメージング・グレース（NEW BRITAIN・1節）:

```bash
# 柔らかい正弦波
python sfx_generator.py --input-file scores/amazing_grace.abc --format abc --style sine -o amazing_grace --output-format all

# FMベル音色
python sfx_generator.py --input-file scores/amazing_grace.abc --format abc --fm-preset bell -o amazing_grace_bell
```

公開楽譜の標準旋律 `NEW BRITAIN` を基準にした、G調・3/4拍子・四分音符=80の1節です。弱起のDから始まり、音価を含めて回帰テストしています。

歓喜の歌（二重奏・二重和音サンプル）:

```bash
# 主旋律と低音伴奏を同時に鳴らす
python sfx_generator.py --input-file scores/ode_to_joy_melody.abc --format abc --track-file scores/ode_to_joy_bass.abc --style sine -o ode_to_joy_duet

# チップチューン風の二重奏を全形式で生成
python sfx_generator.py --input-file scores/ode_to_joy_melody.abc --format abc --track-file scores/ode_to_joy_bass.abc --style square -o ode_to_joy_duet_chip --output-format all
```

`--track-file` で低音パートを追加し、主旋律と同時にミックスしています。

エリーゼのために（細かな音符・休符のサンプル）:

```bash
# 2オペレーターFMのエレピ音色で演奏
python sfx_generator.py --input-file scores/fur_elise_fast_sample.abc --format abc --fm-preset e-piano -o fur_elise_fast_fm

# アンチエイリアス済み矩形波で演奏
python sfx_generator.py --input-file scores/fur_elise_fast_sample.abc --format abc --style square -o fur_elise_fast_square

# 比較用の正弦波
python sfx_generator.py --input-file scores/fur_elise_fast_sample.abc --format abc --style sine -o fur_elise_fast_sine
```

八分音符=120 BPM・十六分音符主体です。3/8拍子の弱起、小節ごとの音価、旋律間の休符を含み、細かな発音タイミングを確認できます。

生成ファイルは `output/` に保存されます。

### MML から生成

```bash
python sfx_generator.py --input "O4 L4 T120 C4 D4 E4 G4" --style square -o melody.wav
```

### ABC から生成

```bash
python sfx_generator.py --abc "X:1
K:C
Q:120
C D E | G" --style triangle -o bgm.wav
```

### 正確性の基準: チューリップ

`scores/tulip.abc` を、音程と音長の回帰テストに使う基準スコアとして収録しています。

```bash
python sfx_generator.py --input-file scores/tulip.abc --format abc --style sine -o tulip --output-format all
python -m unittest discover -s tests -v
```

基準出力は C4=261.625565Hz、A4=440Hz の十二平均律、四分音符=120 BPM、38音、12.00秒です。

### テキストファイルから読み込み

```bash
python sfx_generator.py --input-file score.mml -o out.wav
python sfx_generator.py --input-file score.abc --format abc -o out.wav
```

## よく使うオプション

| オプション | 説明 | 例 |
|-----------|------|-----|
| `--output`, `-o` | 出力ファイル名（`output/` に保存、拡張子省略可） | `-o jump` |
| `--output-format` | 出力形式 | `wav`, `mp3`, `ogg`, `all` |
| `--bitrate` | MP3 ビットレート (kbps) | `--bitrate 192` |
| `--ogg-quality` | OGG 品質 (0〜10) | `--ogg-quality 5` |
| `--style` | 波形 | `square`, `sawtooth`, `triangle`, `sine`, `noise` |
| `--no-anti-alias` | 矩形波のアンチエイリアスを無効化 | 荒いレトロ音が必要な場合 |
| `--volume` | 音量 (0〜1) | `--volume 0.8` |
| `--fade-in` | 出力冒頭のスムーズフェード秒数 | `--fade-in 0.005` |
| `--duty` | 矩形波デューティ比 | `--duty 0.25` |
| `--noise-color` | ノイズの色 | `white`, `pink`, `brown` |
| `--filter` | 共通フィルター | `none`, `lowpass`, `highpass` |
| `--cutoff` | フィルターのカットオフ周波数 Hz | `--cutoff 2000` |
| `--fm-preset` | 2オペレーターFM音色 | `bell`, `e-piano`, `bass` |
| `--preset`, `-p` | 内蔵プリセット | `-p coin` |

矩形波は既定で PolyBLEP アンチエイリアス処理され、耳障りな折り返しノイズを抑えます。複数トラックのミックス時には、圧縮形式での音割れを避けるため約 1 dB のヘッドルームを確保します。

再生開始時のクリックや立ち上がりノイズを抑えるため、既定で出力全体の冒頭に5msのスムーズフェードを適用します。無効化する場合は `--fade-in 0`、さらに柔らかくする場合は `--fade-in 0.02` などを指定します。各音符の立ち上がりは `--attack` で調整できます。

## MML コマンド（独自簡易版）

現状のMMLはPPMCK / MCKを参考にした部分がありますが、**まだPPMCK / MCK互換ではありません**。特に音符直後の数字の意味が異なります。

```text
PPMCK / MCK: c4 = 四分音符のC
現行OnGen:  C4 = オクターブ4のC（音長はLコマンドを使用）
```

そのため、既存のPPMCK / MCK楽譜をそのまま読み込むと音長・オクターブ・ループなどが誤って解釈される可能性があります。

| コマンド | 意味 |
|---------|------|
| `C4 D4 E4` | ノート（音名 + オクターブ） |
| `O4` | オクターブ指定 |
| `L8` | デフォルト音長 |
| `T120` | テンポ (BPM) |
| `V15` | 音量 (0〜15) |
| `R` / `R8` | 休符 |
| `[C4D4E4]2` | ループ（2回） |
| `@1` | 音色プリセット（1〜7） |
| `%12` | FM 変調指数 (0〜15) |
| `*4` | FM モジュレータ倍率（値÷2） |
| `~8` | LFO 深度 (0〜15) |
| `W(kick.wav)` | WAV サンプル再生 |

### PPMCK / MCK互換性

| PPMCK / MCK記法 | 現状 | 備考 |
|-----------------|------|------|
| `c d e f g a b` | 部分対応 | 大文字・小文字を同一視 |
| `+`, `-` | 対応 | シャープ・フラット |
| `r4`, `r8` | 対応 | 休符の音長指定 |
| `t120` | 対応 | テンポ |
| `l4`, `l8` | 対応 | デフォルト音長 |
| `o4` | 対応 | オクターブ指定 |
| `v0`〜`v15` | 対応 | 固定音量 |
| `c4`, `c8` | **非互換** | 現状は数字をオクターブとして解釈 |
| `>`, `<` | 未対応 | 相対オクターブ変更 |
| `c.`, `c4.` | 部分対応 | デフォルト音長への付点のみ実用可能 |
| `&`, `^` | 未対応 | タイ・音長連結 |
| `q`, `@q` | 未対応 | ゲートタイム／クオンタイズ |
| `[ ... ]4` | **非互換** | 現状は基本的に2回反復のみ |
| `|: ... :|` | 未対応 | 多重リピート |
| `K<num>` | 未対応 | トランスポーズ |
| `n<num>` | 未対応 | ノート番号直接指定 |
| トラック文字 `A`〜`E` | 未対応 | CLIの`--track` / `--track-file`を使用 |
| `#TITLE`等のヘッダ | 未対応 | 読み飛ばされる可能性あり |
| `@v`, `@EN`, `@EP`等のマクロ | 未対応 | エンベロープ・アルペジオマクロ |
| `@DPCM` | 未対応 | 代替として独自記法`W(...)`を使用 |

独自拡張の `%`（FM指数）、`*`（FM倍率）、`~`（LFO深度）、`W(...)`（WAV再生）はPPMCK / MCK記法ではありません。

## FM / LFO

本ツールの FM は、**キャリア1基＋モジュレーター1基の2オペレーター相当**の簡易FMです。実装上はモジュレーターでキャリアの位相を変調します。LFOはオペレーター個別ではなく、出力音の音程・音量・矩形波デューティ比に作用します。

DX7のような6オペレーター、複数アルゴリズム、オペレーターごとのエンベロープ、フィードバックには対応していません。複雑なFM音色の再現より、効果音や簡単な音色変化を手軽に作ることを目的としています。

```bash
# FM合成: 倍音を増やして金属的な音色にする
python sfx_generator.py --input "O4 L1 A4" --style sine --fm --fm-ratio 2 --fm-index 3 -o fm

# 2オペレーターFM音色プリセット
python sfx_generator.py --input "O4 L1 A4" --fm-preset bell -o fm_bell
python sfx_generator.py --input "O4 L1 A4" --fm-preset e-piano -o fm_e_piano
python sfx_generator.py --input "O2 L1 A2" --fm-preset bass -o fm_bass

# ビブラート: 音程を周期的に揺らす
python sfx_generator.py --input "O4 L1 A4" --style sine --lfo --lfo-target pitch --lfo-rate 5 --lfo-depth 0.02 -o lfo_pitch

# トレモロ: 音量を周期的に揺らす
python sfx_generator.py --input "O4 L1 A4" --style sine --lfo --lfo-target volume --lfo-rate 5 --lfo-depth 0.8 -o lfo_volume

# PWM: 矩形波のデューティ比を周期的に揺らす
python sfx_generator.py --input "O4 L1 A4" --style square --lfo --lfo-target duty --lfo-rate 2 --lfo-depth 0.5 -o lfo_duty

# MMLコマンドで FM + ビブラート
python sfx_generator.py --input "O4 L8 %12 *4 ~8 C4 E4 G4" --lfo --style sine -o fm_lfo
```

| オプション | 説明 |
|-----------|------|
| `--fm` | FM 合成を有効化 |
| `--fm-ratio` | モジュレータ倍率（既定: 2.0） |
| `--fm-index` | 変調指数（既定: 2.0） |
| `--lfo` | LFO 変調を有効化 |
| `--lfo-rate` | LFO 周波数 Hz（既定: 5.0） |
| `--lfo-depth` | LFO 深度（既定: 0.02） |
| `--lfo-target` | `pitch` / `volume` / `duty` |

`--lfo-depth` は `pitch` では基準周波数に対する揺れ幅、`volume` では振幅の揺れ幅、`duty` では矩形波のパルス幅変化量として扱われます。比較用サンプルは `output/sample_fm_lfo_*.wav` に生成できます。

## ノイズ音源

`--style noise` では、ホワイト／ピンク／ブラウンノイズを生成できます。共通のADSRとローパス／ハイパスフィルターを組み合わせて、打撃音、風、地鳴りなどを調整できます。フィルターはノイズ以外の波形にも適用できます。

```bash
# 短く減衰する打撃音向けノイズ
python sfx_generator.py --input "O4 L8 C4" --style noise --attack 0.001 --decay 0.08 --sustain 0 --release 0.05 -o noise_hit

# 柔らかいピンクノイズ
python sfx_generator.py --input "O4 L1 C4" --style noise --noise-color pink --filter lowpass --cutoff 3000 -o noise_pink

# 低域の強いブラウンノイズ
python sfx_generator.py --input "O4 L1 C4" --style noise --noise-color brown --filter lowpass --cutoff 800 -o noise_brown

# 高域だけを残したホワイトノイズ
python sfx_generator.py --input "O4 L1 C4" --style noise --noise-color white --filter highpass --cutoff 5000 -o noise_highpass
```

## WAV サンプルの混在

サンプルファイルを `samples/` などに置き、`--sample-root` で参照します。

```bash
# MML でサンプルと合成音を混在
python sfx_generator.py --input "T120 L8 W(kick.wav) R4 C4" --sample-root samples -o mixed.wav

# 生成した音の上にサンプルを重ねる
# 形式: ファイルパス[:開始秒[:ゲイン]]
python sfx_generator.py --input "O4 L4 C4 D4 E4" --overlay-sample "samples/kick.wav:0:0.6" -o overlay.wav
```

## ADSR エンベロープ

```bash
python sfx_generator.py --preset hit --attack 0.001 --decay 0.1 --sustain 0 --release 0.05 -o hit.wav
```

## 複数トラックの同時再生（合奏・伴奏）

`--track` / `--track-file` で追加トラックを指定すると、メインのトラックと同時に再生して1つのファイルにミックスします（複数回指定可）。

```bash
# メロディ + ベースラインを同時に鳴らす
python sfx_generator.py --input "O4 L4 T120 C D E F" --style triangle \
  --track "O3 L4 T120 C E G C" -o duet

# ファイルで指定（拡張子 .abc は ABC として解釈）
python sfx_generator.py --input-file melody.mml --track-file bass.mml --track-file harmony.abc -o song
```

各トラックには `--style` などの全体設定が共通で適用されます。音色を変えたい場合は MML の `@1`〜`@7`（音色プリセット）をトラックごとに指定してください。

## 出力フォーマット（Phaser 向け）

```bash
# WAV のみ（既定）
python sfx_generator.py --preset jump -o jump

# MP3 のみ（SFX 配布向け、軽量）
python sfx_generator.py --preset jump -o jump --output-format mp3 --bitrate 192

# OGG のみ
python sfx_generator.py --preset jump -o jump --output-format ogg

# WAV + MP3 + OGG 一括（Phaser で同一キーに両形式を渡す運用向け）
python sfx_generator.py --input "O4 L4 C4 D4 E4" -o jump --output-format all --bitrate 192
# → output/jump.wav, output/jump.mp3, output/jump.ogg
```

Phaser での読み込み例:

```javascript
this.load.audio('jump', ['audio/jump.ogg', 'audio/jump.mp3']);
```

| 用途 | 推奨フォーマット | 備考 |
|------|----------------|------|
| 短い SFX | `wav` または `mp3` | WAV は編集向け、MP3 は軽量 |
| BGM | `ogg` または `all` | OGG は圧縮効率・ループ向き |
| クロスブラウザ配布 | `all` | MP3 + OGG を同時生成 |

## 出力仕様

- サンプリングレート: 44100 Hz
- WAV ビット深度: 16 bit
- チャンネル: モノラル
- MP3: `--bitrate` で指定（既定 192 kbps）
- OGG: Vorbis、`--ogg-quality` で指定（既定 5）

## ファイル構成

```
OnGen/
├── .rulesync/          # Rulesyncルール・スキルの正本
├── _workingspace/      # ローカルの目標・進行ログ・計画
├── docs/dna-kernel/    # dna_kernelの運用説明
├── tools/kernel/       # 査証ログ等の運用ツール
├── rulesync.jsonc      # Rulesync生成設定
├── .gitignore          # 生成音源・キャッシュ・ローカル作業物を除外
├── .gitattributes      # 改行コードと音声バイナリの扱いを固定
├── sfx_generator.py   # メインスクリプト（単一ファイル）
├── requirements.txt
├── scores/             # 再生成可能な楽譜
├── tests/              # 音程・音長の回帰テスト
├── samples/           # WAV サンプル置き場（任意）
├── output/            # 生成 WAV の出力先（自動作成）
└── README.md
```

`output/` の音声ファイルは楽譜とコマンドから再生成できるため、Gitの追跡対象外です。再生成に必要な `scores/`、`samples/`、`tests/` は追跡対象として残します。

## License

OnGen is released under the [MIT License](LICENSE).
