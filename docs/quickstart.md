# クイックスタート

このガイドを読むと、OnGen をセットアップし、プリセット効果音の生成、その場再生、楽譜からの BGM 生成までを一通り実行できます。

## 前提

- Python 3 が利用できること
- プロジェクトルートで作業すること

## 1. 依存関係のインストール

Python パッケージをインストールします。

```bash
pip install -r requirements.txt
```

MP3 / OGG を出力する場合は [ffmpeg](https://ffmpeg.org/download.html) を別途インストールし、PATH に追加します。`--play` でその場再生する場合は `ffplay`（ffmpeg 同梱）も PATH に必要です。

```bash
ffmpeg -version
ffplay -version
```

## 2. プリセット効果音を生成する

内蔵プリセットからコイン取得音を WAV で生成します。

```bash
python tools/sound/sfx_generator.py --preset coin -o output/quickstart/coin
```

実行後、`output/quickstart/coin.wav` が作成されます。コンソールに長さとイベント数が表示されれば成功です。

## 3. その場で再生する

`ffplay` が使える環境では、生成と同時に再生できます。

```bash
python tools/sound/sfx_generator.py --preset coin --play
```

`--play` が使えない環境では、手順 2 の WAV をメディアプレーヤーで開いてください。

## 4. 楽譜から BGM を生成する

収録済みのチューリップを ABC から生成します。

```bash
python tools/sound/sfx_generator.py --input-file scores/tulip.abc --format abc --style sine -o output/quickstart/tulip
```

実行後、`output/quickstart/tulip.wav`（約 12 秒）が作成されます。

## 5. 次に読むガイド

- プリセット一覧や効果音の調整は [効果音（SFX）](audio/sfx.md) を参照してください。
- 収録曲や複数トラックは [BGMと楽譜](audio/bgm-and-scores.md) を参照してください。
- ゲームへ組み込むときは [出力とゲーム統合](audio/output-and-game-integration.md) を参照してください。
