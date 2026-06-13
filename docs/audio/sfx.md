# 効果音（SFX）

このガイドを読むと、内蔵プリセットの利用、CLI オプションの調整、ドラム風の合成音の作り方が分かります。

## プリセット一覧

一覧を表示します。

```bash
python tools/sound/sfx_generator.py --list-presets
```

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

プリセットを生成します。

```bash
python tools/sound/sfx_generator.py --preset jump -o output/sfx/jump
python tools/sound/sfx_generator.py --preset coin --play
```

実行後、既定では `output/` 配下に WAV が保存されます。

## よく使う CLI オプション

| オプション | 説明 | 例 |
|-----------|------|-----|
| `--output`, `-o` | 出力ファイル名（`output/` に保存、拡張子省略可） | `-o jump` |
| `--output-format` | 出力形式 | `wav`, `mp3`, `ogg`, `all` |
| `--style` | 波形 | `square`, `sawtooth`, `triangle`, `sine`, `noise` |
| `--volume` | 音量 (0〜1) | `--volume 0.8` |
| `--fade-in` | 出力冒頭のフェード秒数（既定 0.005） | `--fade-in 0` |
| `--preset`, `-p` | 内蔵プリセット | `-p coin` |
| `--play` | 生成後に ffplay で再生 | `--play` |

複数形式の一括出力やゲーム向け配置は [出力とゲーム統合](output-and-game-integration.md) を参照してください。

## ドラム風（合成）

専用のドラムキットはありませんが、ノイズと ADSR・フィルターを組み合わせると、キック・スネア・ハイハットに近い音が作れます。

### キック

低いサイン波の胴と短いノイズのクリックを重ねます。

```bash
# 1. 低い胴（ベース）
python tools/sound/sfx_generator.py --input "O2 L8 C" --style sine --filter lowpass --cutoff 150 --attack 0.001 --decay 0.1 --sustain 0 --release 0.05 -o output/drums/kick_body

# 2. ノイズのクリックを重ねてキック完成
python tools/sound/sfx_generator.py --input "O2 L32 C" --style noise --noise-color white --filter lowpass --cutoff 400 --attack 0.001 --decay 0.03 --sustain 0 --release 0.01 --volume 0.6 --overlay-sample "output/drums/kick_body.wav:0:0.8" -o output/drums/kick_mixed
```

`kick_mixed.wav` が完成形です。`--decay` でタイトさ、`--overlay-sample` 末尾のゲインでクリックの強さを調整できます。

### スネア

```bash
python tools/sound/sfx_generator.py --input "O4 L16 C" --style noise --noise-color pink --filter highpass --cutoff 800 --attack 0.001 --decay 0.06 --sustain 0 --release 0.03 --volume 0.75 -o output/drums/snare
```

### ハイハット（クローズ）

```bash
python tools/sound/sfx_generator.py --input "O5 L32 C" --style noise --noise-color white --filter highpass --cutoff 6000 --attack 0.001 --decay 0.02 --sustain 0 --release 0.01 --volume 0.5 -o output/drums/hihat_closed
```

ノイズ全般や ADSR の詳細は [音色合成](synthesis.md) を参照してください。
