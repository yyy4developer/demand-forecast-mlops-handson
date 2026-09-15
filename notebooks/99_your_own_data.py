# Databricks notebook source
# MAGIC %md
# MAGIC # 99 — 自分のデータで自由に試す
# MAGIC
# MAGIC > ⏱ **目安 30 分**
# MAGIC
# MAGIC ⭐⭐ **Genie Code に言葉で頼んで作ってもらいます。** コードは書きません。
# MAGIC
# MAGIC | | 内容 |
# MAGIC |---|---|
# MAGIC | 1 | CSV を自分の Volume に置く（⭐ ここだけ手作業） |
# MAGIC | ⭐ 2 | ⭐⭐ **Genie Code に頼む**（テーブル → ダッシュボード → Genie Agent） |
# MAGIC
# MAGIC ⚠️ **決まった手順はありません。** ⭐ 下の例文を出発点に、自由に試してください。
# MAGIC
# MAGIC > ⭐ Genie Code は右上のランプのアイコン、または左メニューから開きます。

# COMMAND ----------

# MAGIC %run ./_config

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. CSV を自分の Volume に置く
# MAGIC
# MAGIC 1. 左メニュー **「カタログ」** → 下のセルに出るパスまで降りる
# MAGIC 2. 右上 **「このボリュームにアップロード」** から CSV を選ぶ
# MAGIC
# MAGIC > ⭐ **ここはあなた専用の Volume です。** 他の参加者には見えません。
# MAGIC
# MAGIC > ⚠️ **社外に出せないデータは置かないでください。** この環境は検証用です。
# MAGIC
# MAGIC > ⭐ **手元にデータが無い方**は、リポジトリの **`data/sample_own_data.csv`**
# MAGIC > （4 品目 × 30 か月）を使ってください。
# MAGIC > ⚠️ わざと実データっぽく、**日本語の列名 / `2024年1月` 形式 / 桁区切り `2,155` /
# MAGIC > 出ない月がある品目**を入れてあります。

# COMMAND ----------

import os

MY_UPLOAD_DIR = f"{LANDING_PATH}/your_own_data"
dbutils.fs.mkdirs(MY_UPLOAD_DIR)

files = sorted(os.listdir(MY_UPLOAD_DIR)) if os.path.isdir(MY_UPLOAD_DIR) else []

print("アップロード先")
print(f"  {MY_UPLOAD_DIR}")
print(f"  （カタログ画面: {catalog} → {schema} → ボリューム → {LANDING_VOLUME} → your_own_data）")
print()
if files:
    print("置かれているファイル:")
    for f in files:
        print(f"  ✅ {f}")
else:
    print("⚠️ まだファイルがありません。上の手順でアップロードしてください。")

# ⚠️ テーブル名は決めません。⭐ Genie Code に中身を見て付けてもらいます。
MY_FILE = files[0] if files else "<ファイル名>"
CSV = f"{MY_UPLOAD_DIR}/{MY_FILE}"

print()
print("⭐ プロンプトに使う値（次のセルにも出ます）")
print(f"  CSV        : {CSV}")
print(f"  作成先スキーマ: {MY}")

from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
displayHTML(
    f'<a href="{w.config.host}/explore/data/volumes/{catalog}/{schema}/{LANDING_VOLUME}" '
    'target="_blank">▶ Volume を画面で開く</a>'
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. ⭐⭐ Genie Code に頼む
# MAGIC
# MAGIC ⭐ 下のセルが**例文**を出します。そのまま貼っても、自分の言葉に変えても構いません。
# MAGIC
# MAGIC ### ⚠️ コツは 3 つだけ
# MAGIC
# MAGIC | | |
# MAGIC |---|---|
# MAGIC | 1 | ⚠️ **1 つずつ頼む**（一度に全部頼むと的が外れます） |
# MAGIC | 2 | ⭐ **質問されたら答える**（それがこの時間の体験です） |
# MAGIC | 3 | ⭐ **おかしければ「〜が違う」と言い直す**（会話で直すのが本来の使い方） |
# MAGIC
# MAGIC > ⭐ **Genie Agent を作る前に、列コメントとメトリクスビューを頼んでください。**
# MAGIC > ⭐ 順番は ① 中身を見る → ② テーブル → ③ ダッシュボード → ④ 意味を付ける → ⑤ Genie Agent。
# MAGIC > ⚠️ `02` でやったとおり、ここを飛ばすと答えの精度が出ません。

# COMMAND ----------

print("=" * 78)
print("  ⭐⭐ プロンプト例（メイン）")
print("=" * 78)
print(f"""
① まず中身を見てもらう
   {CSV}
   このファイルの中身を見て、各列が何を表しているか教えてください。

② テーブルにする
   では {MY} にテーブルを作ってください。
   テーブル名は中身に合わせて付けてください。
   何行取り込めたか、変換できなかった行があるかも教えてください。

③ ダッシュボードを作る
   さっき作ったテーブルでダッシュボードを作ってください。日本語のタイトルで。

④ 意味を付ける（⚠️ ⑤ の前に）
   そのテーブルに列コメントを付けて、メトリクスビューも作ってください。

⑤ Genie Agent を作る
   そのメトリクスビューで Genie Agent を作ってください。日本語で答えるように。
""")

print("=" * 78)
print("  ⚠️ プロンプト例（おまけ / 時間が余ったら）")
print("=" * 78)
print("""
⭐ どれも「さっき作ったテーブルで」と言えば通じます。

  ・グラフを足す        「〇〇の推移が見たいのでグラフを足して」
  ・気になることを聞く   Genie Agent に業務の言葉で質問してみる
  ・データを足す        別の CSV も置いて「これも結合して」

⚠️ 時系列データ（日付と数量がある）の場合は、ここまで行けます:

  ・SQL 1 文で予測      「ai_forecast で 12 か月先まで予測して」
  ・モデルを作る        「予測モデルを作って Unity Catalog に登録して」
                       ⚠️ 「去年と同じと比べた結果も見せて」
  ・精度を残す          「予測と実績を突き合わせた表を作って」
  ・自動実行にする      「毎月これを回すジョブにして」
""")

# COMMAND ----------

# MAGIC %md
# MAGIC ## ⚠️ つまずいたら
# MAGIC
# MAGIC | ⚠️ 症状 | ⭐ 言い方 |
# MAGIC |---|---|
# MAGIC | 列の意味を誤解された | ⭐ **① をやり直す** — 「まず各列が何を表しているか教えて」 |
# MAGIC | 日本語の列名でエラー | 「日本語の列名はバッククォートで囲んでください」 |
# MAGIC | 日付が変換できない | ⭐ **元の値をそのまま見せて**「この形式です」と伝える |
# MAGIC | 数値が文字列扱いになる | 「桁区切りが入っています。カンマを除いて数値にしてください」 |
# MAGIC | 日本語が化ける | 「文字コードは Shift_JIS かもしれません」 |
# MAGIC | Genie の答えがおかしい | ⚠️ ④ のメタデータを飛ばしていませんか |
# MAGIC | 行が減っている / 増えている | 「取り込めなかった行と、重複していた行を教えて」 |
# MAGIC | ⚠️ 予測で「データが足りない」 | ⚠️ 予測には**各系列 24 か月以上**必要。⭐ 短ければ `ai_forecast` を試す |
# MAGIC
# MAGIC ### ⭐⭐ うまくいかない方が学びになります
# MAGIC
# MAGIC 実データは必ず想定と違う形をしています。
# MAGIC ⭐ **「どう頼み直したら通ったか」**を持ち帰ってください。
# MAGIC それがそのまま、社内で使うときのコツになります。
# MAGIC
# MAGIC ⚠️ 詰まったところは遠慮なく声をかけてください。
