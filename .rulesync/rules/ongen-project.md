---
targets: ["*"]
description: "OnGenプロジェクト固有の目的・正本・検証ルール"
---

# OnGen project rules

## Project goals

- `sfx_generator.py` を、単体で別プロジェクトへ持ち込める効果音・BGM生成ツールとして維持する。
- ユーザー向け正式名称は `OnGen` とする。CLIファイル名 `sfx_generator.py` と既存パス名は互換性のため維持する。
- OnGenはMIT Licenseで公開する。ライセンス正本はルートの`LICENSE`とする。
- Rulesyncの `audio-generation` スキルから、プリセット、MML、ABC、複数トラック生成を再利用できる状態にする。
- MMLは独自互換性を壊さず、PPMCK / MCK互換モードを段階的に追加する。

## Sources of truth

- 音源生成実装: `sfx_generator.py`
- 動作仕様と利用例: `README.md`
- 再生成可能な楽譜: `scores/`
- 回帰検証: `tests/test_sfx_generator.py`
- 目標とロードマップ: `_workingspace/plans/`

## Required verification

- `sfx_generator.py` の変更後は `python -m unittest discover -s tests -v` を実行する。
- 楽曲スコアの変更時は、音程・音価を固定する回帰テストを追加または更新する。
- 出力確認用音声は `output/` に生成し、正本として扱わない。
- `sfx_generator.py` の単体可搬性を壊すプロジェクト内モジュール依存を追加しない。

## MML compatibility

- 現行の独自MMLとPPMCK / MCK記法の意味が衝突する場合、黙って挙動を変更しない。
- PPMCK / MCK対応は明示的な互換モードとして追加し、既存入力の回帰テストを維持する。
- 対応状況と非互換点はREADMEと `_workingspace/plans/mml-compatibility-roadmap.md` に反映する。
