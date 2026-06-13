# 音源生成ガイド

OnGen で効果音・BGM を生成するときの人間向けマニュアルです。MML/ABC の記法、音色設計、ゲームへの出力までを目的別に案内します。

## ガイド一覧

| ページ | いつ読むか |
|--------|-----------|
| [クイックスタート](../quickstart.md) | 初めて音を出すとき |
| [効果音（SFX）](sfx.md) | プリセットやドラム風の短い音を作るとき |
| [BGMと楽譜](bgm-and-scores.md) | 楽譜ファイルや複数トラックで曲を鳴らすとき |
| [MMLリファレンス](mml-reference.md) | MML の書き方や PPMCK/MCK 互換を確認するとき |
| [Pyxel 連携](pyxel-integration.md) | Pyxel 向け MML や WAV 持ち込みを検討するとき |
| [音色合成](synthesis.md) | FM、LFO、ノイズ、ADSR、サンプル混在を使うとき |
| [出力とゲーム統合](output-and-game-integration.md) | WAV/MP3/OGG や Phaser 向け配布を検討するとき |

## 実装と正本

- 音源生成の実装正本は `tools/sound/sfx_generator.py` です。
- 再生成可能な楽譜は `scores/` に置きます。
- 生成した音声は `output/` に保存します（Git 管理外）。

LLM エージェント向けの作業手順は [audio-generation スキル](../../.rulesync/skills/audio-generation/SKILL.md) が正本です。人間向けの操作説明はこの `docs/audio/` 配下を参照してください。
