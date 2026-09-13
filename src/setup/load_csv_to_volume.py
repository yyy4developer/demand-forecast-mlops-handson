# Databricks notebook source
# MAGIC %md
# MAGIC # サンプルデータを Volume に投入する（管理者向け）
# MAGIC
# MAGIC > 🔑 **必要な権限**: 対象 Volume への `WRITE VOLUME`
# MAGIC >
# MAGIC > 🧑‍💼 **これは管理者が事前に実行するノートブックです**。参加者は実行しません。
# MAGIC
# MAGIC repo に含まれている CSV を、Unity Catalog の Volume にコピーします。
# MAGIC CSV は `data/` 配下に **生成済みの状態で commit されている**ため、
# MAGIC 誰がいつ実行しても同じデータが入ります。
# MAGIC
# MAGIC ## 投入先のディレクトリ構成
# MAGIC
# MAGIC | ディレクトリ | 中身 |
# MAGIC |---|---|
# MAGIC | `shipments/` | 月次出荷実績 ← ⭐ **当日ここに新しい CSV を置くとパイプラインが取り込む** |
# MAGIC | `items/` | 品目マスタ |
# MAGIC | `channels/` | チャネル定義 |
# MAGIC | `inventory/` | 月末在庫・安全在庫・欠品フラグ |
# MAGIC | `lead_time/` | 品目 × 拠点の標準リードタイム |
# MAGIC | `forecast_baseline/` | 前年同月ナイーブのベースライン予測 |
# MAGIC | `your_own_data/` | 参加者が自分のデータを置く場所（自由時間用・空で作る） |
# MAGIC
# MAGIC ## `load_set` パラメータ
# MAGIC
# MAGIC | 値 | 投入する出荷実績 | いつ使うか |
# MAGIC |---|---|---|
# MAGIC | `A` | 2020-01 〜 2026-07 | ⭐ **ハンズオン前**（既定） |
# MAGIC | `B` | 2026-08 のみ | ⭐ **ハンズオン当日**（「新しいデータが届いた」を再現する） |
# MAGIC | `all` | 両方 | 動作確認したいとき |
# MAGIC
# MAGIC > ⚠️ **同じ名前のファイルを上書きしても、ファイル到着トリガーは発火しません。**
# MAGIC > だから出荷実績を A / B の 2 本に分けています。当日は **新しいファイル名**で
# MAGIC > セット B が追加されるため、「新規ファイルが来た」として検知できます。

# COMMAND ----------

dbutils.widgets.text("bundle_file_path", "", "bundle のファイルパス")
dbutils.widgets.text("catalog", "demand_forecast_handson", "カタログ")
dbutils.widgets.text("schema", "fc_shared", "共有スキーマ")
dbutils.widgets.text("volume", "landing", "Volume 名")
dbutils.widgets.dropdown("load_set", "A", ["A", "B", "all"], "投入するセット")

bundle_file_path = dbutils.widgets.get("bundle_file_path")
catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
volume = dbutils.widgets.get("volume")
load_set = dbutils.widgets.get("load_set")

# COMMAND ----------

import os
import shutil

if bundle_file_path:
    # ジョブ実行時: bundle が同期したファイルパスが渡される
    source_root = os.path.join(bundle_file_path, "data")
else:
    # ノートブックを直接開いて実行した場合: このノートブックの 2 階層上が repo ルート
    here = os.path.dirname(
        dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
    )
    source_root = os.path.join("/Workspace", here.lstrip("/"), "..", "..", "data")

source_root = os.path.normpath(source_root)
volume_root = f"/Volumes/{catalog}/{schema}/{volume}"

print(f"コピー元 : {source_root}")
print(f"コピー先 : {volume_root}")
assert os.path.isdir(source_root), f"コピー元が見つかりません: {source_root}"

# COMMAND ----------

# MAGIC %md
# MAGIC ## ファイルの割り当て
# MAGIC
# MAGIC ⚠️ `_generation_report.csv` は「目標値と実測値の対比」であってデータではないため、
# MAGIC Volume には入れません（パイプラインが誤って取り込まないようにするため）。

# COMMAND ----------

# (コピー元ファイル名, 投入先サブディレクトリ, どのセットに属するか)
FILE_MAP = [
    ("shipments_2020_2026_07.csv", "shipments", "A"),
    ("shipments_2026_08.csv", "shipments", "B"),
    ("dim_item.csv", "items", "A"),
    ("dim_channel.csv", "channels", "A"),
    ("fct_inventory.csv", "inventory", "A"),
    ("dim_lead_time.csv", "lead_time", "A"),
    ("fct_forecast_baseline.csv", "forecast_baseline", "A"),
]

# 参加者が自分のデータを置く場所は空のまま作る
EMPTY_DIRS = ["your_own_data"]

wanted = {"A", "B"} if load_set == "all" else {load_set}

# COMMAND ----------

# ⚠️ Volume 配下のディレクトリ作成は `os.makedirs` ではなく `dbutils.fs.mkdirs` を使う。
#    `os.makedirs` は親ディレクトリを順に作ろうとするため、Volume より上の階層
#    (/Volumes/<catalog>/<schema>) に到達して "Operation not supported" で失敗する。
for sub in sorted({sub for _, sub, _ in FILE_MAP} | set(EMPTY_DIRS)):
    dbutils.fs.mkdirs(f"{volume_root}/{sub}")

copied, skipped = [], []
for filename, sub, belongs_to in FILE_MAP:
    if belongs_to not in wanted:
        skipped.append(filename)
        continue
    src = os.path.join(source_root, filename)
    dst = f"{volume_root}/{sub}/{filename}"
    shutil.copyfile(src, dst)
    copied.append(f"{sub}/{filename} ({os.path.getsize(src):,} bytes)")

print(f"=== 投入セット: {load_set} ===")
print("\n[コピーしました]")
for c in copied:
    print(f"  ✅ {c}")
if skipped:
    print("\n[今回は対象外]")
    for s in skipped:
        print(f"  ⏭  {s}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 投入結果の確認

# COMMAND ----------

for sub in sorted({sub for _, sub, _ in FILE_MAP} | set(EMPTY_DIRS)):
    entries = sorted(os.listdir(f"{volume_root}/{sub}"))
    label = ", ".join(entries) if entries else "(空)"
    print(f"  {sub + '/':<20} {label}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 次のステップ
# MAGIC
# MAGIC 1. **パイプラインを実行する** — `[handson] 02 メダリオンパイプライン` を Run すると
# MAGIC    bronze → silver → gold のテーブルが作られます
# MAGIC 2. **UC メタデータを適用する** — `src/setup/apply_uc_metadata.py` を実行して
# MAGIC    コメント・主キー・メトリクスビューを付けます
# MAGIC    （⚠️ これを飛ばすと Genie Agent の回答精度が出ません）
