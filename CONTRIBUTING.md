# このリポジトリに手を入れるときの約束

## ⚠️ ノートブックの出力は commit しない

このリポジトリは公開されています。ノートブックの**実行結果セルには実データが
そのまま残る**ため、commit する前に必ず出力をクリアしてください。

- Databricks 上で編集した場合: エクスポート前に `Clear` → `Clear all cell outputs`
- ローカルの `.py` 形式（`# Databricks notebook source`）で編集する場合: 出力は含まれません

## ⚠️ サンプルデータは手で編集しない

`data/` 配下の CSV は `src/setup/generate_sample_data.py` が生成したものです。
内容を変えたいときは **仕様ファイル `src/setup/item_master_spec.yaml` を編集して
再生成**してください。

```bash
uv run src/setup/generate_sample_data.py
git diff --stat data/          # 意図した差分だけになっているか確認する
```

CSV を直接編集すると、再生成したときに差分が出て再現性が壊れます。

## ✅ 公開前チェック

```bash
bash scripts/check_publish.sh
```

すべて 0 件になっていることを確認してください。
