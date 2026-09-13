# Databricks notebook source
# MAGIC %md
# MAGIC # 99 — 自分のデータで試す（自由時間）
# MAGIC
# MAGIC > ⏱ **目安 30 分**
# MAGIC
# MAGIC ⭐ ここまではこちらが用意したデータでした。
# MAGIC **自分の手元にあるデータ**を取り込んで、今日やったことを試してみてください。
# MAGIC
# MAGIC ## 進め方
# MAGIC
# MAGIC | | 内容 |
# MAGIC |---|---|
# MAGIC | 1 | CSV を Volume に置く（画面から） |
# MAGIC | 2 | 読み込んで中身を確認する |
# MAGIC | 3 | ⭐ 列名を合わせて、自分のスキーマにテーブルとして保存する |
# MAGIC | 4 | ⭐ そのまま `01`〜`06` と同じことを試す |
# MAGIC
# MAGIC > ⚠️ **うまくいかないときは遠慮なく声をかけてください。**
# MAGIC > 実データは必ず「想定と違う形」をしています。そこが今日いちばん学びになる部分です。

# COMMAND ----------

# MAGIC %run ./_config

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. CSV を Volume に置く
# MAGIC
# MAGIC ### 手順
# MAGIC
# MAGIC 1. 左メニュー **「カタログ」** を開く
# MAGIC 2. 下のセルに出るパスまで降りる
# MAGIC 3. 右上 **「このボリュームにアップロード」** から CSV を選ぶ
# MAGIC
# MAGIC > ⚠️ **他の参加者も同じ場所を使います。** ファイル名に自分の名前を入れてください。
# MAGIC > 例: `yamada_売上実績.csv`
# MAGIC
# MAGIC > ⚠️ **社外に出せないデータは置かないでください。** この環境は検証用です。
# MAGIC > 迷ったら、数行だけ抜いたサンプルにするか、数値を変えたものを使ってください。

# COMMAND ----------

MY_UPLOAD_DIR = f"{LANDING_PATH}/your_own_data"
print("CSV をここにアップロードしてください:")
print(f"  {MY_UPLOAD_DIR}")
print()
print("カタログ画面での場所:")
print(f"  {catalog}  →  {SHARED_SCHEMA}  →  ボリューム  →  {LANDING_VOLUME}  →  your_own_data")

from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
displayHTML(
    f'<a href="{w.config.host}/explore/data/volumes/{catalog}/{SHARED_SCHEMA}/{LANDING_VOLUME}" '
    'target="_blank">▶ Volume を画面で開く</a>'
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. 置いたファイルを確認する

# COMMAND ----------

import os

files = sorted(os.listdir(MY_UPLOAD_DIR)) if os.path.isdir(MY_UPLOAD_DIR) else []
if files:
    print(f"{len(files)} 件のファイルがあります:")
    for f in files:
        size = os.path.getsize(f"{MY_UPLOAD_DIR}/{f}")
        print(f"  {f:<50} {size:>12,} bytes")
else:
    print("⚠️ まだファイルがありません。上の手順でアップロードしてください。")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. 読み込んで中身を見る
# MAGIC
# MAGIC ⭐ 下の `MY_FILE` に自分のファイル名を入れて実行してください。
# MAGIC
# MAGIC ### ⚠️ 実データでよくつまずくところ
# MAGIC
# MAGIC | ⚠️ 症状 | 対処 |
# MAGIC |---|---|
# MAGIC | 日本語が化ける | `encoding` を `Shift_JIS` や `CP932` にする（下のセルで切り替えられます） |
# MAGIC | 先頭に説明行がある | `skipRows` で読み飛ばす |
# MAGIC | 数値がカンマ区切りで文字列になる | 読み込んだ後に `replace(',', '')` して数値化する |
# MAGIC | 年月が「2026年4月」「2026/4」など | 下のセルで月末日に変換します |
# MAGIC | 月ごとに別ファイル・形式が違う | ⭐ **まず 1 ファイルだけで通してから増やす** |

# COMMAND ----------

# ★ 自分のファイル名に書き換えてください
MY_FILE = files[0] if files else "your_file.csv"

# ★ 日本語が化けたら "Shift_JIS" や "CP932" に変えてください
ENCODING = "UTF-8"
# ★ 先頭に説明行があるときは行数を入れてください
SKIP_ROWS = 0

print(f"読み込むファイル: {MY_FILE}（encoding={ENCODING}, skipRows={SKIP_ROWS}）")

raw = (
    spark.read.format("csv")
    .option("header", "true")
    .option("encoding", ENCODING)
    .option("skipRows", SKIP_ROWS)
    .option("inferSchema", "true")
    .load(f"{MY_UPLOAD_DIR}/{MY_FILE}")
)

print(f"\n行数: {raw.count():,}")
print("列:")
for f in raw.schema.fields:
    print(f"  {f.name:<30} {f.dataType.simpleString()}")
display(raw.limit(20))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. ⭐ 列名を今日の形に合わせる
# MAGIC
# MAGIC 今日使ったテーブルは、この 4 列だけあれば同じことができます。
# MAGIC
# MAGIC | 必要な列 | 意味 |
# MAGIC |---|---|
# MAGIC | `item_code` | 品目や商品を識別するもの |
# MAGIC | `channel` | チャネル・拠点・得意先など（無ければ固定値でよい） |
# MAGIC | `ym` | 年月（⭐ **月末日**に揃えます） |
# MAGIC | `qty` | 数量 |
# MAGIC
# MAGIC ⭐ 下のセルで、自分のデータの列名を左側に書いてください。

# COMMAND ----------

# ★ 左が「今日の形の列名」、右が「自分のデータの列名」
COLUMN_MAP = {
    "item_code": "商品コード",     # ← 自分のデータの列名に書き換え
    "channel":   None,             # ← 無ければ None（固定値 'ALL' になります）
    "ym":        "年月",           # ← 自分のデータの列名に書き換え
    "qty":       "数量",           # ← 自分のデータの列名に書き換え
}

from pyspark.sql import functions as F

available = set(raw.columns)
missing = [v for v in COLUMN_MAP.values() if v is not None and v not in available]
if missing:
    print(f"⚠️ 見つからない列があります: {missing}")
    print(f"   実際の列名: {sorted(available)}")
    print("   COLUMN_MAP を直してから再実行してください。")
else:
    df = raw.select(
        F.col(COLUMN_MAP["item_code"]).cast("string").alias("item_code"),
        (F.lit("ALL") if COLUMN_MAP["channel"] is None
         else F.col(COLUMN_MAP["channel"]).cast("string")).alias("channel"),
        # ⭐ 年月を月末日に揃える。文字列でも日付でも通るように to_date を通します。
        F.last_day(F.coalesce(
            F.to_date(F.col(COLUMN_MAP["ym"])),
            F.to_date(F.regexp_replace(F.col(COLUMN_MAP["ym"]).cast("string"),
                                       r"[年/\.]", "-"), "yyyy-M"),
        )).alias("ym"),
        # ⭐ カンマ区切りの数値にも耐えるようにしておきます
        F.regexp_replace(F.col(COLUMN_MAP["qty"]).cast("string"), ",", "")
         .cast("double").alias("qty"),
    )
    display(df.limit(20))
    bad_ym = df.filter(F.col("ym").isNull()).count()
    bad_qty = df.filter(F.col("qty").isNull()).count()
    print(f"\n年月が変換できなかった行: {bad_ym:,}")
    print(f"数量が変換できなかった行: {bad_qty:,}")
    if bad_ym or bad_qty:
        print("⚠️ 変換できない行があります。元の値を確認してください。")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. 自分のスキーマにテーブルとして保存する
# MAGIC
# MAGIC ⭐ ここまで来れば、今日やったことが全部そのまま使えます。

# COMMAND ----------

TABLE_NAME = f"{MY}.my_shipments"

if not missing:
    (df.groupBy("item_code", "channel", "ym")
       .agg(F.sum("qty").alias("qty"))
       .write.mode("overwrite").option("overwriteSchema", "true")
       .saveAsTable(TABLE_NAME))
    spark.sql(f"COMMENT ON TABLE {TABLE_NAME} IS '自分で持ち込んだデータ。品目 × チャネル × 月で集計済み。'")
    n = spark.table(TABLE_NAME).count()
    print(f"✅ {TABLE_NAME} に {n:,} 行を保存しました")
    display(spark.sql(f"""
        SELECT
          COUNT(DISTINCT item_code) AS `品目数`,
          COUNT(DISTINCT channel)   AS `チャネル数`,
          MIN(ym)                   AS `最初の月`,
          MAX(ym)                   AS `最後の月`,
          COUNT(DISTINCT ym)        AS `月数`
        FROM {TABLE_NAME}
    """))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6. ⭐ ここから何を試すか
# MAGIC
# MAGIC | やりたいこと | 参考 | 変えるところ |
# MAGIC |---|---|---|
# MAGIC | ダッシュボードを作る | `01_dashboard` | データソースに `my_shipments` を選ぶ |
# MAGIC | Genie Agent で聞く | `02_genie_agent` | `my_shipments` を渡す（⭐ 列の説明を付けると精度が上がります） |
# MAGIC | SQL 1 文で予測 | `03_ai_forecast` | `fct_shipments` を `my_shipments` に置き換える |
# MAGIC | モデルを作る | `04_train_register` | 同じく置き換え。⚠️ **月数が少ないと特徴量が作れません**（最低 24 か月ほど必要） |
# MAGIC
# MAGIC ### ⚠️ 月数が足りないとき
# MAGIC
# MAGIC 今日の特徴量は**前年同月**を使うため、各系列に **最低 13 か月**、
# MAGIC 学習と検証に分けるなら **24 か月以上**が必要です。
# MAGIC ⭐ 足りない場合は `03_ai_forecast` の方法（SQL 1 文）を試してください。
# MAGIC こちらは短い系列でも動きます。
# MAGIC
# MAGIC ### ⭐ うまくいかない方が学びになります
# MAGIC
# MAGIC 実データは必ず想定と違う形をしています。
# MAGIC 「**どこで詰まったか**」を持ち帰っていただくのが、この時間のいちばんの目的です。
# MAGIC 詰まったところは遠慮なく声をかけてください。
