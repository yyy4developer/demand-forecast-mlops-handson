# Databricks notebook source
# MAGIC %md
# MAGIC # 03 — SQL 1 文で予測する（`ai_forecast`）
# MAGIC
# MAGIC > ⏱ **目安 5 分**
# MAGIC
# MAGIC 前のパートで、Genie Agent は「**過去**に何が起きたか」には答えられるけれど
# MAGIC 「**来月どうなるか**」には答えられませんでした。
# MAGIC
# MAGIC ⭐ ここでは **SQL 1 文だけ**で 18 か月先まで予測してみます。
# MAGIC モデルの学習も、ライブラリのインストールも要りません。
# MAGIC
# MAGIC ## ⚠️ 動かす場所に注意
# MAGIC
# MAGIC `ai_forecast` は **SQL ウェアハウス（Pro または Serverless）でしか動きません。**
# MAGIC ノートブックの計算資源から実行すると、こう言われます。
# MAGIC
# MAGIC ```
# MAGIC [UNSUPPORTED_FEATURE.AI_FUNCTION_PREVIEW]
# MAGIC AI function ai_forecast is in preview and currently disabled in this environment
# MAGIC ```
# MAGIC
# MAGIC ⭐ そこでこのノートブックでは、**SQL ウェアハウスにクエリを投げて**実行します。
# MAGIC （SQL エディタに貼って実行しても同じです。むしろそちらが本来の使い方です。）
# MAGIC
# MAGIC ## ⚠️ そして、これで終わりではありません
# MAGIC
# MAGIC | できること | ⚠️ できないこと |
# MAGIC |---|---|
# MAGIC | SQL 1 文で全品目を一括予測 | **どの手法が使われたか**は分からない |
# MAGIC | 予測区間つきで返ってくる | **品目ごとに手法を選ぶ**ことはできない |
# MAGIC | すぐ試せる | **前回より良くなったか**を記録できない |
# MAGIC | | **毎月自動で回して結果を残す**仕組みがない |
# MAGIC
# MAGIC ⭐ **「1 回試す」なら十分。でも「毎月回して改善し続ける」には足りない。**
# MAGIC その足りない部分を埋めるのが次のパート（MLflow / Unity Catalog / Jobs）です。

# COMMAND ----------

# MAGIC %run ./_config

# COMMAND ----------

# MAGIC %md
# MAGIC ## 引数でつまずきやすい 2 点
# MAGIC
# MAGIC | 引数 | ⚠️ 間違えやすいところ |
# MAGIC |---|---|
# MAGIC | `horizon` | **「何期先」ではなく「いつまで」** を日付で渡します（`18` ではなく `'2028-01-31'`） |
# MAGIC | `frequency` | 月次は **`'ME'`**（Month End = 月末）。`'M'` ではありません |
# MAGIC
# MAGIC ⭐ `group_col` に系列を識別する列を渡すと、**グループごとに別々の予測**になります。
# MAGIC ここでは品目とチャネルを繋いだキーを作って渡します。

# COMMAND ----------

row = spark.sql(f"""
    SELECT MAX(ym) AS last_ym, LAST_DAY(ADD_MONTHS(MAX(ym), 18)) AS horizon_ym
    FROM {MY}.fct_shipments
""").collect()[0]

LAST_YM, HORIZON_YM = str(row["last_ym"]), str(row["horizon_ym"])
print(f"実績の最終月 : {LAST_YM}")
print(f"予測の終端   : {HORIZON_YM}  ← horizon にこれを渡します（18 か月先）")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 実行する SQL
# MAGIC
# MAGIC ⭐ 下のセルで、これから実行する SQL がそのまま表示されます。
# MAGIC **SQL エディタに貼って実行しても同じ結果になります**ので、試してみてください。

# COMMAND ----------

AI_FORECAST_SQL = f"""
CREATE OR REPLACE TABLE {MY}.fct_forecast_ai AS
SELECT
  SPLIT(series_id, '\\\\|')[0] AS item_code,
  SPLIT(series_id, '\\\\|')[1] AS channel,
  ym                          AS target_ym,
  'ai_forecast'               AS model_name,
  qty_forecast                AS p50,
  qty_lower                   AS lower_bound,
  qty_upper                   AS upper_bound
FROM AI_FORECAST(
  TABLE(
    SELECT
      CONCAT(item_code, '|', channel) AS series_id,
      ym,
      CAST(qty AS DOUBLE)             AS qty
    FROM {MY}.fct_shipments
  ),
  horizon   => '{HORIZON_YM}',
  time_col  => 'ym',
  value_col => 'qty',
  group_col => 'series_id',
  frequency => 'ME'
)
"""

print(AI_FORECAST_SQL)

# COMMAND ----------

# MAGIC %md
# MAGIC ## SQL ウェアハウスに投げて実行する

# COMMAND ----------

import time

from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
api = w.api_client

assert WAREHOUSE_ID, "SQL ウェアハウスが見つかりませんでした。講師に確認してください。"


def run_on_warehouse(statement: str, wait: str = "50s") -> dict:
    """SQL ウェアハウス上でクエリを実行し、終わるまで待つ。"""
    res = api.do(
        "POST",
        "/api/2.0/sql/statements",
        body={"warehouse_id": WAREHOUSE_ID, "statement": statement, "wait_timeout": wait},
    )
    statement_id = res.get("statement_id")
    state = (res.get("status") or {}).get("state")
    # 50 秒で終わらなければ、終わるまでポーリングする
    while state in ("PENDING", "RUNNING"):
        time.sleep(5)
        res = api.do("GET", f"/api/2.0/sql/statements/{statement_id}")
        state = (res.get("status") or {}).get("state")
    if state != "SUCCEEDED":
        raise RuntimeError(f"SQL が {state} で終了しました: {(res.get('status') or {}).get('error')}")
    return res


run_on_warehouse(AI_FORECAST_SQL, wait="50s")
n = spark.table(f"{MY}.fct_forecast_ai").count()
print(f"✅ {MY}.fct_forecast_ai に {n:,} 行の予測を書き出しました")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 結果を見る
# MAGIC
# MAGIC ⭐ **品目ごとに違う動きを予測している**ことに注目してください。
# MAGIC 「全品目まとめて 1 つの傾向」ではありません。

# COMMAND ----------

# MAGIC %sql
# MAGIC SELECT
# MAGIC   item_code,
# MAGIC   channel,
# MAGIC   ROUND(AVG(p50), 1)         AS `avg_forecast_qty`,
# MAGIC   ROUND(MIN(lower_bound), 1) AS `min_lower`,
# MAGIC   ROUND(MAX(upper_bound), 1) AS `max_upper`,
# MAGIC   COUNT(*)                   AS `months`
# MAGIC FROM fct_forecast_ai
# MAGIC GROUP BY item_code, channel
# MAGIC ORDER BY `avg_forecast_qty` DESC
# MAGIC LIMIT 15

# COMMAND ----------

# MAGIC %md
# MAGIC ### ⚠️ 予測区間の広さを見てください
# MAGIC
# MAGIC ⭐ 出ない月がある品目（`intermittent` / `lumpy`）は、区間が数量に対して極端に広くなります。
# MAGIC ⚠️ 「予測値が 1 個、でも 0〜5 個の間」というのは、**実務では判断材料になりません**。
# MAGIC こういう品目は、精度を上げるより「**安全在庫を厚めに持つ**」方が正解の場合もあります。

# COMMAND ----------

# MAGIC %sql
# MAGIC SELECT
# MAGIC   i.demand_class                                        AS `需要分類`,
# MAGIC   ROUND(AVG(f.p50), 1)                                  AS `avg_forecast`,
# MAGIC   ROUND(AVG(f.upper_bound - f.lower_bound), 1)          AS `interval_width`,
# MAGIC   ROUND(AVG((f.upper_bound - f.lower_bound)
# MAGIC             / NULLIF(f.p50, 0)), 1)                     AS `width_per_forecast`
# MAGIC FROM fct_forecast_ai f
# MAGIC JOIN dim_item i USING (item_code)
# MAGIC GROUP BY i.demand_class
# MAGIC ORDER BY `width_per_forecast` DESC

# COMMAND ----------

# MAGIC %md
# MAGIC ## ✅ ここまでできたら
# MAGIC
# MAGIC 次は **`04_train_register`** に進みます。
# MAGIC
# MAGIC ⭐ ここまでで「予測は簡単に出せる」ことは分かりました。
# MAGIC ⚠️ でも今の状態には、実務で困ることが残っています。
# MAGIC
# MAGIC 1. どの手法で予測したのか **記録が残っていない**
# MAGIC 2. **前年同月ナイーブより良いのか**を確かめていない
# MAGIC 3. 来月また同じことを **手で繰り返す**しかない
# MAGIC
# MAGIC ⭐ 次のパートからは、この 3 つを仕組みで解決していきます。
