# tools（dna_kernel）

自己発展型ルールガバナンスを「実働」させるためのツールです。
`kernel/` にコアツールを収め、`sound/` に OnGen 音源生成ツールを配置しています。

## コア（どのプロジェクトにも移植できる）

プロジェクトの種類に関わらず使えるツールです。

- **追記ログ（auditability）**
  - `kernel/workspace_audit_log.py`
  - 追記先: `_workingspace/log/YYYYMM.md`, `_workingspace/diary/YYYYMM.md`
  - 依存: なし（標準ライブラリのみ）
- **ドキュメントリンク検証**
  - `kernel/verify_doc_links.py`
  - 依存: なし（標準ライブラリのみ）
- **重み付き乱数選択（weighted-pick）**
  - `kernel/json_weighted_pick.py`
  - 依存: なし（標準ライブラリのみ）

## OnGen project tool

- `sound/sfx_generator.py` - 音源生成実装の正本。単体で別プロジェクトへ移植できる
  - 依存: NumPy、SciPy
  - 人間向け説明: `sound/README.md`
  - Rulesyncスキル: `.rulesync/skills/audio-generation/SKILL.md`

`kernel/workspace_audit_log.py` と `kernel/json_weighted_pick.py` は標準ライブラリだけで単独動作します。
