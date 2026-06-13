---
name: workspace-audit-log
description: >-
  _workingspace/log/YYYYMM.md 査証ログを tools/kernel/workspace_audit_log.py で追記専用運用する。
  既存行の上書き・削除は行わない。
targets: ["*"]
---

## 目的

作業の事実を **`_workingspace/log/YYYYMM.md` にのみ追記**し、履歴を機械的に保証する。

- **追記型のみ**: 新規エントリは `workspace_audit_log.py append` で追加する。スクリプトは `open(..., "a")` 以外でログ本文を書かない。
- **ファイル命名**: 西暦4桁＋月2桁、`202604.md` のように **ゼロ埋め2桁の月**。
- **エントリの1行形式**:  
  `- YYYY-MM-DD HH:MM: 本文`  
  本文に改行を含めない（複数行貼り付けは空白で連結）。

## いつ追記するか

セッションごとに、更新したファイル・実施した作業・次にすべきことを1エントリにまとめる。

## 何を記録するか

| 記録すべき内容 | 例 |
|--------------|-----|
| 重要な実装パス | どのファイルをどう変えたか |
| ユーザーの好み・ワークフロー上の決定 | 「毎回○○を先にやる」 |
| プロジェクト固有のパターン | 命名規則、採番ルール等 |
| 既知の課題 | 未解決の問題と経緯 |
| 次に望ましい作業 | 継続タスクの引き継ぎ |

## 実行方法

**1件追記**:

```bash
python tools/kernel/workspace_audit_log.py append "関連ファイルを更新。次は…が望ましい。"
```

**標準入力から**（長文に便利）:

```bash
echo "本文" | python tools/kernel/workspace_audit_log.py append
```

**追記先の月を指定**:

```bash
python tools/kernel/workspace_audit_log.py append --year-month 202604 "本文"
```

**エントリの日時を指定**:

```bash
python tools/kernel/workspace_audit_log.py append --at "2026-04-11 15:30" "本文"
```

**今月のログファイルのパスを確認**:

```bash
python tools/kernel/workspace_audit_log.py path
```

**体裁チェック**（読み取り専用）:

```bash
python tools/kernel/workspace_audit_log.py verify
python tools/kernel/workspace_audit_log.py verify --strict
```

**dry-run**（書き込まずに確認）:

```bash
python tools/kernel/workspace_audit_log.py append --dry-run "本文"
```

## 禁止

- 既存行の削除・並べ替え・中間挿入・全文置換を行わない。
- 誤記の訂正は訂正エントリを追記して理由を残す。
- エディタで直接追記するのは緊急時のみ（形式が崩れるリスクがある）。

## エージェント向け運用

- セッション終了前に `append` を1回実行する。
- 「査証ログを書いた」と言うだけで済ませず、実際にコマンドを実行する。

## 関連

- スクリプト: `tools/kernel/workspace_audit_log.py`
- 保存先: `_workingspace/log/YYYYMM.md`
- 概念正本: `rules/concepts.md`（査証ログの原則）
- 姉妹スキル: `workspace-diary`（`_workingspace/diary/`）
