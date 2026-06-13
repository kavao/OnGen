# スキル索引

OnGen プロジェクトでは、LLM エージェント向けの作業手順を `.rulesync/skills/` に正本として置き、Rulesync で各ツール向けに生成します。

## このドキュメントを使う場面

- プロジェクト内にどんなスキルがあるか把握したいとき
- 外部からスキルを取り込む前に判断基準を確認したいとき
- 人間向けの操作説明とスキルの役割分担を理解したいとき

## 主なスキル

| スキル | 用途 |
|--------|------|
| `audio-generation` | 効果音・BGM の生成 |
| `code-testing` | コード変更後のテスト実行 |
| `workspace-audit-log` | 査証ログへの追記 |
| `backup-before-edit` | 上書き前の旧版退避 |
| `approval-flow` | 課金・外部 API・不可逆操作の承認 |

正本は `.rulesync/skills/<name>/SKILL.md` です。生成物（`.claude/`、`.cursor/`、`.agents/` 等）は直接編集しないでください。

## 人間向けガイドとの関係

| 内容 | 人間向け | LLM向け |
|------|---------|--------|
| 音源の操作例 | [docs/audio/](../audio/README.md) | `audio-generation` スキル |
| テスト手順 | [テストと検証](../development/testing.md) | `code-testing` スキル |
| 外部スキル取り込み | [外部スキルの取り込み](importing-external-skills.md) | — |

外部スキルを評価・導入するときは [外部スキルの取り込み](importing-external-skills.md) を参照してください。
