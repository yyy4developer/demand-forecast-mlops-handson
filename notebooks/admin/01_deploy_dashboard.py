# Databricks notebook source
# MAGIC %md
# MAGIC # 管理者向け — 見本ダッシュボードを作る
# MAGIC
# MAGIC > 🧑‍💼 **管理者が事前に 1 回実行するノートブックです。** 参加者は実行しません。
# MAGIC
# MAGIC ## なぜノートブックで作るのか
# MAGIC
# MAGIC ダッシュボードは **SQL ウェアハウスの ID** を必要としますが、この ID は
# MAGIC ワークスペースごとに違います。
# MAGIC
# MAGIC ⚠️ bundle に書くと「デプロイのときに ID を渡す」必要が出てしまい、
# MAGIC **画面からのデプロイ（Databricks CLI なし）ができなくなります。**
# MAGIC
# MAGIC ⭐ そこでダッシュボードだけは bundle から外し、
# MAGIC **このノートブックが実行時にウェアハウスを見つけて作る**形にしています。
# MAGIC ⭐ 結果として bundle は**変数を 1 つも渡さずにデプロイできます**。
# MAGIC
# MAGIC ## やること
# MAGIC
# MAGIC 1. SQL ウェアハウスを見つける
# MAGIC 2. `dashboards/demand_overview.lvdash.json` を読み、テーブル名にカタログとスキーマを補う
# MAGIC 3. ダッシュボードを作成（既にあれば更新）して公開する
# MAGIC
# MAGIC > ⭐ **名前に「見本」が入ります。** `01_dashboard` が参加者向けに
# MAGIC > その文字でダッシュボードを探すためです。

# COMMAND ----------

# MAGIC %run ../_config

# COMMAND ----------

dbutils.widgets.text("dashboard_title", "[handson] 見本 需要予測 概況ダッシュボード", "ダッシュボード名")
DASHBOARD_TITLE = dbutils.widgets.get("dashboard_title")

# ⭐ 見本スキーマに対して作ります（参加者は自分のスキーマで自分の分を作ります）
TARGET_SCHEMA = SAMPLE_SCHEMA

print(f"作成先スキーマ : {catalog}.{TARGET_SCHEMA}")
print(f"ダッシュボード名: {DASHBOARD_TITLE}")
assert WAREHOUSE_ID, "SQL ウェアハウスが見つかりませんでした。1 台作成してから再実行してください。"
print(f"SQL ウェアハウス: {WAREHOUSE_ID}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. 定義ファイルを読み、テーブル名を完全な名前に直す
# MAGIC
# MAGIC ⭐ 定義ファイルの中のクエリは **テーブル名だけ**（カタログ・スキーマなし）で
# MAGIC 書かれています。どのワークスペースでも使えるようにするためです。
# MAGIC ここでカタログとスキーマを補います。

# COMMAND ----------

import json
import os

_nb = dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(_nb), "..", ".."))
_prefix = "" if REPO_ROOT.startswith("/Workspace") else "/Workspace"
DASH_PATH = f"{_prefix}{REPO_ROOT}/dashboards/demand_overview.lvdash.json"

print(f"定義ファイル: {DASH_PATH}")
with open(DASH_PATH, encoding="utf-8") as f:
    dash = json.load(f)

# 定義ファイルが参照しているテーブル
TABLES = [
    "fct_shipments", "dim_item", "dim_channel", "dim_lead_time",
    "fct_inventory", "fct_forecast_baseline", "fct_forecast_accuracy",
    "mv_demand", "mv_forecast_accuracy",
]

fq = f"{catalog}.{TARGET_SCHEMA}"
replaced = 0
for ds in dash.get("datasets", []):
    lines = ds.get("queryLines") or []
    for i, line in enumerate(lines):
        for tbl in TABLES:
            # 「FROM <table> 」「JOIN <table> 」だけを置き換える（列名は触らない）
            for kw in ("FROM ", "JOIN "):
                needle = f"{kw}{tbl} "
                if needle in line:
                    lines[i] = lines[i].replace(needle, f"{kw}{fq}.{tbl} ")
                    replaced += 1
    ds["queryLines"] = lines

print(f"✅ テーブル参照を {replaced} 箇所、{fq} で修飾しました")
for ds in dash.get("datasets", []):
    print(f"  {ds['name']}: {''.join(ds['queryLines'])[:90]}…")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. 作成（既にあれば更新）して公開する
# MAGIC
# MAGIC ⭐ 同じ名前のダッシュボードがあれば**更新**します（何度実行しても安全です）。

# COMMAND ----------

from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
api = w.api_client
PARENT = f"/Workspace/Users/{spark.sql('SELECT current_user()').collect()[0][0]}"

listed = api.do("GET", "/api/2.0/lakeview/dashboards", query={"page_size": 200}) or {}
existing = [
    d for d in (listed.get("dashboards") or [])
    if d.get("display_name") == DASHBOARD_TITLE and d.get("lifecycle_state") != "TRASHED"
]

body = {
    "display_name": DASHBOARD_TITLE,
    "warehouse_id": WAREHOUSE_ID,
    "serialized_dashboard": json.dumps(dash, ensure_ascii=False),
}

if existing:
    dashboard_id = existing[0]["dashboard_id"]
    api.do("PATCH", f"/api/2.0/lakeview/dashboards/{dashboard_id}", body=body)
    print(f"✅ 既存のダッシュボードを更新しました: {dashboard_id}")
else:
    body["parent_path"] = PARENT
    created = api.do("POST", "/api/2.0/lakeview/dashboards", body=body)
    dashboard_id = created["dashboard_id"]
    print(f"✅ ダッシュボードを作成しました: {dashboard_id}")

api.do("POST", f"/api/2.0/lakeview/dashboards/{dashboard_id}/published",
       body={"warehouse_id": WAREHOUSE_ID})
print("✅ 公開しました")

displayHTML(
    f'<a href="{w.config.host}/dashboardsv3/{dashboard_id}/published" target="_blank">'
    "▶ 見本ダッシュボードを開く</a>"
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. 参加者に見せられる状態か確認する
# MAGIC
# MAGIC ⚠️ 参加者グループに **`CAN VIEW`** を付けてください（画面の「共有」から）。
# MAGIC ⚠️ ダッシュボードは**開いた人の権限**でクエリを実行します。
# MAGIC 参加者が見本スキーマを読めないと、開いてもエラーになります。
# MAGIC （`admin/00_prepare_environment` の GRANT で付与済みのはずです）

# COMMAND ----------

for ds in dash.get("datasets", []):
    sql = "".join(ds["queryLines"])
    try:
        n = spark.sql(f"SELECT COUNT(*) FROM ({sql})").collect()[0][0]
        print(f"  ✅ {ds['name']:<16} {n:>8,} 行")
    except Exception as e:  # noqa: BLE001
        print(f"  ❌ {ds['name']:<16} {type(e).__name__}: {str(e).splitlines()[0][:100]}")
