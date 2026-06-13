# OnGen dna_kernel manifest

このファイルは、各ファイルの役割と、導入先プロジェクトへ移植・注入するときの推奨配置先を示します。

## .rulesync/rules/（概念・ガバナンスの正本）

rulesync が各 LLM ツールの設定ファイルへ変換します。

| ファイル | 役割 | 導入先での配置先 |
|----------|------|--------------------------|
| `.rulesync/rules/concepts.md` | 正本・副本・完了条件の概念定義 | `.rulesync/rules/concepts.md` |
| `.rulesync/rules/rule-authoring.md` | ルール追加時の分類・置き場の作法 | `.rulesync/rules/rule-authoring.md` |
| `.rulesync/rules/docs-writing.md` | docs/ ドキュメント記述ルール（`docs/**/*.md` に適用） | `.rulesync/rules/docs-writing.md` |
| `.rulesync/rules/git.md` | git コミットメッセージ・ブランチ運用ルール | `.rulesync/rules/git.md` |

## .rulesync/skills/（LLM 向けの実行手順）

rulesync が各 LLM ツールのスキル設定へ変換します。

| ファイル | 役割 | 導入先での配置先 |
|----------|------|--------------------------|
| `.rulesync/skills/workspace-audit-log/SKILL.md` | 査証ログ追記の手順 | `.rulesync/skills/workspace-audit-log/` |
| `.rulesync/skills/workspace-diary/SKILL.md` | 横断ナレッジ日記の手順 | `.rulesync/skills/workspace-diary/` |
| `.rulesync/skills/output-discipline/SKILL.md` | ファイル出力→確認→報告の完了規律 | `.rulesync/skills/output-discipline/` |
| `.rulesync/skills/pre-work-check/SKILL.md` | 作業前の必須確認パターン | `.rulesync/skills/pre-work-check/` |
| `.rulesync/skills/backup-before-edit/SKILL.md` | 上書き前の旧版退避パターン | `.rulesync/skills/backup-before-edit/` |
| `.rulesync/skills/approval-flow/SKILL.md` | dry-run→承認→実行→確認の承認フロー | `.rulesync/skills/approval-flow/` |
| `.rulesync/skills/weighted-pick/SKILL.md` | JSON 重み付き乱数選択の手順 | `.rulesync/skills/weighted-pick/` |
| `.rulesync/skills/project-context/SKILL.md` | プロジェクト文脈の要約・引き継ぎ | `.rulesync/skills/project-context/` |
| `.rulesync/skills/project-onboarding/SKILL.md` | 新規作成・既存注入と overview.md 作成フロー | `.rulesync/skills/project-onboarding/` |
| `.rulesync/skills/code-testing/SKILL.md` | コード変更時のテスト実行・デグレード防止 | `.rulesync/skills/code-testing/` |
| `.rulesync/skills/audio-generation/SKILL.md` | `sfx_generator.py` による効果音・BGM生成 | `.rulesync/skills/audio-generation/` |

## rulesync.jsonc（rulesync 設定）

| ファイル | 役割 | 導入先での配置先 |
|----------|------|--------------------------|
| `rulesync.jsonc` | targets・features の指定 | プロジェクトルート |
| `LICENSE` | OnGenのMITライセンス正本 | プロジェクトルート |

## docs/（人間向けの説明）

rulesync の管理外。人間が読む説明ドキュメント。

| ファイル | 役割 | 導入先での配置先（例） |
|----------|------|-------------------------------|
| `docs/dna-kernel/README.md` | dna_kernel の詳細説明 | `docs/dna-kernel/README.md` |
| `docs/dna-kernel/onboarding.md` | 新規導入・既存注入フロー | `docs/dna-kernel/onboarding.md` |
| `docs/dna-kernel/self-evolving-governance.md` | パターン全体の説明（なぜ・どう動くか） | `docs/dna-kernel/self-evolving-governance.md` |

## tools/kernel/（実働コード）

### コア（どのプロジェクトにも移植できる）

| ファイル | 役割 | 導入先での配置先（例） |
|----------|------|-------------------------------|
| `tools/kernel/workspace_audit_log.py` | 査証ログ・日記への追記書き込み | `tools/kernel/workspace_audit_log.py` |
| `tools/kernel/json_weighted_pick.py` | JSON リストからの重み付き乱数選択 | `tools/kernel/json_weighted_pick.py` |

## 最小セット（どれか1つから始めるなら）

- **ルールだけ**: `.rulesync/rules/concepts.md` + `rulesync.jsonc` + `corepack pnpm dlx rulesync generate` 実行
- **ログまで**: 上記に `tools/kernel/workspace_audit_log.py` を追加
- **音源生成まで**: 上記に `sfx_generator.py` と `.rulesync/skills/audio-generation/SKILL.md` を追加
