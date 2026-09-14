# Databricks notebook source
# MAGIC %md
# MAGIC # _uc_metadata — テーブルに「意味」を付ける
# MAGIC
# MAGIC `%run ./_config` の後に `%run ./_uc_metadata` で呼び出します。
# MAGIC 変数 `TARGET` が定義されていればそのスキーマに、無ければ自分のスキーマに適用します。
# MAGIC
# MAGIC ## なぜこれが必要なのか
# MAGIC
# MAGIC ⚠️ **説明が付いていないと、Genie Agent はまともに答えられません。**
# MAGIC
# MAGIC Genie Agent は Unity Catalog のメタデータ（テーブルの説明、メトリクスビューの
# MAGIC 軸・指標の定義と説明）を読んで SQL を組み立てます。
# MAGIC 「`qty` って何の数量？」「`ym` は年月なのか年度なのか？」が分からなければ、
# MAGIC 人間と同じように間違えます。
# MAGIC
# MAGIC ⭐ **順番が大事です**: Unity Catalog を整える → その上で Genie Agent を作る。
# MAGIC 逆順にすると「Genie の精度が出ない」とだけ言って終わってしまいます。
# MAGIC
# MAGIC ## ここでやること
# MAGIC
# MAGIC | # | 内容 | 効果 |
# MAGIC |---|---|---|
# MAGIC | 1 | テーブルに**説明**を付ける | 何のテーブルかが伝わる |
# MAGIC | 2 | **メトリクスビュー**を作る | 指標の定義・列の意味・テーブル同士の繋がりを 1 箇所にまとめられる |
# MAGIC
# MAGIC ⚠️ やりすぎないこと。説明を詰め込むほど良くなるわけではありません。
# MAGIC 「1 行で言い切る」のがコツです。
# MAGIC
# MAGIC > ⚠️ **列コメントと主キー / 外部キーは、このハンズオンでは付けられません。**
# MAGIC >
# MAGIC > gold テーブルはパイプラインが作った**マテリアライズドビュー**です。
# MAGIC > マテリアライズドビューに対しては `ALTER TABLE ... ALTER COLUMN ... COMMENT` と
# MAGIC > `ALTER TABLE ... ADD CONSTRAINT` が使えません（「これは view です」と拒否されます）。
# MAGIC >
# MAGIC > ⭐ **代わりにメトリクスビューがその役目を果たします。**
# MAGIC > メトリクスビューの YAML には ① 軸と指標の**説明** ② テーブル同士の**結合条件**の
# MAGIC > 両方を書けるので、Genie Agent に渡す情報としてはこれで足ります。

# COMMAND ----------

# MAGIC %run ./_config

# COMMAND ----------

# ⭐ 上のセルで共通設定を読み込んでいるので、このノートブックは単体でも動きます。
#    （`02_genie_agent` からは `%run ./_config` の後に呼ばれるため 2 回読まれますが、
#     何度実行しても同じ結果になる作りなので問題ありません）
#
# TARGET が未定義なら自分のスキーマに適用する
try:
    TARGET  # noqa: B018
except NameError:
    TARGET = MY

print(f"適用先: {TARGET}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. テーブルの説明

# COMMAND ----------

TABLE_COMMENTS = {
    "fct_shipments": "月次の出荷実績。品目 × チャネル × 月で 1 行。需要予測の入力になる中心テーブル。",
    "dim_item": "品目マスタ。カテゴリ・本体か消耗品か・需要の性質・国内専用かどうかを持つ。集計の軸に使う。",
    "dim_channel": "販売チャネルの定義。DOM は国内、EXP は海外。",
    "dim_lead_time": "品目と拠点の組み合わせごとの標準リードタイム日数。いつ発注すれば間に合うかの判断に使う。",
    "fct_inventory": "拠点別の月末在庫。安全在庫と欠品フラグを持つ。欠品と余剰在庫を見るためのテーブル。",
    "fct_forecast_baseline": "前年同月と同じ数量を予測値とする、最も単純な予測。作ったモデルの比較対象になる。",
    "fct_forecast_accuracy": "予測と実績を突き合わせた結果。誤差を率と個数の両方で持つ。",
}

applied, failed = 0, []
for table, comment in TABLE_COMMENTS.items():
    escaped = comment.replace("'", "''")
    try:
        spark.sql(f"COMMENT ON TABLE {TARGET}.{table} IS '{escaped}'")
        applied += 1
    except Exception as e:  # noqa: BLE001
        failed.append(f"{table}: {type(e).__name__}")

print(f"✅ テーブルの説明を {applied} 件付けました")
if failed:
    print("⚠️ 失敗:", ", ".join(failed))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. メトリクスビュー
# MAGIC
# MAGIC ⭐ **「出荷数量とは何か」「予測誤差率とは何か」の定義を 1 箇所に固定する**仕組みです。
# MAGIC
# MAGIC 同じ「売上」を人によって違う式で計算してしまう、という問題はどの会社にもあります。
# MAGIC メトリクスビューに定義を書いておくと、ダッシュボードでも Genie Agent でも
# MAGIC **同じ数字**が出ます。
# MAGIC
# MAGIC ⚠️ **メトリクスビューは 1 本につきファクトテーブル 1 つ**です。
# MAGIC 出荷実績と予測精度は別のファクトなので、2 本に分けます。
# MAGIC
# MAGIC | メトリクスビュー | 何を測るか |
# MAGIC |---|---|
# MAGIC | `mv_demand` | 出荷の数量・金額 |
# MAGIC | `mv_forecast_accuracy` | 予測の当たり具合 |
# MAGIC
# MAGIC ⚠️ 軸と指標を増やしすぎないこと。増えるほど Genie Agent は迷います。
# MAGIC
# MAGIC > ⚠️ **SQL で軸や指標を参照するときは必ずバッククォートで囲んでください。**
# MAGIC > 日本語の名前はそのまま書くと `INVALID_IDENTIFIER` になります。
# MAGIC >
# MAGIC > ```sql
# MAGIC > SELECT `品目カテゴリ`, MEASURE(`出荷数量`) AS qty
# MAGIC > FROM mv_demand GROUP BY 1
# MAGIC > ```
# MAGIC >
# MAGIC > ⭐ 別名（`AS ...`）も日本語にするならバッククォートが必要です。
# MAGIC > Genie Agent が生成する SQL は自動で正しく囲まれるので、手で書くときだけ注意します。

# COMMAND ----------

spark.sql(f"""
CREATE OR REPLACE VIEW {TARGET}.mv_demand
WITH METRICS
LANGUAGE YAML
AS $$
version: 1.1
source: {TARGET}.fct_shipments
comment: "出荷の数量と金額を、月・品目カテゴリ・チャネル別に見るための指標定義。"
joins:
  - name: dim_item
    source: {TARGET}.dim_item
    'on': source.item_code = dim_item.item_code
  - name: dim_channel
    source: {TARGET}.dim_channel
    'on': source.channel = dim_channel.channel_code
dimensions:
  - name: 年月
    expr: source.ym
    comment: "出荷が発生した月（月末日）。"
  - name: 品目カテゴリ
    expr: dim_item.item_category
    comment: "計測ユニット / 記録紙 / 電極パッド / 接続ケーブル / センサモジュール。"
  - name: チャネル
    expr: dim_channel.channel_name
    comment: "国内 または 海外。"
  - name: 国内専用品目
    expr: dim_item.is_domestic_only
    comment: "true なら海外への出荷が発生しない品目。"
measures:
  - name: 出荷数量
    expr: SUM(source.qty)
    comment: "出荷された個数の合計。"
  - name: 出荷金額
    expr: SUM(source.amount)
    comment: "出荷金額の合計（円）。"
  - name: 対象月数
    expr: COUNT(DISTINCT source.ym)
    comment: "集計に含まれる月の数。"
  - name: 月平均出荷数量
    expr: "MEASURE(`出荷数量`) / MEASURE(`対象月数`)"
    comment: "1 か月あたりの平均出荷個数。"
$$
""")
print(f"✅ {TARGET}.mv_demand を作成しました")

# COMMAND ----------

spark.sql(f"""
CREATE OR REPLACE VIEW {TARGET}.mv_forecast_accuracy
WITH METRICS
LANGUAGE YAML
AS $$
version: 1.1
source: {TARGET}.fct_forecast_accuracy
comment: "予測がどれくらい当たっているかを、率と個数の両方で見るための指標定義。"
joins:
  - name: dim_item
    source: {TARGET}.dim_item
    'on': source.item_code = dim_item.item_code
dimensions:
  - name: 対象年月
    expr: source.target_ym
    comment: "予測の対象になった月（月末日）。"
  - name: 品目カテゴリ
    expr: dim_item.item_category
  - name: 需要分類
    expr: dim_item.demand_class
    comment: "需要の性質。smooth / erratic / intermittent / lumpy / lumpy_severe。"
  - name: 予測手法
    expr: source.model_name
    comment: "予測に使った手法の名前。"
measures:
  - name: 平均誤差率
    expr: AVG(source.ape)
    comment: "予測と実績のずれを率で見た平均。⚠️ 数量の少ない品目では大きく出やすい。"
  - name: 平均誤差個数
    expr: AVG(source.abs_error)
    comment: "予測と実績のずれを個数で見た平均。少量品目でも過大評価されない。"
  - name: 予測区間的中率
    expr: AVG(source.within_interval)
    comment: "実績が予測の下限と上限の間に収まった割合。"
  - name: 予測件数
    expr: COUNT(1)
$$
""")
print(f"✅ {TARGET}.mv_forecast_accuracy を作成しました")
