# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "5"
# ///
# MAGIC %md
# MAGIC # 04 — モデルを作り、記録し、登録する
# MAGIC
# MAGIC > ⏱ **目安 15 分**
# MAGIC >
# MAGIC > 🔑 **必要な権限**: 自分のスキーマへの `CREATE MODEL`（自分で作ったスキーマなので既にあります）
# MAGIC
# MAGIC ## このパートでやること
# MAGIC
# MAGIC | | 内容 | 何が解決するか |
# MAGIC |---|---|---|
# MAGIC | 1 | 特徴量を作る | 学習と推論で**同じ作り方**を使う |
# MAGIC | 2 | ⭐ **条件を変えて何回か学習し、MLflow に記録する** | 「どれが良かったか」が後から分かる |
# MAGIC | 3 | ⭐⭐ **「去年と同じ」と比べる** | 作ったモデルに**価値があるのか**を確かめる |
# MAGIC | 4 | ⭐ **Unity Catalog に登録する** | 「本番はどれか」が一目で分かる |
# MAGIC
# MAGIC ## ⚠️ 記録が残らないと何が起きるか
# MAGIC
# MAGIC - 本番で動いているのが **どのモデルのどのバージョンか分からない**
# MAGIC - 試した結果が残らず、**後から再現できない**
# MAGIC - 精度が落ちても、作り直しと切り替えが **人に依存して回らない**
# MAGIC
# MAGIC ⭐ これを仕組みで解決するのが MLflow と Unity Catalog です。

# COMMAND ----------

# MAGIC %pip install -q "mlflow>=2.22.0" "scikit-learn>=1.5.0" matplotlib

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

# MAGIC %run ./_config

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. 特徴量を作る
# MAGIC
# MAGIC ⭐ 特徴量の作り方は `src/mlops/features.py` に**関数として切り出して**あります。
# MAGIC
# MAGIC ⚠️ **これが地味に一番大事です。** 学習時と推論時で特徴量の作り方が少しでも違うと、
# MAGIC 「学習では良い数字が出たのに本番だけ当たらない」という、原因を突き止めにくい事故になります。
# MAGIC 同じ関数を両方から呼ぶことで、それを防ぎます。
# MAGIC
# MAGIC 作っている特徴量:
# MAGIC
# MAGIC | 種類 | 中身 | 狙い |
# MAGIC |---|---|---|
# MAGIC | ラグ | 1・2・3 か月前、**前年同月** | 直近の勢いと季節性 |
# MAGIC | 移動平均 | 3・6・12 か月 | ならした水準 |
# MAGIC | 移動標準偏差 | 6 か月 | 振れの大きさ |
# MAGIC | 非ゼロ比率 | 直近 12 か月で需要が出た月の割合 | **間欠需要の目印** |
# MAGIC | 月 / 通し番号 | — | 季節性とトレンド |
# MAGIC
# MAGIC > ⚠️ 移動平均には `shift(1)` を挟んでいます。当月の実績を特徴量に含めると
# MAGIC > 「答えを見ながら予測する」ことになり、本番では通用しません。

# COMMAND ----------

import os
import sys

# repo の src/ を import できるようにする
_nb_path = dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(_nb_path), ".."))
_src = f"/Workspace{REPO_ROOT}/src" if not REPO_ROOT.startswith("/Workspace") else f"{REPO_ROOT}/src"
if _src not in sys.path:
    sys.path.insert(0, _src)

from mlops.features import FEATURE_COLS, SERIES_COLS, TARGET_COL, TIME_COL, training_frame  # noqa: E402

print(f"特徴量の数: {len(FEATURE_COLS)}")
print("  " + ", ".join(FEATURE_COLS))

# COMMAND ----------

import pandas as pd

pdf = spark.table(f"{MY}.fct_shipments").select(*SERIES_COLS, TIME_COL, TARGET_COL).toPandas()
feat = training_frame(pdf)

print(f"元データ       : {len(pdf):,} 行")
print(f"特徴量が揃った行: {len(feat):,} 行  ← 各系列の先頭 12 か月は落ちます")
print(f"系列数         : {feat.groupby(SERIES_COLS).ngroups}")
display(feat.head(5))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. 学習データと検証データに分ける
# MAGIC
# MAGIC ⚠️ **時系列では「ランダムに分ける」をやってはいけません。**
# MAGIC 未来のデータで学習して過去を予測することになり、本番よりずっと良い数字が出ます。
# MAGIC
# MAGIC ⭐ **ある月で線を引き、それ以前で学習し、それ以降で検証**します。
# MAGIC
# MAGIC ### ⭐⭐ ここでは「半年前にモデルを作った」ことにします
# MAGIC
# MAGIC 実際の現場では、**本番で動いているモデルは過去に作られたもの**です。
# MAGIC 作った後に増えたデータを、そのモデルは見ていません。
# MAGIC
# MAGIC ⭐ その状況を再現するため、**直近 6 か月を「まだ存在しなかったこと」にして**学習します。
# MAGIC
# MAGIC ```
# MAGIC   |------- 学習に使う -------|-- 検証 --|== 見ないことにする ==|
# MAGIC                                          ↑ ここから先は「モデルを作った後に届いたデータ」
# MAGIC ```
# MAGIC
# MAGIC ⚠️ **これは手抜きではありません。** 後のパート（`06_retrain`）で
# MAGIC 「新しいデータで作り直すと本当に良くなるのか」を検証するために、
# MAGIC **本番モデルが古い**という現実的な前提を作っています。

# COMMAND ----------

# ⭐ 「モデルを作った時点」を何か月前に置くか
MODEL_BUILT_MONTHS_AGO = 6
# 検証に使う月数
VALID_MONTHS = 12

months = sorted(feat[TIME_COL].unique())
# モデルを作った時点（この月までのデータしか使わない）
as_of_ym = months[-1 - MODEL_BUILT_MONTHS_AGO]
# 検証はその直前 12 か月
split_ym = months[-1 - MODEL_BUILT_MONTHS_AGO - VALID_MONTHS + 1]

available = feat[feat[TIME_COL] <= as_of_ym]
train = available[available[TIME_COL] < split_ym]
valid = available[available[TIME_COL] >= split_ym]

print(f"データの最終月       : {pd.Timestamp(months[-1]).date()}")
print(f"⭐ モデルを作った時点 : {pd.Timestamp(as_of_ym).date()}  "
      f"（ここから先の {MODEL_BUILT_MONTHS_AGO} か月は見ないことにします）")
print(f"分割の境目           : {pd.Timestamp(split_ym).date()}")
print(f"学習                 : {len(train):,} 行  "
      f"({train[TIME_COL].min().date()} 〜 {train[TIME_COL].max().date()})")
print(f"検証                 : {len(valid):,} 行  "
      f"({valid[TIME_COL].min().date()} 〜 {valid[TIME_COL].max().date()})")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. ⭐⭐ 比べる相手（「去年と同じ」）の成績を先に出す
# MAGIC
# MAGIC ⭐ **モデルを作る前に、超えるべき数字を確認します。**
# MAGIC これをやらないと「精度 ◯◯% でした」と言っても良いのか悪いのか分かりません。
# MAGIC
# MAGIC ⚠️ 指標は 2 つ見ます。**片方だけ見ると判断を誤ります。**
# MAGIC
# MAGIC | 指標 | 意味 | 注意 |
# MAGIC |---|---|---|
# MAGIC | **MAE**（平均絶対誤差） | 平均で何個ずれたか | 数量の多い品目に引っ張られる |
# MAGIC | **MASE** | 「去年と同じ」を 1.0 としたときの相対値 | ⭐ **1.0 未満なら勝ち、超えたら負け** |

# COMMAND ----------

import numpy as np

# 「去年と同じ」= 前年同月の実績 = 特徴量の lag_12
baseline_pred = valid["lag_12"].to_numpy()
y_valid = valid[TARGET_COL].to_numpy()

baseline_mae = float(np.mean(np.abs(y_valid - baseline_pred)))
print(f"「去年と同じ」の MAE : {baseline_mae:.2f} 個")
print(f"  → これより小さくできれば、モデルに価値があります")
print(f"  → MASE は「モデルの MAE ÷ {baseline_mae:.2f}」で計算します（1.0 未満なら勝ち）")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. ⭐ 条件を変えて何回か学習し、MLflow に記録する
# MAGIC
# MAGIC ⭐ 3 通りの設定で学習します。**学習のコードはほとんど変えません。**
# MAGIC 変わるのは「`mlflow.start_run()` の中で実行し、結果を記録する」ことだけです。
# MAGIC
# MAGIC 記録されるもの:
# MAGIC
# MAGIC | 種類 | 例 |
# MAGIC |---|---|
# MAGIC | パラメータ | 木の深さ、学習率、反復回数 |
# MAGIC | 評価指標 | MAE、MASE |
# MAGIC | モデル本体 | 後から呼び出して推論できる形で |
# MAGIC | 入出力の形 | どんな列を受け取り、何を返すか |

# COMMAND ----------

import mlflow
from mlflow.models import infer_signature
from sklearn.ensemble import HistGradientBoostingRegressor

mlflow.set_registry_uri("databricks-uc")
EXPERIMENT = f"/Users/{spark.sql('SELECT current_user()').collect()[0][0]}/需要予測ハンズオン"
mlflow.set_experiment(EXPERIMENT)
print(f"実験の記録先: {EXPERIMENT}")

X_train, y_train = train[FEATURE_COLS], train[TARGET_COL]
X_valid = valid[FEATURE_COLS]

# 試す設定（わざと性能に差が出るようにしています）
TRIALS = [
    {"name": "浅い木",   "max_depth": 3,  "learning_rate": 0.10, "max_iter": 150},
    {"name": "標準",     "max_depth": 6,  "learning_rate": 0.05, "max_iter": 400},
    {"name": "深い木",   "max_depth": 12, "learning_rate": 0.05, "max_iter": 400},
]

results = []
for trial in TRIALS:
    name = trial.pop("name")
    with mlflow.start_run(run_name=name) as run:
        model = HistGradientBoostingRegressor(random_state=42, **trial)
        model.fit(X_train, y_train)

        pred = np.clip(model.predict(X_valid), 0, None)
        mae = float(np.mean(np.abs(y_valid - pred)))
        mase = mae / baseline_mae

        mlflow.log_params(trial)
        # ⭐ 「いつまでのデータで学習したか」を残す。06 でここを見て劣化を説明します。
        # ⭐ 「学習に使った最終月」を残す（06 でここを見て劣化を説明します）
        mlflow.log_param("trained_through", str(pd.Timestamp(train[TIME_COL].max()).date()))
        mlflow.log_param("data_available_through", str(pd.Timestamp(as_of_ym).date()))
        mlflow.log_metrics({
            "mae": mae,
            "mase": mase,
            "baseline_mae": baseline_mae,
        })
        mlflow.sklearn.log_model(
            model,
            name="model",
            signature=infer_signature(X_valid, pred),
            input_example=X_valid.head(3),
        )
        results.append({"name": name, "run_id": run.info.run_id, "mae": mae, "mase": mase})
    trial["name"] = name  # 表示用に戻す

print(f"\n{'設定':<10} {'MAE':>10} {'MASE':>8}   判定")
print("-" * 50)
for r in sorted(results, key=lambda x: x["mae"]):
    verdict = "⭐ 去年と同じに勝った" if r["mase"] < 1.0 else "⚠️ 去年と同じに負けた"
    print(f"{r['name']:<10} {r['mae']:>10.2f} {r['mase']:>8.3f}   {verdict}")

# COMMAND ----------

# MAGIC %md
# MAGIC ### 実験の画面を開いてみる
# MAGIC
# MAGIC ⭐ 左メニューの **「実験」** から、いま記録した 3 回の実行を並べて比較できます。
# MAGIC 半年後に「あのとき何を試したか」を思い出す必要がなくなります。

# COMMAND ----------

from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
exp = mlflow.get_experiment_by_name(EXPERIMENT)
displayHTML(f'<a href="{w.config.host}/ml/experiments/{exp.experiment_id}" target="_blank">▶ 実験の画面を開く</a>')

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. ⭐ いちばん良かったモデルを Unity Catalog に登録する
# MAGIC
# MAGIC ⭐ 登録すると何が変わるか:
# MAGIC
# MAGIC | | 登録しないと | ⭐ 登録すると |
# MAGIC |---|---|---|
# MAGIC | 本番のモデル | コードやファイル名で管理（人に依存） | **エイリアス**で一目で分かる |
# MAGIC | 履歴 | 上書きされて消える | **バージョン**として全部残る |
# MAGIC | 由来 | 追えない | どのデータ・どの実行から来たか追える |
# MAGIC | 権限 | ファイル任せ | テーブルと同じ仕組みで管理 |
# MAGIC
# MAGIC ⭐ **エイリアス**は「今どれが本番か」を指す名札です。
# MAGIC ここでは `@champion`（本番稼働中）を付けます。
# MAGIC 次のパートで再学習したモデルには `@challenger`（挑戦者）を付け、勝ったら入れ替えます。

# COMMAND ----------

best = min(results, key=lambda x: x["mae"])
MODEL_NAME = f"{MY}.demand_forecast"

print(f"いちばん良かった設定: {best['name']}（MAE {best['mae']:.2f} / MASE {best['mase']:.3f}）")

registered = mlflow.register_model(
    model_uri=f"runs:/{best['run_id']}/model",
    name=MODEL_NAME,
)
version = registered.version
print(f"✅ 登録しました: {MODEL_NAME} バージョン {version}")

client = mlflow.MlflowClient()
client.set_registered_model_alias(name=MODEL_NAME, alias="champion", version=version)
print(f"✅ エイリアス @champion をバージョン {version} に付けました")

# 後のノートブックが参照できるように、判定の材料も記録しておく
client.set_model_version_tag(MODEL_NAME, version, "mae", f"{best['mae']:.4f}")
client.set_model_version_tag(MODEL_NAME, version, "mase", f"{best['mase']:.4f}")
client.set_model_version_tag(MODEL_NAME, version, "baseline_mae", f"{baseline_mae:.4f}")
client.set_model_version_tag(
    MODEL_NAME, version, "trained_through", str(pd.Timestamp(train[TIME_COL].max()).date()))
client.set_model_version_tag(
    MODEL_NAME, version, "data_available_through", str(pd.Timestamp(as_of_ym).date()))

displayHTML(
    f'<a href="{w.config.host}/explore/data/models/{catalog}/{schema}/demand_forecast" '
    'target="_blank">▶ Unity Catalog で登録したモデルを見る</a>'
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## ✅ ここまでできたら
# MAGIC
# MAGIC 次は **`05_batch_inference`** に進みます。
# MAGIC
# MAGIC ⭐ 登録したモデルを **名前で呼び出して**、全品目の予測をまとめて作ります。
# MAGIC ⚠️ 「どのファイルのモデルだったか」を覚えておく必要はもうありません。
# MAGIC `@champion` と書けば、いつでも「今の本番」が呼ばれます。
