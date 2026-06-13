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

## Common commands

標準パスは `python tools/sound/sfx_generator.py` とする。

```bash
python tools/sound/sfx_generator.py --list-presets
python tools/sound/sfx_generator.py --preset coin -o coin --output-format all
python tools/sound/sfx_generator.py --preset coin --play
python tools/sound/sfx_generator.py --input-file scores/tulip.abc --format abc --style sine -o tulip
python tools/sound/sfx_generator.py --input-file melody.abc --format abc --track-file bass.abc -o duet
python -m unittest discover -s tests -v
```

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
- MMLの音符直後の数字は音長（PPMCK / MCK流）。オクターブは`O`コマンドと相対オクターブ変更`>` / `<`で指定する。詳細・未対応項目は`docs/audio/mml-reference.md`を確認する。
- Rulesync生成物（`.agents/skills/audio-generation/` 等）は直接編集しない。正本は `.rulesync/skills/audio-generation/SKILL.md` を更新してから `rulesync generate` する。
