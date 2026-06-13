# dna_kernel 詳細

dna_kernel は、LLM ハーネス（Claude Code 等）を使う創作・執筆・開発プロジェクトに、
**ルールが肥大化せず、完了条件が曖昧にならず、再現可能に発展する**仕組みを組み込むための最小セットです。

ルート `README.md` は導入先プロジェクトのものとして扱います。
dna_kernel 自体の詳しい説明は、この `docs/dna-kernel/` 配下へ置きます。

## なぜ必要か

LLM への指示は「書き足す」ほど矛盾が増え、「完了した」は言葉で言うだけでは根拠になりません。
このカーネルは、その2つの問題を構造で解決します。

- **ルールの一本化**: 概念の正本を1か所に置き、他の指示は「それを参照する」形にする
- **完了の拘束**: ファイルへの書き込みと機械確認を済ませるまで「完了」と言わせない
- **追記だけの履歴**: 査証ログは上書き禁止にし、作業事実を改ざんさせない

## このカーネルに含まれるもの

```text
dna_kernel/
  README.md                  ← 短い入口
  manifest.md                ← 各ファイルの役割と移植先での置き場
  rulesync.jsonc             ← rulesync 設定（targets・features）
  .rulesync/
    rules/                   ← 概念・運用ルールの正本
    skills/                  ← LLM 向けの実行手順
  docs/
    dna-kernel/
      README.md              ← この詳細説明
      onboarding.md          ← 新規導入・既存注入フロー
      self-evolving-governance.md
  tools/
    README.md
    kernel/
      workspace_audit_log.py
      json_weighted_pick.py
```

## README の扱い

導入先プロジェクトでは、ルート `README.md` をプロジェクト自身の紹介・使い方のために残します。
dna_kernel の説明は `docs/dna-kernel/` 配下へ置き、既存プロジェクトの README を勝手に移動・上書きしません。

新規プロジェクトで README がない場合だけ、作成するか確認します。

## よく使うコマンド

初回セットアップ:

```bash
uv run python init.py
```

ルール再生成:

```bash
npx rulesync generate --dry-run
npx rulesync generate
```

査証ログ追記:

```bash
uv run python tools/kernel/workspace_audit_log.py append "作業内容"
```

## 詳細

- 導入・注入フロー: [onboarding.md](onboarding.md)
- ガバナンスの考え方: [self-evolving-governance.md](self-evolving-governance.md)
- ファイル一覧: [../../manifest.md](../../manifest.md)
