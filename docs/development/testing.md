# テストと検証

このガイドを読むと、OnGen の回帰テストの実行、可搬性の確認、コード変更後の検証手順が分かります。

## 全テストの実行

```bash
python -m unittest discover -s tests -v
```

終了コード 0 を確認してください。`tools/sound/sfx_generator.py` を変更した場合は必ず実行します。

## テストの種類

| テストファイル | 内容 |
|---------------|------|
| `tests/test_sfx_generator.py` | 正本実装の音程・音長・音色の回帰 |
| `tests/test_sfx_generator_portability.py` | 単一ファイルのコピー先での起動確認 |

基準曲 `scores/tulip.abc` は音程と音長のベンチマークとしてテストに含まれています。

## 楽譜を変更したとき

- 音程・音価を固定する回帰テストを追加または更新してください。
- 全テストを実行し、終了コード 0 を確認してください。

## 文書内コマンドの確認

README や docs の代表コマンドを実行して、CLI 仕様と一致することを確認します。

```bash
python tools/sound/sfx_generator.py --preset coin -o output/docs-check/coin
python tools/sound/sfx_generator.py --input-file scores/tulip.abc --format abc -o output/docs-check/tulip
```

## ドキュメントリンクの確認

```bash
python tools/kernel/verify_doc_links.py README.md docs
```

終了コード 0 で、参照先ファイルが存在することを確認できます。

## 関連

- MML 互換の詳細: [MMLリファレンス](../audio/mml-reference.md)
- LLM 向けテスト規律: `.rulesync/skills/code-testing/SKILL.md`
