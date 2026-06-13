# BGMと楽譜

このガイドを読むと、MML/ABC からの生成、収録曲の利用、複数トラックのミックスができます。

## MML から生成

MML 文字列を直接渡して生成します。

```bash
python tools/sound/sfx_generator.py --input "O4 L4 T120 C D E G" --style square -o output/bgm/melody
```

## ABC から生成

ABC 記譜をファイルまたは文字列で渡します。ファイル例では、収録済みの `scores/tulip.abc` を使います。

```bash
python tools/sound/sfx_generator.py --input-file scores/tulip.abc --format abc --style sine -o output/bgm/tulip
```

独自の ABC ファイルを使う場合は、実在するパスへ置き換えてください（`score.abc` はプレースホルダー名です）。

```bash
python tools/sound/sfx_generator.py --input-file path/to/your_score.abc --format abc -o output/bgm/from_file
```

## 収録曲の例

`scores/` に再生成可能な楽譜を収録しています。

| 楽譜 | 用途 |
|------|------|
| `tulip.abc` | 音程・音長の回帰テスト基準（12 秒、38 音） |
| `twinkle_twinkle.abc` | 単旋律の ABC 例 |
| `amazing_grace.abc` | 弱起・付点を含む 3/4 拍子 |
| `ode_to_joy_melody.abc` + `ode_to_joy_bass.abc` | 二重奏サンプル |
| `scores/ppmck_phase2_sample.mml` | フェーズ2互換（Q/K/N）の検証用 |
| `scores/ppmck_phase3_sample.mml` | フェーズ3互換（A〜E トラック宣言）の検証用 |
| `scores/eine_kleine_nachtmusik_sample.mml` | モーツァルト（アレグロ冒頭 mm.1〜4、A/C 二声） |
| `scores/pyxel_*.mml` | Pyxel 方言の短尺フィクスチャ |
| `scores/pyxel_composer_sample.mml` | Pyxel Composer 由来の4パート曲（権利フリー） |
| `scores/sfx_*_sample.mml` | MML 効果音サンプル（ジャンプ・コイン・打撃・UI 等） |
| `canon_in_d_*.mml` | 3 トラックのカノン |
| `fur_elise_fast_sample.abc` | 短い音符・休符のタイミング確認 |

チューリップ（基準曲）の生成例です。

```bash
python tools/sound/sfx_generator.py --input-file scores/tulip.abc --format abc --style sine -o output/bgm/tulip --output-format all
```

基準出力は C4=261.625565Hz、A4=440Hz、四分音符=120 BPM、38 音、12.00 秒です。

きらきら星の例です。

```bash
python tools/sound/sfx_generator.py --input-file scores/twinkle_twinkle.abc --format abc --style sine -o output/bgm/twinkle
python tools/sound/sfx_generator.py --input-file scores/twinkle_twinkle.abc --format abc --style square -o output/bgm/twinkle_chip
```

## 複数トラック（PPMCK形式・CLI）

### MML 内トラック宣言（フェーズ3）

1つの `.mml` ファイルに `A`〜`E` のトラック宣言を書くと、自動でミックスされます。

```text
A @1 V12 O4 L4 T120
C4 E4 G4
B @2 V10 O4 L8
E8 G8 C8
C V8 O3 L2
C2 G2 E2
```

| PPMCKチャンネル | OnGen 波形 | 備考 |
|----------------|------------|------|
| A, B | square | `@0`〜`@3` でデューティ比（12.5% / 25% / 50% / 75%） |
| C | triangle | |
| D, E | noise | E（DPCM）はノイズ代替。サンプルは `W(...)` を使用 |

裸の `A C4 D4` や `C D E F` は従来どおり単一トラックの音符列として解釈します。複数トラックとして確実に認識させるには、異なるチャンネルを2つ以上宣言するか、`AB` の複数文字宣言、または `A @1 ...` のようにチャンネル設定を続けてください。

最初のトラック宣言より前に書いた `T120 L8` などのMML設定は、すべてのトラックへ共通適用されます。

検証用: `scores/ppmck_phase3_sample.mml`

```bash
python tools/sound/sfx_generator.py --input-file scores/ppmck_phase3_sample.mml -o output/bgm/ppmck_phase3
```

### 実在曲サンプル（モーツァルト）

`scores/eine_kleine_nachtmusik_sample.mml` は『アイネ・クライネ・ナハトムジーク』第1楽章アレグロの冒頭 **4小節のみ** です。P.D. 編曲の PPMCK 形式を OnGen 向けに収録しています（`T180` `K-7`、トラック A=メロディ、C=和声）。

```bash
python tools/sound/sfx_generator.py --input-file scores/eine_kleine_nachtmusik_sample.mml -o output/bgm/eine_kleine_nachtmusik_sample
python tools/sound/sfx_generator.py --input-file scores/eine_kleine_nachtmusik_sample.mml -o output/bgm/eine_kleine_nachtmusik_sample --play
```

成功時は約 5 秒のミックス WAV が生成されます。

### CLI の `--track` / `--track-file`

別ファイルや追加パートを重ねる場合は従来どおり CLI フラグを使います。

```bash
python tools/sound/sfx_generator.py --input-file scores/ode_to_joy_melody.abc --format abc --track-file scores/ode_to_joy_bass.abc --style sine -o output/bgm/ode_duet
```

カノン（3 トラック）の例です。2 声目だけ波形を変えて聞き分けやすくしています。

```bash
python tools/sound/sfx_generator.py --input-file scores/canon_in_d_bass.mml --track-file scores/canon_in_d_round1.mml --track-file scores/canon_in_d_round2.mml --track-style sine --track-style triangle --style sine -o output/bgm/canon_sample
```

`--track-style` は、MML内トラックではなく `--track` / `--track-file` の順に波形（square/sawtooth/triangle/sine/noise）を上書きします。ADSR・FM・LFO は全トラック共通です。

## Pyxel Composer 4パート曲

`scores/pyxel_composer_sample.mml` は Pyxel MML Studio 由来の権利フリー楽譜です。1行が1パート（メロディ・和声・コード・打撃）になっています。4パートをまとめて試聴するときは `--pyxel-multipart` を付けます。

```bash
python tools/sound/sfx_generator.py \
  --mml-dialect pyxel \
  --pyxel-multipart \
  --input-file scores/pyxel_composer_sample.mml \
  -o output/bgm/pyxel_composer_sample
```

`ffplay` が使える環境では、その場再生もできます。

```bash
python tools/sound/sfx_generator.py \
  --mml-dialect pyxel \
  --pyxel-multipart \
  --input-file scores/pyxel_composer_sample.mml \
  -o output/bgm/pyxel_composer_sample \
  --play
```

成功時は約 32 秒の WAV が `output/bgm/pyxel_composer_sample.wav` に保存されます。ファイル末尾の MML Studio 共有 URL はパース時に自動で除外されます。

1パートだけ聞く場合は、該当行だけを `--input` に渡すか、行を抜き出した小さな `.mml` を別途用意してください（`--pyxel-multipart` は付けません）。

## MML の書き方

コマンド一覧と PPMCK/MCK 互換は [MMLリファレンス](mml-reference.md) を参照してください。

## 正本の扱い

- 楽譜ファイル（MML/ABC）を正本として残してください。
- `output/` の音声だけを編集して完了にしないでください。再生成可能なコマンドまたは楽譜を記録してください。
