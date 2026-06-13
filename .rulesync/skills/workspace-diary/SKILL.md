---
name: workspace-diary
description: >-
  _workingspace/diary/YYYYMM.md 横断ナレッジ日記を tools/kernel/workspace_audit_log.py diary で追記専用運用する。
  査証ログと同様に既存行の上書き・削除は行わない。
targets: ["*"]
---

## 目的

**次のセッションでも効かせたい**判断理由・好み・方針・学びを `_workingspace/diary/YYYYMM.md` にのみ追記する。

### 査証ログ（log/）との違い

| 査証ログ（log/） | 日記（diary/） |
|-----------------|--------------|
| 「何をしたか」の作業事実 | 「なぜそうしたか」の判断理由 |
| セッションごとに記録 | 再利用したいナレッジのとき |
| 事実ベース | 方針・好み・洞察ベース |

## いつ追記するか

- ルール変更・ツール方針・ユーザー好みの確定など、**次のセッションでも効かせたい**とき。
- 繰り返し説明しなくて済む洞察を残したいとき。
- 査証ログに書いた作業の補足として「背景だけ」残したいとき。

## 実行方法

**1件追記**:

```bash
python tools/kernel/workspace_audit_log.py diary append "○○の方針で固定した。理由は…"
```

**標準入力から**:

```bash
echo "本文" | python tools/kernel/workspace_audit_log.py diary append
```

**追記先の月を指定**:

```bash
python tools/kernel/workspace_audit_log.py diary append --year-month 202604 "本文"
```

**今月の日記ファイルのパスを確認**:

```bash
python tools/kernel/workspace_audit_log.py diary path
```

**体裁チェック**:

```bash
python tools/kernel/workspace_audit_log.py diary verify
```

**dry-run**（書き込まずに確認）:

```bash
python tools/kernel/workspace_audit_log.py diary append --dry-run "本文"
```

## 禁止

- 既存行の削除・並べ替え・中間挿入・全文置換を行わない。
- `tools/kernel/workspace_audit_log.py diary` を使わずファイルを全文上書きしない（LLM の誤動作で履歴が消えるリスク）。

## エージェント向け運用

- 査証ログ（`append`）と混同しない。作業の事実は査証ログ、再利用したい方針は日記。

## 関連

- スクリプト: `tools/kernel/workspace_audit_log.py`（`diary` サブコマンド）
- 保存先: `_workingspace/diary/YYYYMM.md`
- 概念正本: `rules/concepts.md`（査証ログの原則）
- 姉妹スキル: `workspace-audit-log`（`_workingspace/log/`）
