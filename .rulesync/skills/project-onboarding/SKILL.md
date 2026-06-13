---
name: project-onboarding
description: "新規作成または既存注入で dna_kernel を導入し、overview.md と docs/dna-kernel/ を起点に支援スケルトンを立ち上げる"
targets: ["*"]
---

## 目的

新しいプロジェクトや既存プロジェクトで dna_kernel を使い始めるときに、最初の会話と初期化を迷わせない。
既存構成を壊さず、`overview.md` と `docs/dna-kernel/` を起点に rulesync・uv・ワークスペースを整える。

## 適用する場面

- ユーザーが新規プロジェクトへ dna_kernel を導入したいと言ったとき
- ユーザーが既存プロジェクトへ dna_kernel を注入したいと言ったとき
- ルールやスキルはあるが、プロジェクト概要がまだ見当たらないとき
- 「開発を進める際の支援スケルトン」を作る依頼を受けたとき

## 適用しない場面

- dna_kernel 本体を開発・修正しているとき
- ユーザーが明示的に「DNA_KERNEL 開発モード」と言ったとき
- 既存の `overview.md` があり、ユーザーが通常の作業を依頼しているとき

## 最初に判定すること

プロジェクトルートで次を確認する。

- `README.md`
- `overview.md`
- `docs/`
- `tools/`
- `.rulesync/`
- `rulesync.jsonc`
- `.gitignore`

判定:

- `README.md` や既存 docs/tools がある場合は **既存プロジェクト注入モード** として扱う。
- README も概要もなく、空に近い場合は **新規プロジェクト作成モード** として扱う。
- dna_kernel 本体を修正している場合は **DNA_KERNEL 開発モード** として扱う。

## README の扱い

- ルート `README.md` はプロジェクト自身の入口として扱う。
- dna_kernel の詳しい説明は `docs/dna-kernel/` 配下へ置く。
- 既存プロジェクトの README を確認なしに移動・上書きしない。
- README が存在しない新規プロジェクトでは、作成するかユーザーに確認する。

## 既存プロジェクト注入モード

既存プロジェクトでは、先に変更予定を提示して了承を得る。

### 注入先ルート

ユーザーが注入先ディレクトリを明示した場合、そのディレクトリを注入先ルートとして扱う。
monorepo の上位ディレクトリや Git ルートへ自動的に広げない。

配置先:

- `.rulesync/`
- `rulesync.jsonc`
- `docs/dna-kernel/`
- `tools/kernel/`
- `_workingspace/`

これらは、指定された注入先ルートの配下に置く。

提示する内容:

- 追加または統合するファイル: `.rulesync/`, `rulesync.jsonc`, `docs/dna-kernel/`, `tools/kernel/`
- 追記する可能性があるファイル: `.gitignore`, `pyproject.toml`
- 触らない方針: 既存 `README.md` は上書きしない

確認文の例:

```text
指定されたディレクトリを注入先ルートとして扱います。上位の monorepo ルートや Git ルートへは広げません。
README.md は触らず、dna_kernel の説明は docs/dna-kernel/ に追加します。
.rulesync/・rulesync.jsonc・tools/kernel/・_workingspace/・.gitignore の追加または統合を進めてよいですか？
```

了承後の流れ:

1. `docs/dna-kernel/` に説明文書を置く。
2. `.rulesync/` と `rulesync.jsonc` を追加または統合する。
3. `tools/kernel/` に必要なツールを置く。
4. `.gitignore` に rulesync 生成物と `_workingspace/` の扱いを追記する。
5. `npx rulesync generate --dry-run` を実行し、結果を提示する。
6. 了承後に `npx rulesync generate` を実行する。
7. 必要なら `overview.md` を作るか確認し、プロジェクト内容を聞く。

## 新規プロジェクト作成モード

### 1. overview.md の有無を確認する

プロジェクトルートで `overview.md` を探す。

存在する場合:

- 内容を読み、プロジェクトの目的・制約・現在地を短く要約する。
- 不足があれば、必要な最小限の質問だけを行う。

存在しない場合:

- `overview.md` を作成するかユーザーに確認する。
- 作成しないと言われた場合は、導入作業を止め、通常の依頼として扱う。

確認文の例:

```text
このプロジェクトには overview.md がまだありません。プロジェクト概要の正本として作成しますか？
```

### 2. rulesync と uv の導入状況を確認する

`overview.md` を作成する了承を得たら、次を確認する。

```bash
npx rulesync --version
uv --version
```

未導入または実行できないものがある場合は、導入案を提示してから明示了承を得る。

導入案の例:

```text
rulesync または uv が未導入です。初期化に必要なので、こちらで導入してよいですか？
実行予定:
- npm install -g rulesync
- uv の公式インストーラを実行
- uv run python init.py
- npx rulesync generate --dry-run
- npx rulesync generate
```

### 3. 了承後に自動導入する

ユーザーが明示的に了承したら実行する。

推奨順:

Windows PowerShell:

```powershell
npm install -g rulesync
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
uv run python init.py
npx rulesync generate --dry-run
npx rulesync generate
```

macOS / Linux:

```bash
npm install -g rulesync
curl -LsSf https://astral.sh/uv/install.sh | sh
uv run python init.py
npx rulesync generate --dry-run
npx rulesync generate
```

既に導入済みのコマンドは再導入しなくてよい。
uv インストール直後に `uv` が見つからない場合は、PATH 反映のために新しいシェルで再確認する。
実行後は、生成先と終了コードを確認してから次へ進む。

### 4. プロジェクト内容を聞く

導入・初期化が終わってから、どのようなプロジェクトかを聞く。
最初の質問は絞る。

質問例:

```text
このプロジェクトでは、何を作る・進める予定ですか？
分かる範囲で、目的、成果物、守りたい制約を教えてください。
```

必要に応じて追加で聞く項目:

- 成果物の種類
- 想定ユーザーまたは読者
- 使う技術・ツール
- 変更してはいけない制約
- 完了確認の方法

### 5. overview.md を作成する

回答をもとに、`overview.md` を作成する。
初期テンプレート:

```markdown
# Project Overview

## 目的

未定

## 成果物

未定

## 制約

未定

## 作業方針

- 正本を先に更新し、派生物は再生成する。
- ファイル保存と確認が終わるまで完了扱いにしない。

## 完了確認

未定
```

作成後は読み直して保存確認を行い、更新ファイルパスを報告する。

## DNA_KERNEL 開発モード

dna_kernel 本体を直していると判断できる場合は、このスキルの質問フローを使わない。

判断例:

- `.rulesync/` のルールやスキルを修正する依頼
- `README.md` や `manifest.md` の導入説明を直す依頼
- `docs/dna-kernel/` の説明を直す依頼
- `tools/kernel/` や `init.py` を修正する依頼

この場合は、既存ファイルを読んで直接修正し、必要に応じて `npx rulesync generate --dry-run` または `npx rulesync generate --check` で確認する。

## 関連

- 概念正本: `rules/concepts.md`（プロジェクト導入モード、DNA_KERNEL 開発モード）
- 承認フロー: `skills/approval-flow/SKILL.md`
- 出力規律: `skills/output-discipline/SKILL.md`
