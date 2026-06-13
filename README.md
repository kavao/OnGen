![OnGen - MML/ABC audio generator](images/title.png)

# OnGen — MML/ABC 音源合成ツール

**OnGen** は、NumPy / SciPy ベースのチップチューン風音源合成 CLI です。MML・ABC 記譜から WAV / MP3 / OGG を生成します。

実装正本は `tools/sound/sfx_generator.py` です。詳しい操作説明は [docs/](docs/README.md) にあります。

## できること

- 内蔵プリセットから効果音を生成する
- MML / ABC 楽譜から BGM を生成する
- 複数トラックをミックスする
- FM、LFO、ノイズ、ADSR で音色を調整する
- WAV / MP3 / OGG を出力する（ゲーム向け）

## セットアップ

```bash
pip install -r requirements.txt
```

MP3 / OGG には [ffmpeg](https://ffmpeg.org/download.html) が別途必要です。`--play` でその場再生する場合は `ffplay`（ffmpeg 同梱）も PATH に追加してください。

## 30秒クイックスタート

### プリセットを生成して再生する

```bash
python tools/sound/sfx_generator.py --preset coin --play
```

`ffplay` が使えない環境では、次のコマンドで WAV だけ生成してください。

```bash
python tools/sound/sfx_generator.py --preset coin -o output/quickstart/coin
```

成功時は `output/quickstart/coin.wav` が作成されます。

### 楽譜から BGM を生成する

```bash
python tools/sound/sfx_generator.py --input-file scores/tulip.abc --format abc --style sine -o output/quickstart/tulip
```

成功時は `output/quickstart/tulip.wav`（約 12 秒）が作成されます。

## ゲーム開発・別プロジェクトで使う場合

1. `tools/sound/sfx_generator.py` を対象プロジェクトへコピーする
2. `numpy>=2.0` と `scipy>=1.11` を依存に追加する
3. 生成コマンドと楽譜を正本として残し、音声は再生成可能に保つ

詳細は [出力とゲーム統合](docs/audio/output-and-game-integration.md) と [audio-generation スキル](.rulesync/skills/audio-generation/SKILL.md) を参照してください。

## 外部スキルを取り込む前に

便利さだけで取り込まず、次を確認してから導入してください。

- 配布元、作者、バージョンまたはコミットを特定できるか
- `SKILL.md` と参照するスクリプト・設定・アセットを読めるか
- ファイル書き込み、削除、外部通信、秘密情報、外部 API、課金を要求するか
- 依存パッケージ、対応 OS、必要コマンドがプロジェクトと両立するか
- ライセンスと再配布条件がプロジェクト用途に合うか
- 導入前後の差分、Rulesync dry-run、関連テストを確認できるか

詳細手順は [外部スキルの取り込み](docs/skills/importing-external-skills.md) を参照してください。

## ドキュメント

| ガイド | 内容 |
|--------|------|
| [ドキュメント索引](docs/README.md) | 全ガイドの入口 |
| [クイックスタート](docs/quickstart.md) | セットアップから最初の生成まで |
| [効果音（SFX）](docs/audio/sfx.md) | プリセット、ドラム風合成、CLI |
| [BGMと楽譜](docs/audio/bgm-and-scores.md) | 収録曲、複数トラック |
| [MMLリファレンス](docs/audio/mml-reference.md) | MML コマンド、PPMCK/MCK 互換 |
| [音色合成](docs/audio/synthesis.md) | FM、LFO、ノイズ、ADSR |
| [出力とゲーム統合](docs/audio/output-and-game-integration.md) | WAV/MP3/OGG、Phaser |
| [スキル運用](docs/skills/README.md) | スキル索引、外部スキル取り込み |
| [dna_kernel](docs/dna-kernel/README.md) | Rulesync・ガバナンス運用 |

## 開発・テスト

```bash
python -m unittest discover -s tests -v
```

手順の詳細は [テストと検証](docs/development/testing.md) を参照してください。

## ライセンス

OnGen is released under the [MIT License](LICENSE).
