# 音源品質チェック

このガイドを読むと、OnGenで生成した音声と楽譜イベントを検査し、音割れ、長い無音、極端な音域、ループ時のクリックノイズリスクを確認できます。

## このドキュメントを使う場面

効果音やBGMを書いたあと、ゲームへ組み込む前に品質を確認したいときに使います。

チャットで依頼する場合は、次のように入力できます。

```text
このMMLをOnGenで生成して、lintと解析も確認してください
```

アシスタントは `--lint` と `--analyze` を使い、生成前のイベント列と生成後の波形を確認します。
ユーザーは、標準出力のレポート、生成された音声ファイル、必要に応じてJSONレポートを確認できます。

## 楽譜と波形を確認する

楽譜イベントと生成後の波形をまとめて確認します。

```bash
python tools/sound/sfx_generator.py --input-file scores/sfx_jump_sample.mml --lint --analyze -o output/lint-check/jump
```

実行後、音声ファイルが `output/lint-check/` に保存され、標準出力に `OnGen Audio Lint Report` が表示されます。

## JSONレポートを保存する

CIや作業記録で使う場合は、JSONレポートを保存します。

```bash
python tools/sound/sfx_generator.py --input-file scores/sfx_jump_sample.mml --lint --analyze --report-json output/lint-check/jump.json -o output/lint-check/jump
```

実行後、`output/lint-check/jump.json` に `status`、`peak_db`、`rms_db`、`note_range`、`issues` が保存されます。

## CIで失敗扱いにする

警告以上を失敗扱いにしたい場合は `--fail-on-warn` を使います。
まず通常実行で警告量を確認してから、CIに組み込んでください。

```bash
python tools/sound/sfx_generator.py --input-file scores/sfx_jump_sample.mml --lint --analyze --fail-on-warn -o output/lint-check/jump
```

ERRORだけを失敗扱いにする場合は `--fail-on-error` を使います。

## 判定される主な項目

| 区分 | 主なコード |
|------|-----------|
| 波形解析 | `clipping_detected`, `too_loud_peak`, `too_quiet_rms`, `too_long_silence`, `loop_click_risk` |
| 楽譜Lint | `invalid_frequency`, `note_above_hard_limit`, `note_below_hard_limit`, `note_jump_too_large`, `note_too_short`, `note_too_long` |

初期実装では自動補正は行いません。レポートを見て、音量、音長、音域、フェードなどを調整してください。
