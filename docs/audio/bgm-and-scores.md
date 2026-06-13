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

## 複数トラック（合奏・伴奏）

`--track` / `--track-file` で追加トラックを指定すると、メインと同時にミックスします。

```bash
python tools/sound/sfx_generator.py --input-file scores/ode_to_joy_melody.abc --format abc --track-file scores/ode_to_joy_bass.abc --style sine -o output/bgm/ode_duet
```

カノン（3 トラック）の例です。2 声目だけ波形を変えて聞き分けやすくしています。

```bash
python tools/sound/sfx_generator.py --input-file scores/canon_in_d_bass.mml --track-file scores/canon_in_d_round1.mml --track-file scores/canon_in_d_round2.mml --track-style sine --track-style triangle --style sine -o output/bgm/canon_sample
```

`--track-style` は `--track` / `--track-file` の順に波形（square/sawtooth/triangle/sine/noise）を上書きします。ADSR・FM・LFO は全トラック共通です。

## MML の書き方

コマンド一覧と PPMCK/MCK 互換は [MMLリファレンス](mml-reference.md) を参照してください。

## 正本の扱い

- 楽譜ファイル（MML/ABC）を正本として残してください。
- `output/` の音声だけを編集して完了にしないでください。再生成可能なコマンドまたは楽譜を記録してください。
