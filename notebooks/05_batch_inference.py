# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "5"
# ///
# MAGIC %md
# MAGIC # 05 — 登録したモデルでまとめて推論する
# MAGIC
# MAGIC > ⏱ **目安 8 分**
# MAGIC
# MAGIC ⭐ 前のパートで登録したモデルを、**名前とエイリアスで呼び出して**使います。
# MAGIC 「どのファイルのモデルだったか」を覚えておく必要はもうありません。
# MAGIC
# MAGIC ```
# MAGIC   models:/<カタログ>.<あなたのスキーマ>.demand_forecast@champion
# MAGIC                                                        ↑
# MAGIC                                         「今の本番」を指す名札
# MAGIC ```
# MAGIC
# MAGIC ⭐ 後でモデルを差し替えても、**このコードは 1 文字も変えません。**
# MAGIC 名札の付け替えだけで本番が切り替わります。これが登録する一番の利点です。

# COMMAND ----------

# MAGIC %pip install -q "mlflow>=2.22.0" "scikit-learn>=1.5.0" matplotlib

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

# MAGIC %run ./_config

# COMMAND ----------

import os
import sys

_nb_path = dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(_nb_path), ".."))
_src = f"/Workspace{REPO_ROOT}/src" if not REPO_ROOT.startswith("/Workspace") else f"{REPO_ROOT}/src"
if _src not in sys.path:
    sys.path.insert(0, _src)

from mlops.features import FEATURE_COLS, SERIES_COLS, TARGET_COL, TIME_COL, build_features  # noqa: E402

MODEL_NAME = f"{MY}.demand_forecast"
MODEL_URI = f"models:/{MODEL_NAME}@champion"
print(f"使うモデル: {MODEL_URI}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. 何を予測するか
# MAGIC
# MAGIC ⭐ ここでは **実績のある全期間について予測を作り直します**。
# MAGIC 「未来だけ」ではなく過去も予測するのは、**実績と突き合わせて精度を測れるようにする**ためです。
# MAGIC
# MAGIC ⚠️ 18 か月先まで予測するには、本来「予測値を次の月の特徴量に使う」再帰的な処理が必要です。
# MAGIC 今日はそこまで踏み込まず、**実績のある期間で「モデル vs 去年と同じ」を比べる**ことに集中します。

# COMMAND ----------

import mlflow
import numpy as np
import pandas as pd

mlflow.set_registry_uri("databricks-uc")

pdf = spark.table(f"{MY}.fct_shipments").select(*SERIES_COLS, TIME_COL, TARGET_COL).toPandas()
feat = build_features(pdf).dropna(subset=FEATURE_COLS).reset_index(drop=True)
print(f"推論対象: {len(feat):,} 行 / {feat.groupby(SERIES_COLS).ngroups} 系列")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. 推論する
# MAGIC
# MAGIC ⭐ モデルの読み込みは 1 行です。**中身が何のアルゴリズムかを知らなくても使えます。**

# COMMAND ----------

model = mlflow.pyfunc.load_model(MODEL_URI)
model_version = model.metadata.get_model_info().registered_model_version if hasattr(model.metadata, "get_model_info") else None

# バージョン番号はエイリアスから取り直す（表示用）
client = mlflow.MlflowClient()
mv = client.get_model_version_by_alias(MODEL_NAME, "champion")
model_version = mv.version
print(f"@champion が指しているのはバージョン {model_version}")

pred = np.clip(model.predict(feat[FEATURE_COLS]), 0, None)
feat["forecast_qty"] = pred
print(f"✅ {len(feat):,} 行を推論しました")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. 予測結果をテーブルに書き出す
# MAGIC
# MAGIC ⭐ ベースライン予測 (`fct_forecast_baseline`) と**同じ形**で書き出します。
# MAGIC そうすると 2 つを縦に繋げて、同じクエリで比べられます。

# COMMAND ----------

out = pd.DataFrame({
    "item_code": feat["item_code"],
    "channel": feat["channel"],
    "target_ym": feat[TIME_COL].dt.date,
    "forecast_run_ym": pd.Timestamp.today().to_period("M").to_timestamp("M").date(),
    "model_name": f"demand_forecast_v{model_version}",
    "p50": feat["forecast_qty"].astype(float),
    "lower_bound": (feat["forecast_qty"] * 0.7).astype(float),
    "upper_bound": (feat["forecast_qty"] * 1.3).astype(float),
})

sdf = spark.createDataFrame(out)
sdf.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"{MY}.fct_forecast_model")
spark.sql(f"COMMENT ON TABLE {MY}.fct_forecast_model IS "
          f"'自分で学習したモデルによる予測。fct_forecast_baseline と同じ形なので縦に繋げて比較できる。'")

print(f"✅ {MY}.fct_forecast_model に {sdf.count():,} 行を書き出しました")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. ⭐⭐ 評価テーブルを更新する
# MAGIC
# MAGIC ⚠️ ここまでで予測は作りましたが、**「当たったかどうか」がテーブルに残っていません。**
# MAGIC ⭐ 予測と実績を突き合わせた結果を、**すべての予測手法をまとめて 1 つのテーブル**に
# MAGIC 書き出します。
# MAGIC
# MAGIC ```
# MAGIC   fct_forecast_baseline  （去年と同じ）    ┐
# MAGIC   fct_forecast_model     （自作モデル）    ├─▶ fct_forecast_accuracy_all
# MAGIC   fct_forecast_ai        （ai_forecast）  ┘        ↑ 実績と突き合わせ済み
# MAGIC ```
# MAGIC
# MAGIC ⭐ **これがあると「毎月、精度が自動で記録される」状態になります。**
# MAGIC ⚠️ ここを作らないと、精度は誰かが手でクエリを書いたときにしか分かりません。
# MAGIC 「気づいたら 3 か月ずれ続けていた」が起きるのはこの穴です。

# COMMAND ----------

# 存在する予測テーブルだけを対象にする（03 を飛ばした場合でも動くように）
sources = []
for tbl in ("fct_forecast_baseline", "fct_forecast_model", "fct_forecast_ai"):
    if spark.catalog.tableExists(f"{MY}.{tbl}"):
        sources.append(tbl)
    else:
        print(f"⏭  {tbl} は無いので対象外")

union_sql = " UNION ALL ".join(
    f"SELECT item_code, channel, target_ym, model_name, p50, "
    f"       lower_bound, upper_bound FROM {MY}.{s}"
    for s in sources
)

spark.sql(f"""
    CREATE OR REPLACE TABLE {MY}.fct_forecast_accuracy_all AS
    WITH all_forecasts AS ({union_sql})
    SELECT
      f.item_code,
      f.channel,
      f.target_ym,
      f.model_name,
      f.p50                              AS forecast_qty,
      a.qty                              AS actual_qty,
      abs(a.qty - f.p50)                 AS abs_error,
      CASE WHEN a.qty > 0 THEN abs(a.qty - f.p50) / a.qty END AS ape,
      CASE WHEN a.qty BETWEEN f.lower_bound AND f.upper_bound THEN 1 ELSE 0 END AS within_interval
    FROM all_forecasts f
    INNER JOIN {MY}.fct_shipments a
      ON  f.item_code = a.item_code
      AND f.channel   = a.channel
      AND f.target_ym = a.ym
""")
spark.sql(f"COMMENT ON TABLE {MY}.fct_forecast_accuracy_all IS "
          f"'すべての予測手法を実績と突き合わせた結果。手法ごとの精度を同じ条件で比べられる。'")

print(f"✅ {MY}.fct_forecast_accuracy_all を更新しました "
      f"({spark.table(f'{MY}.fct_forecast_accuracy_all').count():,} 行 / 対象 {len(sources)} 手法)")
display(spark.sql(f"""
    SELECT model_name AS `予測手法`,
           ROUND(AVG(abs_error), 2)            AS `平均誤差_個数`,
           ROUND(AVG(ape) * 100, 1)            AS `平均誤差率_pct`,
           ROUND(AVG(within_interval) * 100, 1) AS `区間的中率_pct`,
           COUNT(*)                            AS `件数`
    FROM {MY}.fct_forecast_accuracy_all
    GROUP BY model_name
    ORDER BY `平均誤差_個数`
"""))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. ⭐⭐ 「モデル」と「去年と同じ」を並べて比べる
# MAGIC
# MAGIC ⭐ **ここが今日いちばん大事なクエリです。**
# MAGIC
# MAGIC ⚠️ 見るべきは 2 列です。
# MAGIC
# MAGIC | 列 | 意味 |
# MAGIC |---|---|
# MAGIC | `err_qty` | 平均で何個ずれたか。**小さい方が良い** |
# MAGIC | `vs_baseline` | 「去年と同じ」を 1.00 としたときの比。⭐ **1.00 未満なら勝ち** |

# COMMAND ----------

# MAGIC %sql
# MAGIC WITH both AS (
# MAGIC   SELECT item_code, channel, target_ym, model_name, p50 FROM fct_forecast_model
# MAGIC   UNION ALL
# MAGIC   SELECT item_code, channel, target_ym, model_name, p50 FROM fct_forecast_baseline
# MAGIC ),
# MAGIC joined AS (
# MAGIC   SELECT b.model_name, i.demand_class, abs(a.qty - b.p50) AS abs_err
# MAGIC   FROM both b
# MAGIC   JOIN fct_shipments a
# MAGIC     ON a.item_code = b.item_code AND a.channel = b.channel AND a.ym = b.target_ym
# MAGIC   JOIN dim_item i ON i.item_code = b.item_code
# MAGIC ),
# MAGIC per_model AS (
# MAGIC   SELECT model_name, ROUND(AVG(abs_err), 2) AS err_qty, COUNT(*) AS n
# MAGIC   FROM joined GROUP BY model_name
# MAGIC )
# MAGIC SELECT
# MAGIC   model_name,
# MAGIC   err_qty,
# MAGIC   n,
# MAGIC   ROUND(err_qty / (SELECT err_qty FROM per_model
# MAGIC                    WHERE model_name = 'baseline_seasonal_naive'), 3) AS vs_baseline
# MAGIC FROM per_model
# MAGIC ORDER BY err_qty

# COMMAND ----------

# MAGIC %md
# MAGIC ### ⭐ 需要の性質ごとに勝ち負けを見る
# MAGIC
# MAGIC ⚠️ **全体で勝っていても、品目によっては負けていることがあります。**
# MAGIC
# MAGIC ⭐ 負けている品目は、無理にモデルを当てようとせず
# MAGIC 「**去年と同じで運用する**」と決めてしまうのも立派な判断です。
# MAGIC 当てにいかない品目を切り分けることも改善のひとつです。

# COMMAND ----------

# MAGIC %sql
# MAGIC WITH both AS (
# MAGIC   SELECT item_code, channel, target_ym, 'model' AS src, p50 FROM fct_forecast_model
# MAGIC   UNION ALL
# MAGIC   SELECT item_code, channel, target_ym, 'baseline' AS src, p50 FROM fct_forecast_baseline
# MAGIC ),
# MAGIC joined AS (
# MAGIC   SELECT b.src, i.demand_class, abs(a.qty - b.p50) AS abs_err
# MAGIC   FROM both b
# MAGIC   JOIN fct_shipments a
# MAGIC     ON a.item_code = b.item_code AND a.channel = b.channel AND a.ym = b.target_ym
# MAGIC   JOIN dim_item i ON i.item_code = b.item_code
# MAGIC )
# MAGIC SELECT
# MAGIC   demand_class,
# MAGIC   ROUND(AVG(CASE WHEN src = 'model'    THEN abs_err END), 2) AS `model_err`,
# MAGIC   ROUND(AVG(CASE WHEN src = 'baseline' THEN abs_err END), 2) AS `baseline_err`,
# MAGIC   ROUND(AVG(CASE WHEN src = 'model'    THEN abs_err END)
# MAGIC       / AVG(CASE WHEN src = 'baseline' THEN abs_err END), 3) AS `vs_baseline`,
# MAGIC   CASE WHEN AVG(CASE WHEN src = 'model' THEN abs_err END)
# MAGIC           < AVG(CASE WHEN src = 'baseline' THEN abs_err END)
# MAGIC        THEN 'モデルの勝ち' ELSE '去年と同じの勝ち' END AS `judge`
# MAGIC FROM joined
# MAGIC GROUP BY demand_class
# MAGIC ORDER BY `vs_baseline`

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6. ⭐ グラフで見る
# MAGIC
# MAGIC 表の数字だけだと差が実感しにくいので、**同じ内容をグラフにします**。

# COMMAND ----------

import os
import sys

_p = dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
_root = os.path.normpath(os.path.join(os.path.dirname(_p), ".."))
_src = f"/Workspace{_root}/src" if not _root.startswith("/Workspace") else f"{_root}/src"
if _src not in sys.path:
    sys.path.insert(0, _src)

from mlops.plots import plot_grouped_bars, plot_pred_vs_actual, plot_error_over_time  # noqa: E402

# COMMAND ----------

# MAGIC %md
# MAGIC ### ① 予測 vs 実績（点が対角線に乗っていれば当たっている）
# MAGIC
# MAGIC ⭐ 対角線から**上に外れている点は多く見込みすぎ**、**下は少なく見込みすぎ**です。
# MAGIC ⚠️ 数量が桁で違うので両軸を対数にしています。

# COMMAND ----------

pva = spark.sql(f"""
    SELECT a.qty AS actual_qty, m.p50 AS forecast_qty
    FROM {MY}.fct_forecast_model m
    JOIN {MY}.fct_shipments a
      ON a.item_code = m.item_code AND a.channel = m.channel AND a.ym = m.target_ym
    WHERE a.qty > 0
""").toPandas()

display(plot_pred_vs_actual(pva, title="model: predicted vs actual"))

# COMMAND ----------

# MAGIC %md
# MAGIC ### ② ⭐⭐ 需要の性質ごとに「モデル」と「去年と同じ」を並べる
# MAGIC
# MAGIC ⭐ **棒が低い方が良い**（誤差が小さい）。
# MAGIC ⚠️ 全体で勝っていても、**性質によっては負けている**ことが見えます。

# COMMAND ----------

cmp_df = spark.sql(f"""
    WITH both AS (
      SELECT item_code, channel, target_ym, 'model' AS src, p50 FROM {MY}.fct_forecast_model
      UNION ALL
      SELECT item_code, channel, target_ym, 'baseline' AS src, p50 FROM {MY}.fct_forecast_baseline
    ),
    j AS (
      SELECT b.src, i.demand_class, abs(a.qty - b.p50) AS e
      FROM both b
      JOIN {MY}.fct_shipments a
        ON a.item_code = b.item_code AND a.channel = b.channel AND a.ym = b.target_ym
      JOIN {MY}.dim_item i ON i.item_code = b.item_code
    )
    SELECT demand_class,
           ROUND(AVG(CASE WHEN src = 'model'    THEN e END), 2) AS model,
           ROUND(AVG(CASE WHEN src = 'baseline' THEN e END), 2) AS baseline
    FROM j GROUP BY demand_class ORDER BY baseline DESC
""").toPandas()

display(plot_grouped_bars(
    cmp_df, "demand_class", ["model", "baseline"],
    "mean absolute error by demand class (lower is better)",
    ylabel="mean absolute error (units)",
))

# COMMAND ----------

# MAGIC %md
# MAGIC ### ③ 月ごとの誤差の推移
# MAGIC
# MAGIC ⭐ **ある月だけ大きく外している**ことがないかを確認します。
# MAGIC ⚠️ 特定の月が飛び抜けている場合、その月に何か業務上の出来事があったはずです。

# COMMAND ----------

trend = spark.sql(f"""
    WITH both AS (
      SELECT item_code, channel, target_ym, 'model' AS src, p50 FROM {MY}.fct_forecast_model
      UNION ALL
      SELECT item_code, channel, target_ym, 'baseline' AS src, p50 FROM {MY}.fct_forecast_baseline
    ),
    j AS (
      SELECT b.src, b.target_ym, abs(a.qty - b.p50) AS e
      FROM both b
      JOIN {MY}.fct_shipments a
        ON a.item_code = b.item_code AND a.channel = b.channel AND a.ym = b.target_ym
    )
    SELECT target_ym,
           ROUND(AVG(CASE WHEN src = 'model'    THEN e END), 2) AS model,
           ROUND(AVG(CASE WHEN src = 'baseline' THEN e END), 2) AS baseline
    FROM j GROUP BY target_ym ORDER BY target_ym
""").toPandas()

display(plot_error_over_time(
    trend, "target_ym", {"model": "model", "baseline (last year)": "baseline"},
    "mean absolute error over time (lower is better)",
))

# COMMAND ----------

# MAGIC %md
# MAGIC ## ✅ ここまでできたら
# MAGIC
# MAGIC 次は **`06_retrain`** に進みます。
# MAGIC
# MAGIC ⭐ 新しい月のデータが届いたときに、**再学習して本番を入れ替える**流れをやります。
# MAGIC ⚠️ そして「新しいモデルが必ず良い」とは限らないので、**入れ替える前に比べます**。
