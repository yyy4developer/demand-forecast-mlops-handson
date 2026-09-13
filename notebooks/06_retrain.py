# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "5"
# ///
# MAGIC %md
# MAGIC # 06 — 新しいデータで再学習し、本番を入れ替える
# MAGIC
# MAGIC > ⏱ **目安 8 分**
# MAGIC
# MAGIC ⭐ ここが **MLOps と呼ばれるものの核心**です。
# MAGIC
# MAGIC モデルは作った瞬間から古くなっていきます。市場も製品も変わるからです。
# MAGIC ⚠️ でも「新しいデータで作り直したから、新しい方が良い」とは限りません。
# MAGIC
# MAGIC ## ⭐ 名札を 2 つ使う
# MAGIC
# MAGIC ```
# MAGIC   バージョン 1  ←  @champion    今の本番
# MAGIC   バージョン 2  ←  @challenger  新しく作った挑戦者
# MAGIC
# MAGIC        ↓  比べる
# MAGIC
# MAGIC   挑戦者が勝った  →  @champion を挑戦者に付け替える（昇格）
# MAGIC   挑戦者が負けた  →  そのまま。@challenger は記録として残す
# MAGIC ```
# MAGIC
# MAGIC ⭐ **「作り直したら必ず入れ替える」ではなく「比べて勝ったら入れ替える」。**
# MAGIC これを人の判断でやると、忙しい月には飛ばされます。だから仕組みにします。
# MAGIC
# MAGIC ## このパートでやること
# MAGIC
# MAGIC | | 内容 |
# MAGIC |---|---|
# MAGIC | 1 | 今の `@champion` の成績を確認する |
# MAGIC | 2 | 最新データで再学習し、新バージョンとして登録して `@challenger` を付ける |
# MAGIC | 3 | ⭐ **2 つを同じ条件で比べる** |
# MAGIC | 4 | ⭐ 勝っていたら `@champion` を付け替える |

# COMMAND ----------

# MAGIC %md
# MAGIC ## 0. 使うライブラリを入れる
# MAGIC
# MAGIC ⚠️ サーバーレスの既定環境（環境バージョン 1）には機械学習のライブラリが入っておらず、
# MAGIC Python も古いため、そのまま `mlflow` を入れると依存関係が衝突します。
# MAGIC
# MAGIC ⭐ このノートブックは先頭で **環境バージョン 5** を宣言しています。
# MAGIC
# MAGIC ```
# MAGIC # /// script
# MAGIC # [tool.databricks.environment]
# MAGIC # environment_version = "5"
# MAGIC # ///
# MAGIC ```
# MAGIC
# MAGIC > 💡 画面右側の **「環境」** パネルでもバージョンを確認・変更できます。
# MAGIC > ⚠️ ここが古いままだと、次のセルの後で `ImportError` が出ます。

# COMMAND ----------

# MAGIC %pip install -q "mlflow>=2.22.0" "scikit-learn>=1.5.0"

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

import mlflow
import numpy as np
import pandas as pd
from mlflow.models import infer_signature
from sklearn.ensemble import HistGradientBoostingRegressor

from mlops.features import FEATURE_COLS, SERIES_COLS, TARGET_COL, TIME_COL, training_frame

mlflow.set_registry_uri("databricks-uc")
MODEL_NAME = f"{MY}.demand_forecast"
client = mlflow.MlflowClient()


def _resolve(obj, name, default=None):
    """属性でもメソッドでも同じように取り出す。

    ⚠️ MLflow のバージョンによって `aliases` や `tags` が
    属性のときとメソッドのときがあるため、両方に対応させています。
    """
    value = getattr(obj, name, default)
    if callable(value):
        try:
            value = value()
        except Exception:  # noqa: BLE001
            value = default
    return value if value is not None else default


def alias_text(mv) -> str:
    """モデルバージョンのエイリアスを読みやすい文字列にする。"""
    raw = _resolve(mv, "aliases", [])
    if isinstance(raw, str):
        return raw or "-"
    try:
        names = [a if isinstance(a, str) else getattr(a, "alias", str(a)) for a in raw]
    except TypeError:
        return "-"
    return ", ".join(names) if names else "-"


def tag_text(mv, key: str, default: str = "?") -> str:
    """モデルバージョンのタグを安全に取り出す。"""
    tags = _resolve(mv, "tags", {}) or {}
    try:
        return str(tags.get(key, default))
    except AttributeError:
        return default


# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. 今の本番モデルを確認する

# COMMAND ----------

champ = client.get_model_version_by_alias(MODEL_NAME, "champion")
print(f"@champion       : バージョン {champ.version}")
print(f"  記録された MAE : {tag_text(champ, 'mae', '(なし)')}")
print(f"  記録された MASE: {tag_text(champ, 'mase', '(なし)')}")
print(f"\n登録されている全バージョン:")
for mv in client.search_model_versions(f"name='{MODEL_NAME}'"):
    print(f"  v{mv.version:<3} エイリアス: {alias_text(mv):<24} MAE: {tag_text(mv, 'mae')}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. 最新データで再学習する
# MAGIC
# MAGIC ⭐ 学習のコードは `04` とまったく同じです。**違うのは使うデータの範囲だけ**です。
# MAGIC
# MAGIC ⚠️ 比べるときの条件を揃えるため、**検証に使う期間は前回と同じ**にします。
# MAGIC 検証期間が違うと「新しい方が良い」の比較が成り立ちません。

# COMMAND ----------

pdf = spark.table(f"{MY}.fct_shipments").select(*SERIES_COLS, TIME_COL, TARGET_COL).toPandas()
feat = training_frame(pdf)

months = sorted(feat[TIME_COL].unique())
split_ym = months[-12]
train = feat[feat[TIME_COL] < split_ym]
valid = feat[feat[TIME_COL] >= split_ym]

print(f"データの最終月 : {pd.Timestamp(months[-1]).date()}")
print(f"検証の開始月   : {pd.Timestamp(split_ym).date()}  ← 前回と同じ条件で比べます")
print(f"学習 {len(train):,} 行 / 検証 {len(valid):,} 行")

# 比べる相手（「去年と同じ」）
y_valid = valid[TARGET_COL].to_numpy()
baseline_mae = float(np.mean(np.abs(y_valid - valid["lag_12"].to_numpy())))
print(f"「去年と同じ」の MAE: {baseline_mae:.2f}")

# COMMAND ----------

EXPERIMENT = f"/Users/{spark.sql('SELECT current_user()').collect()[0][0]}/需要予測ハンズオン"
mlflow.set_experiment(EXPERIMENT)

# ⭐ 再学習では設定を少し変えてみます（本番では前回のベスト設定を引き継ぐのが普通です）
params = {"max_depth": 8, "learning_rate": 0.04, "max_iter": 500}

with mlflow.start_run(run_name="再学習") as run:
    model = HistGradientBoostingRegressor(random_state=42, **params)
    model.fit(train[FEATURE_COLS], train[TARGET_COL])

    pred = np.clip(model.predict(valid[FEATURE_COLS]), 0, None)
    mae = float(np.mean(np.abs(y_valid - pred)))
    mase = mae / baseline_mae

    mlflow.log_params(params)
    mlflow.log_metrics({"mae": mae, "mase": mase, "baseline_mae": baseline_mae})
    mlflow.sklearn.log_model(
        model, name="model",
        signature=infer_signature(valid[FEATURE_COLS], pred),
        input_example=valid[FEATURE_COLS].head(3),
    )
    challenger_run_id = run.info.run_id

print(f"再学習したモデル: MAE {mae:.2f} / MASE {mase:.3f}")

# COMMAND ----------

# MAGIC %md
# MAGIC ### 新バージョンとして登録し、`@challenger` を付ける
# MAGIC
# MAGIC ⚠️ **この時点では本番は切り替わりません。** まだ挑戦者です。

# COMMAND ----------

registered = mlflow.register_model(model_uri=f"runs:/{challenger_run_id}/model", name=MODEL_NAME)
challenger_version = registered.version

client.set_registered_model_alias(MODEL_NAME, "challenger", challenger_version)
client.set_model_version_tag(MODEL_NAME, challenger_version, "mae", f"{mae:.4f}")
client.set_model_version_tag(MODEL_NAME, challenger_version, "mase", f"{mase:.4f}")
client.set_model_version_tag(MODEL_NAME, challenger_version, "baseline_mae", f"{baseline_mae:.4f}")

print(f"✅ バージョン {challenger_version} を登録し、@challenger を付けました")
print(f"⚠️ 本番（@champion）はまだバージョン {champ.version} のままです")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. ⭐ 同じ条件で比べる
# MAGIC
# MAGIC ⭐ **両方のモデルを読み込んで、同じ検証データで予測させます。**
# MAGIC 記録されたタグの数字を比べるのではなく、**その場で実際に走らせて比べる**のが確実です。
# MAGIC （前回と学習データの範囲が違う可能性があるため）

# COMMAND ----------

X_valid = valid[FEATURE_COLS]
scores = {}

for alias in ("champion", "challenger"):
    mv = client.get_model_version_by_alias(MODEL_NAME, alias)
    m = mlflow.pyfunc.load_model(f"models:/{MODEL_NAME}@{alias}")
    p = np.clip(m.predict(X_valid), 0, None)
    scores[alias] = {
        "version": mv.version,
        "mae": float(np.mean(np.abs(y_valid - p))),
    }
    scores[alias]["mase"] = scores[alias]["mae"] / baseline_mae

print(f"{'':<12} {'バージョン':>8} {'MAE':>10} {'MASE':>8}")
print("-" * 44)
print(f"{'去年と同じ':<12} {'-':>8} {baseline_mae:>10.2f} {1.000:>8.3f}")
for alias in ("champion", "challenger"):
    s = scores[alias]
    print(f"{'@' + alias:<12} {s['version']:>8} {s['mae']:>10.2f} {s['mase']:>8.3f}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. ⭐ 勝っていたら本番を入れ替える
# MAGIC
# MAGIC ⚠️ **判定の基準をコードに書いておくことが大事です。**
# MAGIC 「なんとなく良さそう」で入れ替えると、後から「なぜ変えたのか」が誰も説明できません。
# MAGIC
# MAGIC ここでの基準:
# MAGIC
# MAGIC | 条件 | 判定 |
# MAGIC |---|---|
# MAGIC | 挑戦者の MAE が本番より小さい | ⭐ 昇格 |
# MAGIC | かつ MASE が 1.0 未満（「去年と同じ」に勝っている） | ⭐ 昇格 |
# MAGIC | どちらか満たさない | ⚠️ 見送り。挑戦者は記録として残す |

# COMMAND ----------

ch, cp = scores["challenger"], scores["champion"]
improved = ch["mae"] < cp["mae"]
beats_baseline = ch["mase"] < 1.0

print(f"本番より良い       : {'✅' if improved else '❌'}  ({ch['mae']:.2f} < {cp['mae']:.2f})")
print(f"去年と同じに勝った : {'✅' if beats_baseline else '❌'}  (MASE {ch['mase']:.3f} < 1.0)")
print()

if improved and beats_baseline:
    client.set_registered_model_alias(MODEL_NAME, "champion", ch["version"])
    print(f"⭐ 昇格しました: @champion がバージョン {ch['version']} を指すようになりました")
    print("   ⭐ 05_batch_inference のコードは 1 文字も変えていませんが、")
    print("      次に実行すると自動的に新しいモデルが使われます。")
else:
    print(f"⚠️ 見送りました: @champion はバージョン {cp['version']} のままです")
    print("   挑戦者はバージョンとして残るので、後から検証できます。")

# COMMAND ----------

# MAGIC %md
# MAGIC ### 最終状態を確認する

# COMMAND ----------

for mv in sorted(client.search_model_versions(f"name='{MODEL_NAME}'"), key=lambda x: int(x.version)):
    print(f"  v{mv.version:<3} エイリアス: {alias_text(mv):<26} MAE: {tag_text(mv, 'mae')}")

from databricks.sdk import WorkspaceClient  # noqa: E402

w = WorkspaceClient()
displayHTML(
    f'<a href="{w.config.host}/explore/data/models/{catalog}/{schema}/demand_forecast" '
    'target="_blank">▶ Unity Catalog でバージョンとエイリアスを見る</a>'
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## ✅ ここまでできたら
# MAGIC
# MAGIC 次は **`07_jobs`** に進みます。
# MAGIC
# MAGIC ⭐ ここまで全部、**手で 1 つずつ実行してきました**。
# MAGIC ⚠️ このままだと来月も同じ手作業が必要です。
# MAGIC ⭐ 次はこれを**自動実行**にします。
