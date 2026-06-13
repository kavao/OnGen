---
name: audio-generation
description: "OnGenの単体sfx_generator.pyを使い、別プロジェクトでも効果音・BGM・検証用音源を生成する"
targets: ["*"]
---

## Purpose

OnGenの`sfx_generator.py`を単体で利用し、ゲームやアプリ向けの効果音・BGMを再現可能なコマンドとして生成する。

## Required files

- `sfx_generator.py`
- Python依存: `numpy`, `scipy`
- MP3 / OGGも必要な場合: `ffmpeg`

楽譜ファイル、サンプルWAV、README、テストは推奨だが、実行時の必須ファイルではない。

## Workflow

1. 出力目的を確認する: SFX、単旋律BGM、複数トラックBGM、検証用単音。
2. 既存プリセットまたは `scores/` に近いものがあれば再利用する。
3. 楽曲は可能な限り楽譜ファイルへ保存し、CLI引数だけに残さない。
4. 生成コマンドを実行する。
5. WAVの長さ、ピーク、クリップ有無を確認する。
6. 楽譜や実装を変更した場合は回帰テストを追加して実行する。

## Common commands

```bash
python sfx_generator.py --list-presets
python sfx_generator.py --preset coin -o coin --output-format all
python sfx_generator.py --input-file scores/tulip.abc --format abc --style sine -o tulip
python sfx_generator.py --input-file melody.abc --format abc --track-file bass.abc -o duet
python -m unittest discover -s tests -v
```

## Porting to another project

1. `sfx_generator.py` を対象プロジェクトへコピーする。
2. `numpy>=2.0` と `scipy>=1.11` を対象プロジェクトの依存へ追加する。
3. 必要なら `.rulesync/skills/audio-generation/SKILL.md` もコピーする。
4. 対象プロジェクト固有の生成コマンド、出力先、音量基準をスキルへ追記する。

## Guardrails

- 実在楽曲のサンプルは、信頼できる楽譜と音程・音価を照合する。
- `output/` の生成物だけを直して完了にしない。正本の楽譜または生成コマンドを残す。
- 現行MMLをPPMCK / MCK互換と誤認しない。互換モードが完成するまではREADMEの互換性表を確認する。
