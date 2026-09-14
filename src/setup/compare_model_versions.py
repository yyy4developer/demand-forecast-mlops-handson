# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "5"
# ///
# MAGIC %md
# MAGIC # 管理者向け — 登録済みモデルを同じ条件で比べる
# MAGIC
# MAGIC > 🧑‍💼 **管理者用の確認ツールです。**
# MAGIC
# MAGIC 登録されている**すべてのバージョン**を、同じ検証期間で走らせて比べます。
# MAGIC ⭐ 「なぜ昇格した / しなかったのか」を確かめるときに使います。
# MAGIC
# MAGIC ⚠️ モデルバージョンに記録された数字（タグ）は、**学習した時点の検証期間**で
# MAGIC 測ったものです。期間が違うもの同士を比べても意味がないため、
# MAGIC ここでは**その場で全部走らせ直します**。

# COMMAND ----------

# MAGIC %pip install -q "mlflow>=2.22.0" "scikit-learn>=1.5.0"

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

dbutils.widgets.text("catalog", "demand_forecast_handson", "カタログ")
dbutils.widgets.text("schema", "fc_sample", "スキーマ")
dbutils.widgets.text("valid_months", "12", "検証に使う月数")
dbutils.widgets.text("recent_months", "3", "直近だけで見る月数")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
VALID_MONTHS = int(dbutils.widgets.get("valid_months"))
RECENT_MONTHS = int(dbutils.widgets.get("recent_months"))
MY = f"{catalog}.{schema}"
MODEL_NAME = f"{MY}.demand_forecast"

# COMMAND ----------

import os
import sys

_nb = dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
_root = os.path.normpath(os.path.join(os.path.dirname(_nb), "..", ".."))
_src = f"/Workspace{_root}/src" if not _root.startswith("/Workspace") else f"{_root}/src"
if _src not in sys.path:
    sys.path.insert(0, _src)

import mlflow
import numpy as np
import pandas as pd

from mlops.features import FEATURE_COLS, SERIES_COLS, TARGET_COL, TIME_COL, training_frame

mlflow.set_registry_uri("databricks-uc")
client = mlflow.MlflowClient()


def resolve(obj, name, default=None):
    v = getattr(obj, name, default)
    if callable(v):
        try:
            v = v()
        except Exception:  # noqa: BLE001
            v = default
    return v if v is not None else default


# COMMAND ----------

pdf = spark.table(f"{MY}.fct_shipments").select(*SERIES_COLS, TIME_COL, TARGET_COL).toPandas()
feat = training_frame(pdf)
months = sorted(feat[TIME_COL].unique())

split_ym = months[-VALID_MONTHS]
recent_ym = months[-RECENT_MONTHS]
valid = feat[feat[TIME_COL] >= split_ym]
recent = feat[feat[TIME_COL] >= recent_ym]

print(f"データの最終月 : {pd.Timestamp(months[-1]).date()}")
print(f"検証期間       : {pd.Timestamp(split_ym).date()} 〜 {pd.Timestamp(months[-1]).date()}  ({VALID_MONTHS} か月 / {len(valid):,} 行)")
print(f"直近だけ       : {pd.Timestamp(recent_ym).date()} 〜 {pd.Timestamp(months[-1]).date()}  ({RECENT_MONTHS} か月 / {len(recent):,} 行)")


def mae_of(df, pred):
    return float(np.mean(np.abs(df[TARGET_COL].to_numpy() - pred)))


base_valid = mae_of(valid, valid["lag_12"].to_numpy())
base_recent = mae_of(recent, recent["lag_12"].to_numpy())
print(f"\n「去年と同じ」の MAE : 検証期間 {base_valid:.2f} / 直近 {base_recent:.2f}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 全バージョンを同じ条件で走らせる
# MAGIC
# MAGIC ⭐ **`MASE` が 1.0 未満なら「去年と同じ」に勝っています。**
# MAGIC ⭐ `直近 MASE` は、変化が強く出る直近数か月だけで見た数字です。

# COMMAND ----------

aliases = {}
for a in ("champion", "challenger"):
    try:
        aliases[client.get_model_version_by_alias(MODEL_NAME, a).version] = a
    except Exception:  # noqa: BLE001
        pass

# ⚠️ `search_model_versions` の返り値にはタグが入っていないため、
#    バージョン番号だけ拾って 1 件ずつ取り直します。
_nums = sorted(int(mv.version) for mv in client.search_model_versions(f"name='{MODEL_NAME}'"))

rows = []
for mv in (client.get_model_version(MODEL_NAME, str(v)) for v in _nums):
    m = mlflow.pyfunc.load_model(f"models:/{MODEL_NAME}/{mv.version}")
    p_valid = np.clip(m.predict(valid[FEATURE_COLS]), 0, None)
    p_recent = np.clip(m.predict(recent[FEATURE_COLS]), 0, None)
    mae_v, mae_r = mae_of(valid, p_valid), mae_of(recent, p_recent)
    tags = resolve(mv, "tags", {}) or {}
    rows.append({
        "version": int(mv.version),
        "alias": aliases.get(mv.version, "-"),
        "trained_through": tags.get("trained_through", "?"),
        "mae": round(mae_v, 2),
        "mase": round(mae_v / base_valid, 3),
        "mae_recent": round(mae_r, 2),
        "mase_recent": round(mae_r / base_recent, 3),
    })

res = pd.DataFrame(rows)
print(f"{'版':>3} {'alias':<11} {'学習の最終月':<13} {'MAE':>8} {'MASE':>7} {'直近MAE':>9} {'直近MASE':>9}")
print("-" * 66)
print(f"{'-':>3} {'baseline':<11} {'-':<13} {base_valid:>8.2f} {1.0:>7.3f} {base_recent:>9.2f} {1.0:>9.3f}")
for r in rows:
    print(f"{r['version']:>3} {r['alias']:<11} {r['trained_through']:<13} "
          f"{r['mae']:>8.2f} {r['mase']:>7.3f} {r['mae_recent']:>9.2f} {r['mase_recent']:>9.3f}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## ⭐ 読み取り方
# MAGIC
# MAGIC ⚠️ **古いモデルでも成績が落ちにくいことがあります。**
# MAGIC
# MAGIC このモデルは **前月・前年同月・移動平均**を特徴量に使っています。
# MAGIC つまり推論のたびに**最新の実績が特徴量として入ってくる**ため、
# MAGIC 「学習したのが半年前」でも、直近の動きはある程度追えてしまいます。
# MAGIC
# MAGIC ⭐ これは実務では良いこと（急に壊れない）ですが、
# MAGIC ⚠️ **「再学習すれば必ず良くなる」とは限らない**ことも意味します。
# MAGIC
# MAGIC ⭐ 変化を捉えたいときは **直近数か月だけで見た数字 (`直近MASE`)** を見ます。
# MAGIC 検証期間全体では差が薄まっても、直近では差が出ることがあります。

# COMMAND ----------

# ⭐ 結果をテーブルにも残す（後から SQL で確認できるように）
OUT = f"{MY}.model_version_comparison"
spark.createDataFrame(res).write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(OUT)
spark.sql(f"COMMENT ON TABLE {OUT} IS "
          f"'登録済みモデルを同じ検証期間で走らせ直した比較結果。昇格の判断根拠を後から確認するためのもの。'")
print(f"✅ {OUT} に書き出しました")
display(spark.table(OUT))
