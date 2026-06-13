# 出力とゲーム統合

このガイドを読むと、WAV/MP3/OGG の出力、Phaser 向けの配布、ゲームアセットへの配置ができます。

## 出力形式

```bash
# WAV のみ（既定）
python tools/sound/sfx_generator.py --preset jump -o output/game/jump

# MP3 のみ
python tools/sound/sfx_generator.py --preset jump -o output/game/jump --output-format mp3 --bitrate 192

# OGG のみ
python tools/sound/sfx_generator.py --preset jump -o output/game/jump --output-format ogg

# WAV + MP3 + OGG 一括
python tools/sound/sfx_generator.py --preset jump -o output/game/jump --output-format all --bitrate 192
```

実行後、`output/game/` 配下に選択した形式のファイルが作成されます。

| 用途 | 推奨フォーマット | 備考 |
|------|----------------|------|
| 短い SFX | `wav` または `mp3` | WAV は編集向け、MP3 は軽量 |
| BGM | `ogg` または `all` | OGG は圧縮効率・ループ向き |
| クロスブラウザ配布 | `all` | MP3 + OGG を同時生成 |

## 出力仕様

- サンプリングレート: 44100 Hz
- WAV ビット深度: 16 bit
- チャンネル: モノラル
- MP3: `--bitrate`（既定 192 kbps）
- OGG: Vorbis、`--ogg-quality`（既定 5）

## Phaser 向けの読み込み例

```javascript
this.load.audio('jump', ['audio/jump.ogg', 'audio/jump.mp3']);
```

## ゲームアセットへの配置

対象ゲームの既存規約を最優先してください。規約がなければ次を候補にします。

| 種別 | 推奨保存先 | 命名 |
|------|-----------|------|
| 効果音 | `assets/audio/sfx/` | 用途が分かる名前（例: `jump.wav`） |
| BGM | `assets/audio/bgm/` | 曲名またはシーン名 |

生成音声は派生成果物です。正本は楽譜（MML/ABC）または再実行可能な生成コマンドを残してください。

## 別プロジェクトへの持ち込み

```bash
cp tools/sound/sfx_generator.py /path/to/game/tools/sound/sfx_generator.py
```

`numpy>=2.0` と `scipy>=1.11` を依存に追加し、`python tools/sound/sfx_generator.py --list-presets` で動作を確認してください。

LLM エージェント向けの詳細ワークフローは [audio-generation スキル](../../.rulesync/skills/audio-generation/SKILL.md) を参照してください。
