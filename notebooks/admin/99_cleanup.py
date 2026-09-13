# Databricks notebook source
# MAGIC %md
# MAGIC # 管理者向け — 後片付け
# MAGIC
# MAGIC > 🧑‍💼 **管理者用です。** ⚠️⚠️ **実行すると参加者が作ったものが消えます。**
# MAGIC
# MAGIC ハンズオンが終わった後、または検証をやり直したいときに使います。
# MAGIC
# MAGIC ## 消えるもの
# MAGIC
# MAGIC | 対象 | 内容 |
# MAGIC |---|---|
# MAGIC | 参加者のスキーマ | `fc_ws_*` とその中のテーブル・モデルすべて |
# MAGIC | 参加者のパイプライン | `[handson] * のメダリオンパイプライン` |
# MAGIC
# MAGIC ## 消えないもの（別途）
# MAGIC
# MAGIC | 対象 | 消し方 |
# MAGIC |---|---|
# MAGIC | 共有スキーマ / 見本 / Volume / ジョブ | `databricks bundle destroy -t dev` |
# MAGIC | カタログ | 手動で `DROP CATALOG`（意図せず消さないため自動化しません） |
# MAGIC | 参加者が作ったダッシュボード / Genie Agent | 画面から個別に削除 |

# COMMAND ----------

dbutils.widgets.text("catalog", "demand_forecast_handson", "カタログ")
dbutils.widgets.dropdown("dry_run", "true", ["true", "false"], "確認だけ (true) / 実行 (false)")

catalog = dbutils.widgets.get("catalog")
dry_run = dbutils.widgets.get("dry_run") == "true"

print(f"カタログ: {catalog}")
print("モード  : " + ("確認だけ（何も消しません）" if dry_run else "⚠️⚠️ 実際に削除します"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. 参加者のスキーマ

# COMMAND ----------

schemas = [
    r["databaseName"] if "databaseName" in r.asDict() else r[0]
    for r in spark.sql(f"SHOW SCHEMAS IN {catalog}").collect()
]
targets = [s for s in schemas if s.startswith("fc_ws_")]

print(f"対象のスキーマ: {len(targets)} 件")
for s in targets:
    print(f"  {catalog}.{s}")

if not dry_run:
    for s in targets:
        spark.sql(f"DROP SCHEMA IF EXISTS {catalog}.{s} CASCADE")
        print(f"  🗑 削除しました: {catalog}.{s}")
elif targets:
    print("\n（確認モードです。実際に消すには dry_run を false にしてください）")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. 参加者のパイプライン

# COMMAND ----------

from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
api = w.api_client

listed = api.do("GET", "/api/2.0/pipelines", query={"max_results": 100}) or {}
pipes = [
    p for p in (listed.get("statuses") or [])
    if "のメダリオンパイプライン" in (p.get("name") or "")
]

print(f"対象のパイプライン: {len(pipes)} 件")
for p in pipes:
    print(f"  {p.get('name')}  ({p.get('pipeline_id')})")

if not dry_run:
    for p in pipes:
        api.do("DELETE", f"/api/2.0/pipelines/{p['pipeline_id']}")
        print(f"  🗑 削除しました: {p.get('name')}")
elif pipes:
    print("\n（確認モードです。実際に消すには dry_run を false にしてください）")

# COMMAND ----------

# MAGIC %md
# MAGIC ## ✅ 残りの後片付け
# MAGIC
# MAGIC ```bash
# MAGIC # 共有スキーマ・見本・Volume・パイプライン・ジョブを消す
# MAGIC databricks bundle destroy -t dev -p <profile>
# MAGIC ```
# MAGIC
# MAGIC ⚠️ カタログ自体は意図せず消さないよう、手動で消してください。
# MAGIC
# MAGIC ```sql
# MAGIC DROP CATALOG IF EXISTS demand_forecast_handson CASCADE;
# MAGIC ```
