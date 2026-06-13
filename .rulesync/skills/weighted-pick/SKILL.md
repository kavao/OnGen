---
name: weighted-pick
description: >-
  JSON リストから tools/kernel/json_weighted_pick.py で均等または確率フィールドに基づき乱数選択する。
  LLM のあいまい抽選に頼らず Python で再現可能にする。
targets: ["*"]
---

## 目的

企画・分類・候補リストなど、**JSON に定義した候補から1件（または複数回）選ぶ**ときに、
**必ず `json_weighted_pick.py` を実行**し、結果を正とする。
推測や会話上の「だいたいの確率」だけで選ばない。

## 動作の定義

- **対象**: UTF-8 の JSON ファイル、または `--eval` で渡した JSON 文字列、または標準入力（`-`）。
- **パス（階層）**: `--path`（`-p`）に **ドット区切り**で辞書キーを辿る。末端が配列になっているノードで抽選する。
- **末端が文字列・数値の混在配列**: **均等**に1件（`mode: uniform`）。
- **末端がオブジェクトの配列**: 各要素から重みキーを読む。全要素に重みがあれば**重み付き**（`mode: weighted`）。一部のみ・解釈不能なら**均等フォールバック**（`mode: uniform_fallback`）。
- **末端がオブジェクト**: キー名を均等に1つ選ぶ（`mode: uniform_dict_keys`）。
- **再現性**: `--seed 整数` を付けると同じコマンドで毎回同じ結果になる。毎回ばらつかせたいときは `--seed` を付けない。
- **複数回（`-n`）**: 同一の乱数生成器で連続抽選する。

重みとして認識するキー名（先頭から試行）:  
`確率`, `相対確率`, `weight`, `Weight`, `重み`, `prob`, `probability`, `ウェイト`  
文字列 `"30%"` や `"30"` も可。合計は 100 でなくてもよい（正規化される）。

## 実行例

**文字列配列から均等に1件**:

```bash
python tools/kernel/json_weighted_pick.py candidates.json -p options --seed 42 --json
```

**重み付きオブジェクト配列から1件**:

```bash
python tools/kernel/json_weighted_pick.py data.json -p items --json
```

**JSON を直接渡す**:

```bash
python tools/kernel/json_weighted_pick.py --eval '{"items":[{"name":"A","weight":40},{"name":"B","weight":60}]}' -p items --json
```

**標準入力から**:

```bash
type data.json | python tools/kernel/json_weighted_pick.py - -p some.path
```

**複数回抽選**:

```bash
python tools/kernel/json_weighted_pick.py data.json -p items -n 5 --json
```

**多段抽選（例: カテゴリ → 詳細）**:  
コマンドを段階ごとに実行し、2回目以降の `--path` を前回の結果に合わせて組み立てる（自動チェーンはしない）。

## JSON の設計指針

候補リストを JSON で設計するときは次を意識する。

- 均等に選びたい → 文字列配列 `["A", "B", "C"]`
- 重み付きで選びたい → オブジェクト配列に `weight`（または `確率`）を付ける
- 階層で絞りたい → 辞書のネストにしてパスで指定する

## エージェント向け運用

- 「ランダムに選ぶ」「確率に従う」指示が出たら、スクリプトの出力（`picked` と `mode`）をチャットに引用する。
- 階層 JSON では、該当する配列まで `--path` で明示してから実行する（パス誤りは `KeyError` で分かる）。

## 関連

- スクリプト: `tools/kernel/json_weighted_pick.py`
