# Pyxel 連携ガイド

このガイドを読むと、[Pyxel](https://github.com/kitao/pyxel) 向け MML を OnGen で試聴し、WAV をゲームへ持ち込む手順が分かります。

## 方言フラグ

OnGen の既定 MML は PPMCK/MCK 流です。Pyxel 2.4 以降の記法を使うときは `--mml-dialect pyxel` を付けます。

```bash
# Pyxel 方言で WAV を生成する
python tools/sound/sfx_generator.py \
  --mml-dialect pyxel \
  --input-file scores/pyxel_core_sample.mml \
  -o output/pyxel/core_sample
```

| オプション | 既定 | 説明 |
|-----------|------|------|
| `--mml-dialect` | `ppmck` | `pyxel` で Pyxel 2.4+ パーサーを使用 |
| `--max-repeat` | `2` | Pyxel の回数省略リピート `[...]` を何回展開するか（正の整数のみ） |
| `--pyxel-compat-report` | オフ | PPMCK 固有トークンなど非対応候補を stderr に列挙 |
| `--pyxel-multipart` | オフ | 1行を1パートとして解釈し、複数パートを同時演奏 |

`Q`（ゲート％）や `V`（0〜127）など、同名でも意味が異なるコマンドは方言ごとに分岐します。詳細は [MMLリファレンス](mml-reference.md#pyxel-方言) を参照してください。

## 経路1: OnGen で試聴してから Pyxel へ MML を渡す

1. `scores/pyxel_*.mml` のような短い MML を用意する（1 本 = Pyxel の 1 Sound に相当）。
2. OnGen で WAV を生成し、音程・テンポ・ゲートを確認する。
3. 問題なければ同じ MML 文字列を Pyxel の `Sound.mml()` へ渡す。

```bash
python tools/sound/sfx_generator.py \
  --mml-dialect pyxel \
  --input-file scores/pyxel_shooter_bass.mml \
  -o output/pyxel/shooter_bass \
  --play
```

Pyxel 実機との完全一致は目標にしていません。`@ENV` / `@VIB` / `@GLI` は OnGen 側で ADSR・LFO・ピッチ変調への**簡易近似**です。

## 経路2: OnGen の WAV を Pyxel `pcm()` で載せる

合成結果をそのままアセットにする方法です。MML の細かい差異の影響を受けにくく、聴感を優先するときに向きます。

1. OnGen で WAV を出力する（上記コマンド）。
2. Pyxel プロジェクトの `assets/` 等へコピーする。
3. `Sound(...).pcm(path)` または `pyxel.load` 相当の API で読み込む。

```python
import pyxel

pyxel.init(160, 120)
sfx = pyxel.Sound()
sfx.pcm("assets/shooter_bass.wav")
sfx.play(0)
```

## 4 チャンネル合奏（Music.set）

Pyxel は **1 本の MML = 1 Sound（0〜63）** です。4 パート合奏は `Music.set([s0], [s1], [s2], [s3])` で Sound ID を束ねます。

OnGen 側の対応例:

1. パートごとに MML ファイルを分ける（`bass.mml`, `lead.mml` など）。
2. それぞれ `--mml-dialect pyxel` で WAV を生成して試聴する。
3. Pyxel では各 MML を別 Sound として登録し、Music API で同時再生する。

PPMCK の `A`〜`E` トラック宣言を 1 本の Pyxel MML へ自動マージする機能はありません（API 設計が異なるため）。

### 1ファイルのマルチパートを試聴する

Pyxel Composerなどが出力する「1行につき1パート」のテキストは、`--pyxel-multipart` で同時演奏できます。空行、`;` で始まるコメント行、`http://` または `https://` で始まる共有URLはパートから除外されます。

マルチパートのテキストをWAVへ変換します。

```bash
python tools/sound/sfx_generator.py \
  --mml-dialect pyxel \
  --pyxel-multipart \
  --input-file scores/pyxel_composer_sample.mml \
  -o output/pyxel/composer-preview
```

実行後、`output/pyxel/composer-preview.wav` に全パートをミックスした音声が保存されます。通常の改行入り単一パートMMLは、`--pyxel-multipart` を付けずに使用します。

## 非対応・注意点

- PPMCK 流の `N32`（直接ノート番号）、`%` / `*` / `W()`、トラック宣言 `A`〜`E` は Pyxel 方言では使えません。
- Pyxel 2.3 以前の `old_mml` は対象外です。
- 回数省略の `[...]` は無限ループではなく `--max-repeat` 回だけ展開します（既定 2）。
- CI では Pyxel ランタイムをインストールしません。実機比較は手動環境で行います。

`--pyxel-compat-report` でスコア内の衝突トークンを事前確認できます。

```bash
python tools/sound/sfx_generator.py \
  --mml-dialect pyxel \
  --pyxel-compat-report \
  --input-file scores/ppmck_phase3_sample.mml \
  -o output/pyxel/compat_check
```

## 参照

- 計画正本: `_workingspace/plans/pyxel-mml-compatibility-plan.md`
- Pyxel 公式 MML: https://github.com/kitao/pyxel/blob/main/docs/mml-commands.md
- フィクスチャ: `scores/pyxel_*.mml`、`scores/pyxel_composer_sample.mml`（4パート・`--pyxel-multipart`）
