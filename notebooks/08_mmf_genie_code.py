# Databricks notebook source
# MAGIC %md
# MAGIC # 08 — 品目ごとに最適な手法を選ぶ（MMF を自然言語で動かす）
# MAGIC
# MAGIC > ⏱ **目安 15 分**
# MAGIC
# MAGIC ## ⚠️ ここまでの限界
# MAGIC
# MAGIC 今日作ったモデルは **全品目に 1 つ**でした。
# MAGIC でも `00` で見たとおり、品目ごとに需要の性質はまったく違います。
# MAGIC
# MAGIC | 需要分類 | 性質 | 向いている手法 |
# MAGIC |---|---|---|
# MAGIC | smooth | 毎月安定 | トレンドと季節性を素直に追う手法 |
# MAGIC | erratic | 数量が振れる | ばらつきに強い手法 |
# MAGIC | intermittent / lumpy | 出ない月がある | ⭐ **間欠需要専用の手法**（別ジャンル） |
# MAGIC
# MAGIC ⚠️ **1 つのモデルで全部を賄うのは、そもそも無理があります。**
# MAGIC
# MAGIC ## ⭐ Many Models Forecasting (MMF)
# MAGIC
# MAGIC Databricks が公開している需要予測の仕組みです。
# MAGIC **系列ごとに複数の手法を試して、系列ごとのベストを選んでくれます。**
# MAGIC
# MAGIC ⭐ そして **Genie Code に自然言語で指示するだけ**で動かせます。
# MAGIC
# MAGIC ## ⚠️ 先に知っておいてほしいこと
# MAGIC
# MAGIC | ⚠️ | 内容 |
# MAGIC |---|---|
# MAGIC | サポート | **Databricks の正式サポート対象外**（AS-IS で公開されているもの） |
# MAGIC | 実行環境 | **Databricks Runtime for ML 18 以上**が必要 |
# MAGIC | ⚠️⚠️ **1 回の指示では終わらない** | 意図的に**対話しながら進む**作りになっています（後述） |
# MAGIC | 事前準備 | Genie Code に「スキル」を入れておく必要があります（講師が実施済み） |
# MAGIC
# MAGIC > ⚠️⚠️ **「プロンプト 1 つ投げて完成」ではありません。**
# MAGIC > MMF のスキルは「カタログはどこ？」「何を予測したい？」「欠測はどう扱う？」と
# MAGIC > **必ず確認しながら進む**設計になっています。
# MAGIC > ⭐ この「AI が要件をヒアリングしてくる」体験こそが、今日見てほしいところです。

# COMMAND ----------

# MAGIC %run ./_config

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. ⭐ Genie Code に投げるプロンプト（4 分）
# MAGIC
# MAGIC ### 手順
# MAGIC
# MAGIC 1. Genie Code を開く（右上のランプのアイコン、または左メニュー）
# MAGIC 2. 下のセルで出力されるプロンプトを **そのまま貼り付ける**
# MAGIC 3. ⭐ **AI が質問してくるので答える**（回答例は次のセルにあります）
# MAGIC
# MAGIC > 💡 プロンプトは `prompts/genie_code_mmf.md` にもまとめてあります。

# COMMAND ----------

print("=" * 78)
print("  プロンプト①  MMF を始める")
print("=" * 78)
print(f"""
MMF (Many Models Forecasting) を使って需要予測をしたい。

- カタログ: {catalog}
- スキーマ: {schema}
- ユースケース名: scm
- 元データ: {MY}.fct_shipments
- 予測対象: 品目 × チャネルごとの月次出荷数量 (qty)
- 系列 ID: item_code と channel の組み合わせ
- 日付列: ym （月末日で入っています）
- 予測期間: 18 か月先
- 頻度: 月次
""")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. ⭐ AI が聞いてくることへの答え方
# MAGIC
# MAGIC | 聞かれること | ⭐ 答え方 |
# MAGIC |---|---|
# MAGIC | カタログとスキーマ | 上のプロンプトに書いたとおり |
# MAGIC | **何を予測したいのか（背景）** | 「産業用機器とその消耗品の月次需要を 18 か月先まで予測し、欠品と過剰在庫を減らしたい。少量多品種で、出ない月がある品目や、海外向けに大口の山が立つ品目が多い」 |
# MAGIC | 欠測している月の扱い | 「欠測月は 0 とする（出荷実績がない = その月は出荷ゼロ）」 |
# MAGIC | ⚠️ **異常値の扱い** | ⭐ **「大口のスパイクは実需なので丸めない」** |
# MAGIC | 次の手順に進むか | 「進んでください」 |
# MAGIC
# MAGIC ### ⚠️ 異常値の質問は、わざと考えてほしいところです
# MAGIC
# MAGIC 「外れ値は丸めますか？」と聞かれて **「はい」と答えたくなります**。
# MAGIC ⚠️ でもこのデータの大口スパイクは、海外代理店の先行注文という**実需**です。
# MAGIC 丸めてしまうと、**いちばん備えたい需要の山が予測から消えます**。
# MAGIC
# MAGIC ⭐ 「何が異常で、何が実需か」は**データを見ただけでは決められません**。
# MAGIC 業務を知っている人が判断するところです。
# MAGIC AI が聞いてくるのは、まさにそれを聞いています。

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. ⭐⭐ ここが今日いちばんの見せ場（4 分）
# MAGIC
# MAGIC 続けて次の指示を投げてください。
# MAGIC
# MAGIC ```
# MAGIC /profile-and-classify-series
# MAGIC ```
# MAGIC
# MAGIC ⭐ 系列の性質を統計的に調べて、**「予測しやすい系列」と「予測しにくい系列」に分けます。**
# MAGIC そして、予測しにくい系列をどう扱うか **3 択で聞いてきます**。
# MAGIC
# MAGIC | 選択肢 | 内容 |
# MAGIC |---|---|
# MAGIC | A. 全部一緒に扱う | 予測しにくい系列も同じモデルで扱う |
# MAGIC | ⭐⭐ **B. 単純なルールに退避させる** | **「去年と同じ」「平均」「ゼロ」などの単純な手法を当てる** |
# MAGIC | C. 別のパイプラインに分ける | 予測しにくい系列だけ別扱いで本格的に回す |
# MAGIC
# MAGIC ### ⭐ ここでは **B を選び、「去年と同じ（Seasonal Naive）」** を指定してください
# MAGIC
# MAGIC ⭐⭐ **今日いちばん持ち帰ってほしいのはこれです。**
# MAGIC
# MAGIC > **「当てにいかない」という判断が、標準機能として用意されている。**
# MAGIC
# MAGIC ⚠️ 予測モデルの話は「どうやって精度を上げるか」に向かいがちです。
# MAGIC でも実務では、**当たらない品目を見切って単純な運用に寄せる**方が正しいことがあります。
# MAGIC
# MAGIC ⭐ `05` で見たとおり、`intermittent` や `lumpy` の品目は
# MAGIC 「去年と同じ」でも誤差 1 個未満でした。ここに手の込んだモデルを当てる意味は薄いのです。
# MAGIC
# MAGIC ⭐ 選んだ結果は最後の集計に **どの手法で予測したかの区分**として残ります。
# MAGIC 「この品目は機械学習、この品目は単純ルール」が記録として見える形になります。

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. 実行済みの結果を見る（5 分）
# MAGIC
# MAGIC ⚠️ MMF を最後まで通すと **10〜30 分**かかります（系列数とモデル数によります）。
# MAGIC ⭐ 講師が事前に実行しておいた結果を見て、**何が出てくるのか**を確認しましょう。
# MAGIC
# MAGIC MMF が作るテーブル:
# MAGIC
# MAGIC | テーブル | 中身 |
# MAGIC |---|---|
# MAGIC | `scm_train_data` | MMF が使う形に整えた学習データ |
# MAGIC | `scm_series_profile` | 系列ごとの統計的な性質と、予測しやすさの判定 |
# MAGIC | `scm_evaluation_output` | **全モデル × 全系列**の検証結果 |
# MAGIC | ⭐ `scm_best_models` | **系列ごとに選ばれたベストモデル** |
# MAGIC | `scm_evaluation_summary` | 業務向けのまとめ |

# COMMAND ----------

SAMPLE_MMF = f"{SAMPLE}"
tables = [t.name for t in spark.catalog.listTables(SAMPLE_MMF)] if spark.catalog.databaseExists(SAMPLE_MMF) else []
mmf_tables = [t for t in tables if t.startswith("scm_")]

if mmf_tables:
    print(f"見つかった MMF の結果テーブル ({SAMPLE_MMF}):")
    for t in sorted(mmf_tables):
        print(f"  {t:<32} {spark.table(f'{SAMPLE_MMF}.{t}').count():>8,} 行")
else:
    print(f"⚠️ {SAMPLE_MMF} に MMF の結果テーブルが見つかりませんでした。")
    print("   講師が事前実行したスキーマを確認してください。")

# COMMAND ----------

# MAGIC %md
# MAGIC ### ⭐⭐ 系列ごとに違うモデルが選ばれている
# MAGIC
# MAGIC ⚠️ **注目してほしいのは、勝ち数の順位と平均成績の順位が一致しないこと**です。
# MAGIC
# MAGIC ⭐ 「平均でいちばん強いモデル」と「系列ごとに選ばれるモデル」は別物です。
# MAGIC だから **系列ごとに選ぶ**ことに意味があります。

# COMMAND ----------

if mmf_tables and "scm_best_models" in mmf_tables:
    display(spark.sql(f"""
        SELECT model AS `選ばれたモデル`, COUNT(*) AS `勝った系列数`,
               ROUND(AVG(avg_metric), 4) AS `平均スコア`
        FROM {SAMPLE_MMF}.scm_best_models
        GROUP BY model
        ORDER BY `勝った系列数` DESC
    """))
else:
    print("⚠️ scm_best_models が見つかりませんでした。")

# COMMAND ----------

# MAGIC %md
# MAGIC ### ⭐ 内製の予測ロジックと MMF の対応
# MAGIC
# MAGIC よく使われる手法は、ほぼそのまま MMF に入っています。
# MAGIC
# MAGIC | よく使われる手法 | MMF での名前 | 必要な計算資源 |
# MAGIC |---|---|---|
# MAGIC | 指数平滑 (ETS) | `StatsForecastAutoETS` | CPU |
# MAGIC | Theta 法 | `StatsForecastAutoTheta` | CPU |
# MAGIC | ARIMA | `StatsForecastAutoArima` | CPU |
# MAGIC | Prophet | `SKTimeProphet` | CPU |
# MAGIC | LightGBM | `MLForecastLGBM` | CPU |
# MAGIC | ⭐ 間欠需要向け (Croston 系) | `StatsForecastCrostonSBA` | CPU |
# MAGIC | ニューラル予測 (NHITS / NBEATSx) | `NeuralForecastAutoNHITS` など | ⚠️ GPU |
# MAGIC | ⭐⭐ **精度の悪いモデルを自動除外する仕組み** | ⭐ **系列プロファイリング + 退避ルール** | CPU |
# MAGIC
# MAGIC ⭐ **ニューラル予測以外は CPU だけで動きます。**
# MAGIC ⚠️ 一方で **アンサンブル（複数モデルの重み付き合成）に相当する機能はありません**。
# MAGIC 「系列ごとにベストを 1 つ選ぶ」という考え方です。

# COMMAND ----------

# MAGIC %md
# MAGIC ## ✅ ここまでできたら
# MAGIC
# MAGIC 次は **`99_your_own_data`** — ⭐ **自由時間**です。
# MAGIC 自分の手元のデータを取り込んで、今日やったことを試してみてください。
