# OnGen sound tool

`tools/sound/sfx_generator.py` は OnGen の音源生成実装正本です。NumPy と SciPy のみに依存する単一ファイルで、別プロジェクトへコピーして利用できます。

## 最短コマンド

```bash
python tools/sound/sfx_generator.py --preset coin --play
python tools/sound/sfx_generator.py --list-presets
```

## 詳細ドキュメント

人間向けの操作説明は [docs/audio/](../../docs/audio/README.md) が正本です。

- [クイックスタート](../../docs/quickstart.md)
- [効果音（SFX）](../../docs/audio/sfx.md)
- [BGMと楽譜](../../docs/audio/bgm-and-scores.md)
- [出力とゲーム統合](../../docs/audio/output-and-game-integration.md)

LLM エージェント向け手順は [audio-generation スキル](../../.rulesync/skills/audio-generation/SKILL.md) が正本です。

## 別プロジェクトへの持ち込み

```bash
cp tools/sound/sfx_generator.py /path/to/game/tools/sound/sfx_generator.py
```

`numpy>=2.0` と `scipy>=1.11` を依存に追加し、`--list-presets` で動作を確認してください。
