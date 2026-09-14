# Databricks notebook source
# MAGIC %md
# MAGIC # 99 — 自分のデータで試す（自由時間）
# MAGIC
# MAGIC > ⏱ **目安 30 分**
# MAGIC
# MAGIC ⭐ ここまではこちらが用意したデータでした。
# MAGIC **自分の手元にあるデータ**で、今日やったことをもう一度やってみます。
# MAGIC
# MAGIC ## ⭐⭐ この時間の目的
# MAGIC
# MAGIC ⚠️ **手でコードを書き直すことではありません。**
# MAGIC
# MAGIC > ⭐⭐ **Genie Code に自然言語で頼んで作らせる。**
# MAGIC
# MAGIC ## ⭐ 進め方 — ここまでできれば十分です
# MAGIC
# MAGIC | | 内容 | 目安 |
# MAGIC |---|---|---|
# MAGIC | 1〜5 | ⭐ **テーブルを作る**（CSV を置く → 列を合わせる → 保存） | 10 分 |
# MAGIC | ⭐ 6-A | ⭐⭐ **ダッシュボードを作る**（自然言語で） | 8 分 |
# MAGIC | ⭐ 6-B | ⭐⭐ **Genie Agent を作る**（自然言語で） | 10 分 |
# MAGIC | 6-C | ⚠️ **おまけ** — 予測・モデル・自動化（時間が余ったら） | — |
# MAGIC
# MAGIC ⭐⭐ **メインはこの 3 つです**: テーブル作成 → ダッシュボード → Genie Agent。
# MAGIC ⚠️ **それ以降は無理に進めなくて大丈夫です。**
# MAGIC
# MAGIC ⭐ プロンプトは全部用意してあります（下のセルが出力します）。
# MAGIC 💡 `prompts/genie_code_free_play.md` にもまとまっています。
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
# MAGIC > ⭐ **ここはあなた専用の Volume です。** 他の参加者には見えません。
# MAGIC
# MAGIC > ⚠️ **社外に出せないデータは置かないでください。** この環境は検証用です。
# MAGIC > 迷ったら、数行だけ抜いたサンプルにするか、数値を変えたものを使ってください。
# MAGIC
# MAGIC > ⭐⭐ **手元にデータが無い方へ — 練習用の CSV を用意してあります。**
# MAGIC >
# MAGIC > リポジトリの **`data/sample_own_data.csv`**（4 品目 × 30 か月）をダウンロードして
# MAGIC > アップロードしてください。⭐ **列名がこのノートブックの既定と揃っている**ので、
# MAGIC > そのまま通ります。
# MAGIC >
# MAGIC > ⚠️ わざと「実データっぽい形」にしてあります:
# MAGIC > **列名が日本語** / **年月が `2024年1月` 形式** / **数量に桁区切り (`2,155`)** /
# MAGIC > ⭐ **出ない月がある品目つき**

# COMMAND ----------

MY_UPLOAD_DIR = f"{LANDING_PATH}/your_own_data"
dbutils.fs.mkdirs(MY_UPLOAD_DIR)
print("CSV をここにアップロードしてください:")
print(f"  {MY_UPLOAD_DIR}")
print()
print("カタログ画面での場所:")
print(f"  {catalog}  →  {schema}  →  ボリューム  →  {LANDING_VOLUME}  →  your_own_data")

from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
displayHTML(
    f'<a href="{w.config.host}/explore/data/volumes/{catalog}/{schema}/{LANDING_VOLUME}" '
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
MY_FILE = files[0] if files else None

if MY_FILE is None:
    print("⚠️ まだファイルがありません。上の手順で CSV をアップロードしてから、")
    print("   このセル以降をもう一度実行してください。")
    dbutils.notebook.exit("no file uploaded yet")

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
# MAGIC ## 6. ⭐⭐ ここから Genie Code で遊ぶ
# MAGIC
# MAGIC ⭐ **下のセルを実行すると、自分のテーブル名が入ったプロンプトが出ます。**
# MAGIC それを Genie Code にそのまま貼ってください。
# MAGIC
# MAGIC ⭐⭐ **メインは ⓪ → ① → ② → ③ の 4 つ**（データ理解 → ダッシュボード →
# MAGIC メタデータ → Genie Agent）。⚠️ **④ 以降はおまけです。**
# MAGIC
# MAGIC ### ⚠️ コツは 3 つだけ
# MAGIC
# MAGIC | | |
# MAGIC |---|---|
# MAGIC | 1 | ⚠️ **一度に全部頼まない。** ⓪ から順に 1 つずつ |
# MAGIC | 2 | ⭐ **⓪ と ② を先にやる。** データの理解とメタデータで後の精度が決まります |
# MAGIC | 3 | ⭐ **質問されたら答える。** それがこの時間の体験そのものです |
# MAGIC
# MAGIC > ⭐ Genie Code は右上のランプのアイコン、または左メニューから開きます。

# COMMAND ----------

MAIN_PROMPTS = [
    ("⓪ まずデータを理解させる（最初にやると精度が上がります）", """
テーブル {t} の中身を調べて、次を教えてください。

- 各列の意味の推測と、欠損・重複の有無
- 系列の数と、1 系列あたりの月数の分布
- 数量の分布（ゼロが多い系列があるか）
- ⭐ 需要の性質で系列を分類してください
  （毎月安定 / 数量が振れる / 出ない月がある）

結果は表で見せてください。
"""),
    ("① ダッシュボードを作る（01 に相当）", """
{t} を使って AI/BI ダッシュボードを作ってください。

- 上部に KPI: 総数量 / 系列数 / 直近月の数量
- 月ごとの数量推移（折れ線）
- 品目上位 10 件の数量（棒）
- 数量上位の系列の表

タイトルと軸ラベルは日本語にしてください。
"""),
    ("② メタデータとメトリクスビューを作る（Genie の精度はここで決まる）", """
{t} に、Genie Agent が正しく答えられるようメタデータを付けてください。

- テーブルと全列に日本語のコメントを付ける
- 数量・年月・品目・チャネルに相当する列が何かを明示する
- ⭐ メトリクスビューを 1 つ作ってください
  - 軸: 年月 / 品目 / チャネル
  - 指標: 合計数量 / 月平均数量 / 系列数
"""),
    ("③ Genie Agent を作る（02 に相当）", """
② で作ったメトリクスビューを使う Genie Agent を作ってください。

- 渡すのはメトリクスビューだけにする（生テーブルは渡さない）
- 指示: 回答は日本語 / 数量は整数 / 比率は小数第 1 位まで
- 動作確認用に、業務で聞きたくなる質問を 5 つ提案してください
"""),
]

# ⚠️ ここから下は「おまけ」。時間が余った人だけ。
OPTIONAL_PROMPTS = [
    ("④ SQL 1 文で予測する（03 に相当）", """
{t} に対して ai_forecast() で 12 か月先まで予測する SQL を書いてください。

- 系列は品目 × チャネル（group_col）
- 月次
- ⚠️ horizon は「何期先」ではなく終端の日付で渡すこと
- ⚠️ frequency は 'ME'
- SQL ウェアハウスで実行できる形にしてください

結果を可視化するグラフも作ってください。
"""),
    ("⑤ モデルを作って記録・登録する（04 に相当）", """
{t} で需要予測モデルを作ってください。

- ⭐ 特徴量は関数に切り出して、学習と推論で同じものを使えるようにする
  （ラグ 1/2/3/12 か月、移動平均、移動標準偏差、非ゼロ比率、月、通し番号）
- ⚠️ 移動平均は当月を含めない（答えを見ないようにする）
- 検証は直近 12 か月
- ⭐⭐ 「前年同月と同じ」というベースラインを先に計算し、必ず並べて比較する
- 条件を変えて 3 回学習し、MLflow に記録する
- いちばん良いものを Unity Catalog に登録して @champion を付ける
- MAE と MASE をタグに残す
"""),
    ("⑥ まとめて推論し、精度を記録する（05 に相当）", """
@champion を名前で呼び出して、実績のある全期間の予測を作り直してください。

- 予測を {s}.my_forecast_model に書き出す
- ⭐ 予測と実績を突き合わせた評価テーブルも作る
  （誤差率と誤差個数の両方を持たせること）
- ⭐ ベースラインとモデルを需要の性質ごとに比較する表を作る
- グラフも作る: 予測 vs 実績の散布図 / 月ごとの誤差推移
"""),
    ("⑦ 再学習して、勝ったら入れ替える（06 に相当）", """
再学習して本番と比較するノートブックを作ってください。

- 最新までのデータで学習し、新バージョンとして登録して @challenger を付ける
- ⚠️ 設定（ハイパーパラメータ）は今の @champion から引き継ぐ
  （データを新しくした効果だけを見たいので）
- ⭐ 両モデルを同じ検証データで実際に走らせて比較する
- ⭐ 判定は直近 3 か月で行う。基準を満たしたら @champion を付け替える
- 満たさなければ据え置き、その旨を出力する
"""),
    ("⑧ 自動実行にする（07 に相当）", """
⑥ と ⑦ を毎月自動で回すジョブを作ってください。

- タスク: データ取り込み → 再学習と昇格判定 → 推論と評価の更新
- ⭐ 新しいファイルが置かれたら動くトリガーを付ける
- ⚠️ 失敗したらメールが飛ぶようにする
- Databricks Asset Bundle の YAML としても書き出してください
"""),
    ("⑨ 品目ごとに手法を選ぶ（08 に相当）", """
{t} の系列を性質で分類し、⭐ 系列ごとに向いている予測手法を割り当てる方針を
提案してください。

- 予測しやすい系列とそうでない系列に分ける
- ⚠️ 予測しにくい系列は「当てにいかない」選択肢も含めて検討する
  （前年同月そのまま / 平均 / ゼロ）
- どの系列にどの手法を当てたかが後から分かる形で記録する
"""),
]

def show(prompts, header):
    print("#" * 78)
    print(f"#  {header}")
    print("#" * 78)
    print()
    for title, body in prompts:
        print("=" * 78)
        print(f"  {title}")
        print("=" * 78)
        print(body.format(t=TABLE_NAME, s=MY))


show(MAIN_PROMPTS, "⭐⭐ メイン — この 4 つを順にやってください")
print()
print()
show(OPTIONAL_PROMPTS, "⚠️ おまけ — 時間が余ったら。全部やる必要はありません")

# COMMAND ----------

# MAGIC %md
# MAGIC ## ⚠️ うまくいかないときのコツ
# MAGIC
# MAGIC | ⚠️ 症状 | ⭐ 対処 |
# MAGIC |---|---|
# MAGIC | 的が外れた答えが返る | ⭐ **1 つずつ頼む。** ⓪→①→② の順を守る |
# MAGIC | 列の意味を誤解される | ⭐ **⓪ と ② を先にやる。** メタデータが効きます |
# MAGIC | 日本語の列名でエラー | ⚠️ **バッククォートで囲むよう指示する** |
# MAGIC | 月数が足りないと言われる | ⚠️ ラグ 12 か月を使うため **各系列 24 か月以上**必要。⭐ 足りなければ ④ の `ai_forecast` を試す |
# MAGIC | そもそもデータが汚い | ⭐ **⓪ の結果を見せて「まず整えて」と頼む** |
# MAGIC
# MAGIC ### ⭐ うまくいかない方が学びになります
# MAGIC
# MAGIC 実データは必ず想定と違う形をしています。
# MAGIC ⭐ **「どこで詰まったか」を持ち帰っていただくのが、この時間のいちばんの目的です。**
# MAGIC 詰まったところは遠慮なく声をかけてください。
