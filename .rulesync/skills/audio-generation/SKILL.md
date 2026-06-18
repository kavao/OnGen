---
name: audio-generation
description: "OnGenの tools/sound/sfx_generator.py を使い、ゲーム開発でも効果音・BGM・検証用音源を生成する"
targets: ["*"]
---

## Purpose

OnGenの音源生成ツールを使い、ゲームやアプリ向けの効果音・BGMを再現可能なコマンドとして生成する。
実装正本は `tools/sound/sfx_generator.py` であり、単一ファイルとして別プロジェクトへ持ち込める。

## Pre-work check

作業開始前に次を確認する。

1. `tools/sound/sfx_generator.py` が存在するか。
2. 存在しない場合は、OnGenリポジトリから `tools/sound/sfx_generator.py` を対象プロジェクトへコピーする。
3. Python依存 `numpy>=2.0` と `scipy>=1.11` が利用可能か。
4. MP3 / OGG が必要なら `ffmpeg` が PATH にあるか。
5. `--play` でその場再生する場合は `ffplay` が PATH にあるか。
6. 対象ゲームのアセット保存先と命名規則を確認する。既存規約があればそれを優先する。

## Required files

- `tools/sound/sfx_generator.py`（またはコピーした `sfx_generator.py`）
- Python依存: `numpy`, `scipy`
- MP3 / OGGも必要な場合: `ffmpeg`
- `--play` でその場再生する場合: `ffplay`

楽譜ファイル、サンプルWAV、README、テストは推奨だが、実行時の必須ファイルではない。

## Game asset conventions

対象プロジェクトの既存規約を最優先する。規約がなければ次を候補とする。

| 種別 | 推奨保存先 | 命名 |
|------|-----------|------|
| 効果音 | `assets/audio/sfx/` | 用途が分かる名前（例: `jump.wav`, `coin_pickup_01.wav`） |
| BGM | `assets/audio/bgm/` | 曲名またはシーン名（例: `title_theme`, `stage_01_loop`） |
| ループ素材 | ゲーム側のループ規約に合わせる | ループ境界を確認できる名前 |
| 検証用 | `output/` または一時フォルダ | `migration-check/` 等、本番アセットと分離 |

生成音声は派生成果物とする。正本は楽譜（MML/ABC）または再実行可能な生成コマンドを残す。

## Workflow by material type

### SFX（効果音）

1. 用途を確認する（UI、ジャンプ、ダメージ、環境音など）。
2. `--list-presets` で既存プリセットを確認し、近いものがあれば再利用する。
3. プリセットをベースに調整する場合は、MMLまたはCLI引数を記録する。
4. 生成後に長さ、ピーク、クリッピング、立ち上がりノイズを確認する。
5. ゲームエンジン要件に応じて WAV（確認用）と MP3 / OGG を生成する。

### BGM（単旋律・複数トラック）

1. 曲の長さ、テンポ、キー、パート構成を確認する。
2. 可能な限り `scores/` 相当のディレクトリへ ABC または MML を保存する。
3. 複数トラックは `--track-file` で分離し、再生成可能に保つ。
4. 生成後に音程・音価・ミックスのヘッドルームを確認する。
5. 実在曲を使う場合は信頼できる楽譜と音程・音価を照合する。

### ループ素材

1. ループ境界が自然かを WAV で確認する。
2. ループ用の楽譜またはMMLを正本として残す。
3. エンジン側のループ仕様（シームレス、クロスフェード等）に合わせて出力形式を選ぶ。

### 検証用音源

1. 単音、短いスケール、既知の基準曲（例: チューリップ）でパーサーと合成を確認する。
2. 検証出力は本番アセットと分離する。
3. 生成後は `--lint --analyze` で楽譜イベントと波形を確認する。

## Common commands

標準パスは `python tools/sound/sfx_generator.py` とする。

```bash
python tools/sound/sfx_generator.py --list-presets
python tools/sound/sfx_generator.py --preset coin -o coin --output-format all
python tools/sound/sfx_generator.py --preset coin --play
python tools/sound/sfx_generator.py --input-file scores/tulip.abc --format abc --style sine -o tulip
python tools/sound/sfx_generator.py --input-file melody.abc --format abc --track-file bass.abc -o duet
python tools/sound/sfx_generator.py --mml-dialect pyxel --input-file scores/pyxel_core_sample.mml -o output/pyxel/core_sample
python tools/sound/sfx_generator.py --mml-dialect pyxel --pyxel-multipart --input-file scores/pyxel_composer_sample.mml -o output/pyxel/composer_sample
python tools/sound/sfx_generator.py --mml-dialect pyxel --max-repeat 4 --input-file scores/pyxel_repeat_sample.mml -o output/pyxel/repeat
python tools/sound/sfx_generator.py --mml-dialect pyxel --pyxel-multipart --input-file MML.txt -o output/pyxel/composer-preview
python -m unittest discover -s tests -v
```

品質確認コマンド（通常は `--lint --analyze` を使う）:

```bash
# 通常作業
python tools/sound/sfx_generator.py --input-file scores/example.mml --lint --analyze -o output/check/example
# 比較・記録用レポートを残す
python tools/sound/sfx_generator.py --input-file scores/example.mml --lint --analyze --report-json output/check/example.json -o output/check/example
# 警告をエラーとして扱う（CI向け）
python tools/sound/sfx_generator.py --input-file scores/example.mml --lint --analyze --fail-on-warn -o output/check/example
```

詳細は `docs/audio/quality-check.md`。

## PPMCK / MCK MML

既定の方言は `ppmck`（`--mml-dialect` 省略時）。

| 記法 | 意味 |
|------|------|
| `c4` | 4分音符 C（音符直後の数字 = 音長） |
| `O3` / `>` / `<` | オクターブ指定 / 上げ / 下げ |
| `#METER` / `#TIME` | 拍子メタ情報（再生音ではなく小節確認用） |
| `A`〜`E` | トラック宣言（A/B=square、C=triangle、D/E=noise） |
| `Q<n>` / `@Q<n>` | ゲートタイム / 60fps 換算フレーム短縮 |
| `K<n>` | 半音単位トランスポーズ |
| `N<n>` / `N<n>,<len>` | 直接ノート番号 |
| `@v<n>` | 音量エンベロープ |
| `@EP<n>` / `@EN<n>` / `@MP<n>` | ピッチ / ノート / ピッチ LFO エンベロープ |
| `\|` | マクロ内ループ指定 |

詳細・未対応項目は `docs/audio/mml-reference.md`。PPMCK/MCK マクロは実用近似であり完全互換を保証しない。

## Verification samples

各サンプルの役割を確認するときに使う。

| サンプル | 確認項目 |
|----------|----------|
| `scores/macro_pitch_variation_sample.mml` | `@v` / `@EP` / `@EN` / `@MP` の耳確認 |
| `scores/kaeru_no_uta_duet.mml` | `#METER` と 1 小節遅れ |
| `scores/ppmck_phase2_sample.mml` | `Q` / `K` / `N` / `@Q` |
| `scores/ppmck_phase3_sample.mml` | `A`〜`E` トラック宣言 |
| `scores/pyxel_*.mml` | Pyxel 方言 |
| `scores/pyxel_composer_sample.mml` | `--pyxel-multipart` |

## Pyxel 向け MML

Pyxel 2.4+ の MML は `--mml-dialect pyxel` で解釈する。既定 `ppmck` とは `Q` / `V` / `&` の意味が異なるため、方言を明示する。

1. 1 本の MML = Pyxel の 1 Sound として `scores/pyxel_*.mml` を正本にする。
2. OnGen で WAV を生成して試聴する（`--play` 可）。
3. 実機へ渡すか、`pcm()` 用 WAV として配置するかを選ぶ。

詳細は `docs/audio/pyxel-integration.md`。`@ENV` / `@VIB` / `@GLI` は簡易近似であり Pyxel 実機一致は非目標。

```bash
python tools/sound/sfx_generator.py --mml-dialect pyxel --input-file scores/pyxel_core_sample.mml -o output/pyxel/core_sample
python tools/sound/sfx_generator.py --mml-dialect pyxel --pyxel-compat-report --input-file scores/ppmck_phase3_sample.mml -o /tmp/compat_check
```

4 パート合奏は MML をファイル分割し、Pyxel 側で `Music.set` 用に Sound を束ねる。PPMCK の `A`〜`E` 宣言を 1 本へマージする機能はない。

Pyxel Composerなどの「1行につき1パート」のテキストは、`--pyxel-multipart` で全行を同時演奏する。空行、`;` コメント行、共有URL行は除外される。通常の改行入り単一パートMMLでは指定しない。

## Porting to another project

1. `tools/sound/sfx_generator.py` を対象プロジェクトへコピーする（配置先は `tools/sound/` を推奨）。
2. `numpy>=2.0` と `scipy>=1.11` を対象プロジェクトの依存へ追加する。
3. 必要なら `.rulesync/skills/audio-generation/SKILL.md` もコピーする。
4. 対象プロジェクト固有の生成コマンド、出力先、音量基準をスキルへ追記する。
5. ゲームのアセット規約（保存先、命名、音量上限）をスキルまたはプロジェクトルールへ明記する。

## Verification

生成後は最低限次を確認する。

- 長さが意図どおりか
- ピークが 0.99 未満でクリッピングしていないか
- 冒頭に立ち上がりノイズがないか（既定の `--fade-in` を確認）
- ループ素材の場合は境界の継ぎ目

コード、楽譜、またはプリセット定義を変更した場合は `python -m unittest discover -s tests -v` を実行し、終了コード 0 を確認する。

## Guardrails

- 実在楽曲のサンプルは、信頼できる楽譜と音程・音価を照合する。
- `output/` やゲームアセットの生成物だけを直して完了にしない。正本の楽譜または生成コマンドを残す。
- `output/` の WAV / JSON は派生成果物であり、MML/ABC または再実行可能な CLI コマンドを正本にする。
- MMLの音符直後の数字は音長（PPMCK / MCK流）。オクターブは`O`コマンドと相対オクターブ変更`>` / `<`で指定する。詳細・未対応項目は`docs/audio/mml-reference.md`を確認する。
- 品質判定の細部は `docs/audio/quality-check.md` を参照する。
- Pyxel 方言は完全一致ではなく簡易近似。PPMCK/MCK マクロも現時点では実用近似であり、完全互換を名乗らない。
- Rulesync生成物（`.agents/skills/audio-generation/` 等）は直接編集しない。正本は `.rulesync/skills/audio-generation/SKILL.md` を更新してから `npx rulesync generate` する。
