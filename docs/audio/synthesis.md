# 音色合成

このガイドを読むと、FM、LFO、ノイズ、ADSR、WAV サンプルの混在を使った音色設計ができます。

## FM / LFO

OnGen の FM は**キャリア 1 基＋モジュレーター 1 基の 2 オペレーター相当**の簡易 FM です。DX7 のような 6 オペレーター構成には対応していません。

```bash
python tools/sound/sfx_generator.py --input "O4 L1 A" --style sine --fm --fm-ratio 2 --fm-index 3 -o output/synth/fm
python tools/sound/sfx_generator.py --input "O4 L1 A" --fm-preset bell -o output/synth/fm_bell
python tools/sound/sfx_generator.py --input "O4 L1 A" --style sine --lfo --lfo-target pitch --lfo-rate 5 --lfo-depth 0.02 -o output/synth/lfo_pitch
python tools/sound/sfx_generator.py --input "O4 L8 %12 *4 ~8 C E G" --lfo --style sine -o output/synth/fm_lfo_mml
```

| オプション | 説明 |
|-----------|------|
| `--fm` | FM 合成を有効化 |
| `--fm-ratio` | モジュレータ倍率（既定: 2.0） |
| `--fm-index` | 変調指数（既定: 2.0） |
| `--fm-preset` | `bell`, `e-piano`, `bass` |
| `--lfo` | LFO 変調を有効化 |
| `--lfo-rate` | LFO 周波数 Hz（既定: 5.0） |
| `--lfo-depth` | LFO 深度（既定: 0.02） |
| `--lfo-target` | `pitch` / `volume` / `duty` |

## ノイズ音源

`--style noise` でホワイト／ピンク／ブラウンノイズを生成できます。ADSR とフィルターを組み合わせて打撃音や環境音を調整します。

```bash
python tools/sound/sfx_generator.py --input "O4 L8 C" --style noise --attack 0.001 --decay 0.08 --sustain 0 --release 0.05 -o output/synth/noise_hit
python tools/sound/sfx_generator.py --input "O4 L1 C" --style noise --noise-color pink --filter lowpass --cutoff 3000 -o output/synth/noise_pink
```

ドラム風の具体例は [効果音（SFX）](sfx.md) の「ドラム風（合成）」を参照してください。

## ADSR エンベロープ

```bash
python tools/sound/sfx_generator.py --preset hit --attack 0.001 --decay 0.1 --sustain 0 --release 0.05 -o output/synth/hit_adsr
```

| オプション | 説明 |
|-----------|------|
| `--attack` | Attack 秒（既定: 0.01） |
| `--decay` | Decay 秒 |
| `--sustain` | Sustain (0〜1) |
| `--release` | Release 秒 |

## WAV サンプルの混在

サンプルを `samples/` などに置き、`--sample-root` または `--overlay-sample` で参照します。

以下の例では `samples/kick.wav` を**プレースホルダー**として示しています。実行前に、任意の短い WAV を `samples/kick.wav` として配置するか、パスを実在ファイルへ置き換えてください。`samples/` ディレクトリが無い場合は作成します。

```bash
mkdir samples
# 任意の kick.wav を samples/ へ配置してから実行
python tools/sound/sfx_generator.py --input "T120 L8 W(kick.wav) R4 C" --sample-root samples -o output/synth/mixed
python tools/sound/sfx_generator.py --input "O4 L4 C D E" --overlay-sample "samples/kick.wav:0:0.6" -o output/synth/overlay
```

`--overlay-sample` の形式は `path[:offset秒[:gain]]` です。

## その他の音色オプション

- 矩形波は既定で PolyBLEP アンチエイリアス処理されます（`--no-anti-alias` で無効化）。
- 出力冒頭には既定で 5ms のフェードがかかります（`--fade-in`）。
- 複数トラックのミックス時は約 1 dB のヘッドルームを確保します。

出力形式やゲーム向け配布は [出力とゲーム統合](output-and-game-integration.md) を参照してください。
