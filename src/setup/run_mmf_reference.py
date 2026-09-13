# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "5"
# ///
# MAGIC %md
# MAGIC # 管理者向け — MMF の参考結果を作る
# MAGIC
# MAGIC > 🧑‍💼 **管理者が事前に 1 回実行するノートブックです。** 参加者は実行しません。
# MAGIC >
# MAGIC > ⏱ **10〜30 分**かかります（系列数とモデル数によります）
# MAGIC
# MAGIC ## なぜ事前に実行するのか
# MAGIC
# MAGIC `08_mmf_genie_code` で参加者に見せる結果を、あらかじめ用意しておきます。
# MAGIC ⚠️ 当日その場で最後まで回すと 30 分近くかかり、時間が読めません。
# MAGIC
# MAGIC ⭐ 当日は「AI が要件をヒアリングしてくる」ところだけ体験し、
# MAGIC **結果はこのノートブックが作ったものを見る**構成にしています。
# MAGIC
# MAGIC ## ⚠️ 実行環境
# MAGIC
# MAGIC | 項目 | 要件 |
# MAGIC |---|---|
# MAGIC | 計算資源 | ⭐ **サーバーレスで動きます**（環境バージョン 5 を宣言済み） |
# MAGIC | GPU | ⭐ **不要**（GPU が要るのはニューラル予測と基盤モデルだけ。今回は使いません） |
# MAGIC | サポート | ⚠️ MMF は **Databricks の正式サポート対象外**（AS-IS で公開） |
# MAGIC
# MAGIC > ⚠️ **MMF の公式ドキュメントは「DBR 18 for ML 以上」を前提にしています。**
# MAGIC > サーバーレス専用のワークスペースではクラスタを作れないため、
# MAGIC > ここでは**サーバーレス + 環境バージョン 5 + `%pip install`** で動かします。
# MAGIC > ⭐ 統計モデルだけなら Spark の ML ランタイムに依存しないため成立します。
# MAGIC
# MAGIC > ⭐ **Genie Code は使いません。** ここでは MMF の関数を直接呼びます。
# MAGIC > 当日 Genie Code で見せるのは「対話しながら進む」体験の部分で、
# MAGIC > 中で動くのは同じ仕組みです。

# COMMAND ----------

# MAGIC %pip install -q "mmf_sa[local] @ git+https://github.com/databricks-industry-solutions/many-model-forecasting.git@main"

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

dbutils.widgets.text("catalog", "demand_forecast_handson", "カタログ")
dbutils.widgets.text("schema", "fc_sample", "書き込み先スキーマ")
dbutils.widgets.text("use_case", "scm", "ユースケース名")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
use_case = dbutils.widgets.get("use_case")
TARGET = f"{catalog}.{schema}"

print(f"書き込み先   : {TARGET}")
print(f"ユースケース : {use_case}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. MMF に渡す形にデータを整える
# MAGIC
# MAGIC MMF は 3 列だけを見ます。
# MAGIC
# MAGIC | MMF の列 | 意味 | 今回あてるもの |
# MAGIC |---|---|---|
# MAGIC | `unique_id` | 系列の識別子 | 品目コード + チャネル |
# MAGIC | `ds` | 日付 | `ym`（⚠️ **月末日**） |
# MAGIC | `y` | 予測したい値 | `qty` |
# MAGIC
# MAGIC ⚠️⚠️ **`freq="M"` では日付が月末日に揃っていることが必須**です。
# MAGIC 月初日のままだと実行時に失敗します。今回のデータは既に月末日で揃えてあります。

# COMMAND ----------

TRAIN_TABLE = f"{TARGET}.{use_case}_train_data"

spark.sql(f"""
    CREATE OR REPLACE TABLE {TRAIN_TABLE} AS
    SELECT
      CONCAT(item_code, '|', channel) AS unique_id,
      LAST_DAY(ym)                    AS ds,
      CAST(qty AS DOUBLE)             AS y
    FROM {TARGET}.fct_shipments
""")

n_rows = spark.table(TRAIN_TABLE).count()
n_series = spark.sql(f"SELECT COUNT(DISTINCT unique_id) FROM {TRAIN_TABLE}").collect()[0][0]
print(f"✅ {TRAIN_TABLE}: {n_rows:,} 行 / {n_series} 系列")
display(spark.table(TRAIN_TABLE).limit(5))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. モデルを選ぶ
# MAGIC
# MAGIC ⭐ **CPU だけで動くモデルに絞ります。**
# MAGIC よく使われる手法はほぼ揃っています。
# MAGIC
# MAGIC | 選んだモデル | よく知られた名前 |
# MAGIC |---|---|
# MAGIC | `StatsForecastAutoETS` | 指数平滑 (ETS) |
# MAGIC | `StatsForecastAutoTheta` | Theta 法 |
# MAGIC | `StatsForecastAutoArima` | ARIMA |
# MAGIC | `StatsForecastAutoMfles` | MFLES |
# MAGIC | ⭐ `StatsForecastCrostonSBA` | **間欠需要向け (Croston)** |
# MAGIC | `SKTimeProphet` | Prophet |
# MAGIC
# MAGIC ⚠️ ニューラル予測 (`NeuralForecastAutoNHITS` 等) と基盤モデル
# MAGIC (`Chronos` / `TimesFM`) は **GPU が必要**なので入れていません。
# MAGIC
# MAGIC ⭐ **`CrostonSBA` を必ず入れてください。** 出ない月がある品目では、
# MAGIC これが他のモデルより良い結果を出すことがあり、
# MAGIC 「品目ごとに最適な手法が違う」を示す材料になります。

# COMMAND ----------

ACTIVE_MODELS = [
    "StatsForecastAutoETS",
    "StatsForecastAutoTheta",
    "StatsForecastAutoArima",
    "StatsForecastAutoMfles",
    "StatsForecastCrostonSBA",
    "SKTimeProphet",
]

# 予測は 18 か月先まで
PREDICTION_LENGTH = 18
# ⚠️ 検証に使う期間は、予測期間以上でなければなりません。
#    （12 にすると「Backtest length (12) is shorter than prediction length (18)」で失敗します）
BACKTEST_LENGTH = 24
# 6 か月ずつずらして検証します
STRIDE = 6

for m in ACTIVE_MODELS:
    print(f"  {m}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. 実行する
# MAGIC
# MAGIC ⚠️ **10〜30 分かかります。**
# MAGIC
# MAGIC 作られるテーブル:
# MAGIC
# MAGIC | テーブル | 中身 |
# MAGIC |---|---|
# MAGIC | `{use_case}_evaluation_output` | **全モデル × 全系列**の検証結果 |
# MAGIC | `{use_case}_scoring_output` | 18 か月先の予測 |
# MAGIC
# MAGIC ⚠️⚠️ **統計モデルは Unity Catalog に登録されません。**
# MAGIC `evaluation_output` の `model_pickle` にモデル本体が入り、`model_uri` は空になります。
# MAGIC ⭐ MMF の価値は「モデルを登録すること」ではなく
# MAGIC 「**系列ごとにどの手法が良いかを突き止めること**」にあります。

# COMMAND ----------

from mmf_sa import run_forecast

run_id = run_forecast(
    spark=spark,
    train_data=TRAIN_TABLE,
    group_id="unique_id",
    date_col="ds",
    target="y",
    freq="M",
    prediction_length=PREDICTION_LENGTH,
    backtest_length=BACKTEST_LENGTH,
    stride=STRIDE,
    metric="smape",
    train_predict_ratio=1,
    active_models=ACTIVE_MODELS,
    data_quality_check=False,
    resample=False,
    # ⚠️ scoring_data を渡さないと、検証だけで終わり
    #    「18 か月先の予測」(scoring_output) が作られません。
    scoring_data=TRAIN_TABLE,
    experiment_path=f"/Users/{spark.sql('SELECT current_user()').collect()[0][0]}/mmf_{use_case}",
    evaluation_output=f"{TARGET}.{use_case}_evaluation_output",
    scoring_output=f"{TARGET}.{use_case}_scoring_output",
    use_case_name=use_case,
)
print(f"✅ 完了しました (run_id={run_id})")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. ⭐ 系列ごとのベストモデルを選ぶ
# MAGIC
# MAGIC ⚠️ **これは `run_forecast()` が作ってくれるものではありません。**
# MAGIC 検証結果から自分で選びます（SQL 1 本です）。
# MAGIC
# MAGIC ⭐ 系列ごとに、検証期間を通した平均スコアがいちばん良いモデルを 1 つ選びます。

# COMMAND ----------

spark.sql(f"""
    CREATE OR REPLACE TABLE {TARGET}.{use_case}_best_models AS
    WITH scored AS (
      SELECT
        unique_id,
        model,
        AVG(metric_value) AS avg_metric,
        RANK() OVER (PARTITION BY unique_id ORDER BY AVG(metric_value) ASC) AS rnk
      FROM {TARGET}.{use_case}_evaluation_output
      WHERE metric_value IS NOT NULL
      GROUP BY unique_id, model
    )
    SELECT unique_id, model, avg_metric, 'main_pipeline' AS forecast_source
    FROM scored
    WHERE rnk = 1
""")
spark.sql(f"COMMENT ON TABLE {TARGET}.{use_case}_best_models IS "
          f"'系列ごとに選ばれたベストモデル。検証期間の平均スコアが最も良いものを 1 つ選んでいる。'")

print(f"✅ {TARGET}.{use_case}_best_models")
display(spark.sql(f"""
    SELECT model AS `選ばれたモデル`, COUNT(*) AS `勝った系列数`,
           ROUND(AVG(avg_metric), 4) AS `平均スコア`
    FROM {TARGET}.{use_case}_best_models
    GROUP BY model ORDER BY `勝った系列数` DESC
"""))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. ⭐ 業務向けのまとめ
# MAGIC
# MAGIC ⭐ 「どの需要分類にどの手法が選ばれたか」を残しておくと、
# MAGIC 当日そのまま見せられます。

# COMMAND ----------

spark.sql(f"""
    CREATE OR REPLACE TABLE {TARGET}.{use_case}_evaluation_summary AS
    SELECT
      i.demand_class,
      b.model,
      COUNT(*)                       AS series_count,
      ROUND(AVG(b.avg_metric), 4)    AS avg_metric
    FROM {TARGET}.{use_case}_best_models b
    JOIN {TARGET}.dim_item i
      ON i.item_code = SPLIT(b.unique_id, '\\\\|')[0]
    GROUP BY i.demand_class, b.model
""")
spark.sql(f"COMMENT ON TABLE {TARGET}.{use_case}_evaluation_summary IS "
          f"'需要分類ごとに、どの手法が何系列で選ばれたか。'")

print(f"✅ {TARGET}.{use_case}_evaluation_summary")
display(spark.sql(f"""
    SELECT demand_class AS `需要分類`, model AS `選ばれたモデル`,
           series_count AS `系列数`, avg_metric AS `平均スコア`
    FROM {TARGET}.{use_case}_evaluation_summary
    ORDER BY `需要分類`, `系列数` DESC
"""))

# COMMAND ----------

# MAGIC %md
# MAGIC ## ✅ 確認
# MAGIC
# MAGIC ⭐ `08_mmf_genie_code` がこれらのテーブルを読みます。

# COMMAND ----------

for t in ["train_data", "evaluation_output", "scoring_output", "best_models", "evaluation_summary"]:
    name = f"{use_case}_{t}"
    try:
        print(f"  ✅ {name:<28} {spark.table(f'{TARGET}.{name}').count():>8,} 行")
    except Exception as e:  # noqa: BLE001
        print(f"  ❌ {name:<28} {type(e).__name__}")
