# OnGen ドキュメント

OnGen の音源生成、ゲームへの組み込み、スキル運用、開発検証について、目的別にガイドをまとめています。初めて使う場合は [クイックスタート](quickstart.md) から始めてください。

## 音源生成

| ガイド | 内容 |
|--------|------|
| [音源生成ガイド索引](audio/README.md) | 効果音・BGM・記法・合成の入口 |
| [クイックスタート](quickstart.md) | セットアップから最初の生成・再生まで |
| [効果音（SFX）](audio/sfx.md) | プリセット、ドラム風合成、CLIオプション |
| [BGMと楽譜](audio/bgm-and-scores.md) | MML/ABC、収録曲、複数トラック |
| [MMLリファレンス](audio/mml-reference.md) | MMLコマンド、PPMCK/MCK互換性 |
| [音色合成](audio/synthesis.md) | FM、LFO、ノイズ、ADSR、サンプル混在 |
| [出力とゲーム統合](audio/output-and-game-integration.md) | WAV/MP3/OGG、Phaser、アセット配置 |

## スキルと運用

| ガイド | 内容 |
|--------|------|
| [スキル索引](skills/README.md) | プロジェクト内スキルの概要 |
| [外部スキルの取り込み](skills/importing-external-skills.md) | 評価・導入・検証・記録の手順 |

## 開発

| ガイド | 内容 |
|--------|------|
| [テストと検証](development/testing.md) | 回帰テスト、可搬性、変更後の確認 |

## dna_kernel / Rulesync

| ガイド | 内容 |
|--------|------|
| [dna_kernel 概要](dna-kernel/README.md) | 運用構成の説明 |
| [導入・注入フロー](dna-kernel/onboarding.md) | 新規導入と既存プロジェクトへの注入 |
| [自己発展型ガバナンス](dna-kernel/self-evolving-governance.md) | パターン全体の背景 |

## 正本の所在

| 種別 | 正本 |
|------|------|
| 実装 | `tools/sound/sfx_generator.py` |
| 人間向け操作説明 | `docs/audio/` |
| MML仕様（人間向け） | `docs/audio/mml-reference.md` |
| LLM向け作業手順 | `.rulesync/skills/` |
| ファイル役割一覧 | `manifest.md` |
| 入口・代表例 | ルート `README.md` |
