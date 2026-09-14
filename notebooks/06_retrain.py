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


def all_versions(name: str) -> list:
    """登録されている全バージョンを、エイリアスとタグ込みで取得する。

    ⚠️ `search_model_versions` が返すオブジェクトには
    エイリアスとタグが入っていないため（一覧が全部 "-" や "?" になります）、
    バージョン番号だけ拾って 1 件ずつ取り直しています。
    """
    versions = [int(mv.version) for mv in client.search_model_versions(f"name='{name}'")]
    return [client.get_model_version(name, str(v)) for v in sorted(versions)]


# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. 今の本番モデルを確認する

# COMMAND ----------

champ = client.get_model_version_by_alias(MODEL_NAME, "champion")
print(f"@champion       : バージョン {champ.version}")
print(f"  記録された MAE : {tag_text(champ, 'mae', '(なし)')}")
print(f"  記録された MASE: {tag_text(champ, 'mase', '(なし)')}")
print(f"\n登録されている全バージョン:")
for mv in all_versions(MODEL_NAME):
    print(f"  v{mv.version:<3} エイリアス: {alias_text(mv):<24} MAE: {tag_text(mv, 'mae')}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. 最新データで再学習する
# MAGIC
# MAGIC ⭐ 学習のコードは `04` とまったく同じです。**違うのは使うデータの範囲だけ**です。
# MAGIC
# MAGIC ### ⭐⭐ 本番モデルは「古い」
# MAGIC
# MAGIC `04` で作った本番モデルは、**半年前までのデータしか見ていません**（上に表示されています）。
# MAGIC その後の半年分のデータを、本番モデルは知りません。
# MAGIC
# MAGIC ```
# MAGIC   本番モデル  |------- 学習 -------|-- 検証 --|          （ここまでしか知らない）
# MAGIC   今回        |----------- 学習 -----------|-- 検証 --|  （最新まで使う）
# MAGIC                                             ↑ この期間で両方を比べます
# MAGIC ```
# MAGIC
# MAGIC ⚠️ **比べる期間は両モデルで同じ**にします。学習に使った範囲は違っても、
# MAGIC 採点の問題用紙が同じでなければ公平になりません。

# COMMAND ----------

pdf = spark.table(f"{MY}.fct_shipments").select(*SERIES_COLS, TIME_COL, TARGET_COL).toPandas()
feat = training_frame(pdf)

VALID_MONTHS = 12
# ⭐ 昇格の判定は「直近 3 か月」で行います（理由は下の「4.」を読んでください）
RECENT_MONTHS = 3

months = sorted(feat[TIME_COL].unique())
# ⭐ 今回は最新までのデータを全部使う。検証は直近 12 か月。
split_ym = months[-VALID_MONTHS]
train = feat[feat[TIME_COL] < split_ym]
valid = feat[feat[TIME_COL] >= split_ym]
# ⭐ 昇格の判定に使う「直近」の窓
recent = feat[feat[TIME_COL] >= months[-RECENT_MONTHS]]

champ_trained_through = tag_text(champ, "trained_through", "(不明)")
new_trained_through = str(pd.Timestamp(train[TIME_COL].max()).date())

print(f"データの最終月                  : {pd.Timestamp(months[-1]).date()}")
print(f"⚠️ 本番モデルが学習に使った最終月 : {champ_trained_through}")
print(f"⭐ 今回学習に使う最終月          : {new_trained_through}")
print(f"   → 本番モデルより新しいデータを見ています")
print(f"両モデルを比べる期間            : {pd.Timestamp(split_ym).date()} 〜 "
      f"{pd.Timestamp(months[-1]).date()}  （同じ問題用紙で採点します）")
print(f"⭐ 昇格の判定に使う期間          : {pd.Timestamp(months[-RECENT_MONTHS]).date()} 〜 "
      f"{pd.Timestamp(months[-1]).date()}  （直近 {RECENT_MONTHS} か月）")
print(f"学習 {len(train):,} 行 / 検証 {len(valid):,} 行 / 直近 {len(recent):,} 行")

# 比べる相手（「去年と同じ」）を 2 つの期間で
y_valid = valid[TARGET_COL].to_numpy()
y_recent = recent[TARGET_COL].to_numpy()
baseline_mae = float(np.mean(np.abs(y_valid - valid["lag_12"].to_numpy())))
baseline_recent = float(np.mean(np.abs(y_recent - recent["lag_12"].to_numpy())))
print(f"「去年と同じ」の MAE: 12 か月 {baseline_mae:.2f} / 直近 {RECENT_MONTHS} か月 {baseline_recent:.2f}")

# COMMAND ----------

EXPERIMENT = f"/Users/{spark.sql('SELECT current_user()').collect()[0][0]}/需要予測ハンズオン"
mlflow.set_experiment(EXPERIMENT)

# ⭐⭐ 再学習では **今の本番と同じ設定**を引き継ぎます。
#
# ⚠️ ここで設定も一緒に変えてしまうと、成績が変わった理由が
#    「データが新しくなったから」なのか「設定を変えたから」なのか
#    分からなくなります。
# ⭐ 「設定は据え置き、データだけ新しくする」のが再学習の基本形です。
champ_run = client.get_run(champ.run_id)
INHERIT = ("max_depth", "learning_rate", "max_iter")
params = {
    k: (int(v) if k in ("max_depth", "max_iter") else float(v))
    for k, v in champ_run.data.params.items()
    if k in INHERIT
}
if not params:
    # 本番モデルに設定が記録されていない場合の保険
    params = {"max_depth": 6, "learning_rate": 0.05, "max_iter": 400}
    print("⚠️ 本番モデルの設定が読めなかったので既定値を使います")

print("引き継いだ設定:", params)

with mlflow.start_run(run_name="再学習") as run:
    model = HistGradientBoostingRegressor(random_state=42, **params)
    model.fit(train[FEATURE_COLS], train[TARGET_COL])

    pred = np.clip(model.predict(valid[FEATURE_COLS]), 0, None)
    mae = float(np.mean(np.abs(y_valid - pred)))
    mase = mae / baseline_mae

    mlflow.log_params(params)
    mlflow.log_param("trained_through", new_trained_through)
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
client.set_model_version_tag(
    MODEL_NAME, challenger_version, "trained_through", new_trained_through)

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

scores = {}

for alias in ("champion", "challenger"):
    mv = client.get_model_version_by_alias(MODEL_NAME, alias)
    m = mlflow.pyfunc.load_model(f"models:/{MODEL_NAME}@{alias}")
    p_valid = np.clip(m.predict(valid[FEATURE_COLS]), 0, None)
    p_recent = np.clip(m.predict(recent[FEATURE_COLS]), 0, None)
    mae_v = float(np.mean(np.abs(y_valid - p_valid)))
    mae_r = float(np.mean(np.abs(y_recent - p_recent)))
    scores[alias] = {
        "version": mv.version,
        "trained_through": tag_text(mv, "trained_through", "?"),
        "mae": mae_v,
        "mase": mae_v / baseline_mae,
        "mae_recent": mae_r,
        "mase_recent": mae_r / baseline_recent,
    }

print(f"{'':<12} {'版':>4} {'学習の最終月':>13} "
      f"{'12か月MAE':>10} {'MASE':>7} | {'直近MAE':>9} {'直近MASE':>9}")
print("-" * 78)
print(f"{'去年と同じ':<12} {'-':>4} {'-':>13} "
      f"{baseline_mae:>10.2f} {1.000:>7.3f} | {baseline_recent:>9.2f} {1.000:>9.3f}")
for alias in ("champion", "challenger"):
    s = scores[alias]
    print(f"{'@' + alias:<12} {s['version']:>4} {s['trained_through']:>13} "
          f"{s['mae']:>10.2f} {s['mase']:>7.3f} | {s['mae_recent']:>9.2f} {s['mase_recent']:>9.3f}")

# COMMAND ----------

# MAGIC %md
# MAGIC ### ⭐ グラフで比べる
# MAGIC
# MAGIC ⭐ **棒が低い方が良い**（誤差が小さい）。
# MAGIC 「去年と同じ」の棒より低くなっていなければ、そのモデルは使う意味がありません。

# COMMAND ----------

import os
import sys

_p = dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
_root = os.path.normpath(os.path.join(os.path.dirname(_p), ".."))
_src = f"/Workspace{_root}/src" if not _root.startswith("/Workspace") else f"{_root}/src"
if _src not in sys.path:
    sys.path.insert(0, _src)

from mlops.plots import plot_grouped_bars  # noqa: E402

# 上の比較セルで求めた scores から取り出す
_cp, _ch = scores["champion"], scores["challenger"]

compare = pd.DataFrame({
    "model": [
        "baseline (last year)",
        f"@champion v{_cp['version']}",
        f"@challenger v{_ch['version']}",
    ],
    "last 12 months": [baseline_mae, _cp["mae"], _ch["mae"]],
    "last 3 months": [baseline_recent, _cp["mae_recent"], _ch["mae_recent"]],
})
display(plot_grouped_bars(
    compare, "model", ["last 12 months", "last 3 months"],
    "mean absolute error — 12 months vs the last 3 (lower is better)",
    ylabel="mean absolute error (units)",
))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. ⭐ 勝っていたら本番を入れ替える
# MAGIC
# MAGIC ⚠️ **判定の基準をコードに書いておくことが大事です。**
# MAGIC 「なんとなく良さそう」で入れ替えると、後から「なぜ変えたのか」が誰も説明できません。
# MAGIC
# MAGIC ### ⭐⭐ 判定は「直近 3 か月」で行います
# MAGIC
# MAGIC ⚠️ **12 か月平均で比べると、古いモデルの方が良く見えることがあります。**
# MAGIC
# MAGIC 理由は、このモデルが **前月・前年同月・移動平均**を特徴量に使っているからです。
# MAGIC 推論のたびに**最新の実績が特徴量として入ってくる**ので、
# MAGIC 「学習したのが半年前」でも直近の動きはある程度追えてしまいます。
# MAGIC
# MAGIC ⭐ これ自体は良いこと（急に壊れない）ですが、
# MAGIC ⚠️ **12 か月を平均すると「新しくした効果」が薄まって見えなくなります。**
# MAGIC
# MAGIC ⭐ 知りたいのは「**今どうか**」なので、**直近 3 か月**で判定します。
# MAGIC 12 か月の数字も参考として並べて表示します。
# MAGIC
# MAGIC | 条件 | 判定 |
# MAGIC |---|---|
# MAGIC | ⭐ **直近 3 か月の MAE** が本番より小さい | ⭐ 昇格 |
# MAGIC | かつ 直近の MASE が 1.0 未満（「去年と同じ」に勝っている） | ⭐ 昇格 |
# MAGIC | どちらか満たさない | ⚠️ 見送り。挑戦者は記録として残す |
# MAGIC
# MAGIC > ⭐ **今回は挑戦者が勝つはずです。** 本番モデルは半年前までのデータしか
# MAGIC > 見ていないので、その後の変化に追いつけていません。
# MAGIC > **これが「モデルは作った瞬間から古くなる」の中身です。**
# MAGIC >
# MAGIC > ⚠️ ただし**いつも勝つわけではありません。** 需要の傾向が変わっていなければ
# MAGIC > 古いモデルでも十分で、見送りになります。
# MAGIC > ⭐ **見送りも正しい結果です。**「作り直したのに良くならなかった」が記録に残り、
# MAGIC > 本番は据え置かれる——これが仕組みで守られている状態です。
# MAGIC > ⚠️ 人の判断でやっていると、ここで「せっかく作ったから入れ替えよう」が起きます。
# MAGIC
# MAGIC > 💡 判定は**タグに記録された数字ではなく、その場で両モデルを走らせた結果**で
# MAGIC > 行っています。学習データの範囲が違う可能性があるため、記録の数字同士を
# MAGIC > 比べるのは公平ではありません。

# COMMAND ----------

ch, cp = scores["challenger"], scores["champion"]
# ⭐ 判定は直近 3 か月で行う
improved = ch["mae_recent"] < cp["mae_recent"]
beats_baseline = ch["mase_recent"] < 1.0

print(f"直近で本番より良い : {'✅' if improved else '❌'}  "
      f"({ch['mae_recent']:.2f} < {cp['mae_recent']:.2f})")
print(f"去年と同じに勝った : {'✅' if beats_baseline else '❌'}  "
      f"(直近 MASE {ch['mase_recent']:.3f} < 1.0)")
print(f"（参考）12 か月平均 : 挑戦者 {ch['mae']:.2f} / 本番 {cp['mae']:.2f}")
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

for mv in all_versions(MODEL_NAME):
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
