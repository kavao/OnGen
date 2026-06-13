# dna_kernel 導入・注入フロー

dna_kernel には、次の3つの作業モードがあります。

| モード | 用途 | README の扱い |
|--------|------|---------------|
| 新規プロジェクト作成モード | まだ概要や README がない場所へ立ち上げる | 作成するか確認してからプロジェクト用 README を作る |
| 既存プロジェクト注入モード | すでにあるプロジェクトへ dna_kernel を追加する | 既存 README は触らず、dna_kernel 説明は `docs/dna-kernel/` へ置く |
| DNA_KERNEL 開発モード | dna_kernel 本体を修正する | 導入質問を省略して直接修正する |

## 既存プロジェクト注入モード

既存プロジェクトでは、既存の構成を壊さないことを優先します。

ユーザーが注入先ディレクトリを明示した場合、そのディレクトリを注入先ルートとして扱います。
monorepo の上位ディレクトリや Git ルートへ自動的には広げません。

例:

```text
K:\共有\10_プログラム\node\grokbot_news\packages\discord-bot\
```

このパスを指定された場合、以下は `packages/discord-bot/` 配下へ置きます。

```text
.rulesync/
rulesync.jsonc
docs/dna-kernel/
tools/kernel/
_workingspace/
```

基本方針:

- 既存の `README.md` を上書きしない
- 既存の `.gitignore`, `pyproject.toml`, `tools/`, `docs/` は内容を確認してから追記する
- dna_kernel の詳しい説明は `docs/dna-kernel/` 配下へ置く
- `.rulesync/`, `rulesync.jsonc`, `tools/kernel/` を正本・実働ツールとして追加する
- rulesync 生成物（`.claude/`, `.cursor/`, `.codex/`, `.kilo/`, `.agent/`, `AGENTS.md`, `CLAUDE.md`）は ignore する

推奨フロー:

1. 既存の README・docs・tools・.rulesync・rulesync.jsonc の有無を確認する
2. 注入してよいか、変更予定を提示して了承を得る
3. `docs/dna-kernel/` に説明文書を置く
4. `.rulesync/` と `rulesync.jsonc` を追加または統合する
5. `tools/kernel/` に必要なツールを置く
6. `.gitignore` に rulesync 生成物と `_workingspace/` の扱いを追記する
7. `npx rulesync generate --dry-run` で生成内容を確認する
8. 了承後に `npx rulesync generate` を実行する
9. 必要なら `overview.md` を作るか確認し、プロジェクトの目的・成果物・制約を聞く

## 新規プロジェクト作成モード

新規プロジェクトでは、最初に `overview.md` の有無を確認します。
なければ作成するかを確認し、了承後に rulesync と uv の導入状況を確認します。

導入の基本コマンド:

```bash
npm install -g rulesync
uv run python init.py
npx rulesync generate --dry-run
npx rulesync generate
```

`npx rulesync` だけでは、現在の rulesync ではヘルプが表示されるだけです。
生成には `generate` サブコマンドを使います。

## .gitignore 例

```gitignore
# rulesync 生成物
# 正本は rulesync.jsonc と .rulesync/ に置き、各ツール向け生成物は除外する
.claude/
.cursor/
.codex/
.kilo/
.agent/
AGENTS.md
CLAUDE.md

# ワークスペース（ローカル作業ファイル）
_workingspace/**
!_workingspace/**/
!_workingspace/**/.gitkeep
_backup/
_old/
```
