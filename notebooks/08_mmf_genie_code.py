# Databricks notebook source
# MAGIC %md
# MAGIC # 08 — 品目ごとに最適な手法を選ぶ（MMF）
# MAGIC
# MAGIC > ⏱ **目安 15 分**
# MAGIC
# MAGIC ## ⚠️ ここまでの限界
# MAGIC
# MAGIC 今日作ったモデルは **全品目に 1 つ**でした。
# MAGIC でも `00` で見たとおり、**品目ごとに需要の性質はまったく違います**
# MAGIC （毎月安定 / 数量が振れる / 出ない月がある）。
# MAGIC
# MAGIC ⚠️ **1 つのモデルで全部を賄うのは、そもそも無理があります。**
# MAGIC
# MAGIC ## ⭐ Many Models Forecasting (MMF)
# MAGIC
# MAGIC Databricks が公開している需要予測の仕組みです。
# MAGIC ⭐ **系列ごとに複数の手法を試して、系列ごとのベストを選んでくれます。**
# MAGIC
# MAGIC ⭐⭐ そして **Genie Code に自然言語で頼むだけ**で、
# MAGIC データ準備 → 系列の分類 → モデル比較 → 評価まで通せます。
# MAGIC
# MAGIC ```
# MAGIC   ① データ準備 → ② 系列を分類 → ③ モデル選択 → ④ 実行 → ⑤ ベスト選定
# MAGIC ```
# MAGIC
# MAGIC | ⚠️ | 知っておいてほしいこと |
# MAGIC |---|---|
# MAGIC | サポート | **Databricks の正式サポート対象外**（AS-IS で公開） |
# MAGIC | 実行環境 | ⭐ **サーバーレスで動きます**（GPU 不要・実測 6.5 分） |
# MAGIC | ⚠️⚠️ **1 回の指示では終わらない** | 意図的に**対話しながら進む**作りです |
# MAGIC
# MAGIC > ⚠️⚠️ **「プロンプト 1 つ投げて完成」ではありません。**
# MAGIC > ⭐ **AI が要件をヒアリングしてくる**体験こそが、今日見てほしいところです。

# COMMAND ----------

# MAGIC %run ./_config

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. ⭐ MMF のスキルを入れる
# MAGIC
# MAGIC ⭐ Genie Code に**これだけ**渡せば入ります。
# MAGIC
# MAGIC ```
# MAGIC https://github.com/databricks-industry-solutions/many-model-forecasting
# MAGIC
# MAGIC MMF の skill を install したい
# MAGIC ```
# MAGIC
# MAGIC ⭐ 入ったか確認したいときは `What skills do you have access to?` と聞いてください。
# MAGIC
# MAGIC > ⭐ **今日は講師が事前に入れてあります。** この節は「自社でどう始めるか」の参考です。
# MAGIC > ⚠️ うまく入らないときは、下のセルで置き場所を確認してください。

# COMMAND ----------

from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
api = w.api_client
me = spark.sql("SELECT current_user()").collect()[0][0]

# ⚠️ Genie Code はパスに厳格。先頭のドットまで含めて一致していないと読み込まれません。
for path, label in [
    (f"/Users/{me}/.assistant/skills", "スキル本体"),
    (f"/Users/{me}/.assistant_instructions.md", "共通指示 (推奨)"),
]:
    try:
        api.do("GET", f"/api/2.0/workspace/get-status?path={path}")
        print(f"  ✅ {label:<18} {path}")
    except Exception:
        print(f"  ⚠️ {label:<18} {path}  ← 見つかりません")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. ⭐ 実行用のプロンプト
# MAGIC
# MAGIC ⭐ 下のセルが出す内容を Genie Code にそのまま貼ってください。
# MAGIC ⚠️ **あとは聞かれることに答えていくだけです。**

# COMMAND ----------

print("=" * 78)
print("  ⭐ MMF を始めるプロンプト")
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

print("=" * 78)
print("  ⭐ 「何をなぜ予測するのか」を聞かれたら（文例）")
print("=" * 78)
print("""
産業用機器の月次出荷数量を 18 か月先まで予測し、在庫計画に使いたい。
少量多品種で、出ない月がある品目もある。外部変数は使わず、履歴データだけで予測する。
""")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. ⭐ 聞かれたときの答え方
# MAGIC
# MAGIC ⭐ 迷ったらこの表のとおりに答えてください。⚠️ **深く考えずに進めて構いません。**
# MAGIC
# MAGIC | 聞かれること | ⭐ 答え方 |
# MAGIC |---|---|
# MAGIC | ノートブックの保存先 | ⭐ 既定でよい |
# MAGIC | 列のマッピング | 確認して進む |
# MAGIC | 外部変数を使うか | ⭐ 使わない（単変量） |
# MAGIC | 出ない月（ゼロ）の扱い | ⭐ **ゼロのまま残す**（出荷がなかったという情報なので） |
# MAGIC | ⚠️ **異常値の扱い** | ⭐⭐ **丸めない**（下記） |
# MAGIC | ⭐⭐ **予測しにくい系列の扱い（3 択）** | ⭐⭐ **B「単純なルールに退避」→ 去年と同じ**（下記） |
# MAGIC | モデル / クラスタ | ⭐ **「CPU のみ」「サーバーレスのままで」** |
# MAGIC | バックテスト | ⭐ **(b) 標準 3 ウィンドウ** |
# MAGIC
# MAGIC ### ⚠️ この 2 つだけは意味を知っておいてください
# MAGIC
# MAGIC **① 異常値を丸めない**
# MAGIC
# MAGIC 「外れ値は丸めますか？」と聞かれると **つい「はい」と答えたくなります**。
# MAGIC ⚠️ でもこのデータの大口スパイクは、海外代理店の先行注文という**実需**です。
# MAGIC 丸めると **いちばん備えたい需要の山が予測から消えます**。
# MAGIC ⭐ 「何が異常で何が実需か」は業務を知っている人しか判断できません。
# MAGIC
# MAGIC **② ⭐⭐ 予測しにくい系列は「当てにいかない」**
# MAGIC
# MAGIC MMF は系列を統計的に調べて「予測しやすい / しにくい」に分け、
# MAGIC しにくい系列の扱いを **3 択で聞いてきます**。⭐ ここで **B** を選んでください。
# MAGIC
# MAGIC > ⭐⭐ **「当てにいかない」という判断が、標準機能として用意されている。**
# MAGIC
# MAGIC ⚠️ 予測の話は「どう精度を上げるか」に向かいがちですが、実務では
# MAGIC **当たらない品目を見切って単純な運用に寄せる**方が正しいことがあります。
# MAGIC ⭐ `05` で見たとおり、出ない月がある品目は「去年と同じ」でも誤差 1 個未満でした。

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. ⚠️ つまずいたときの言い方
# MAGIC
# MAGIC ⭐ **どれも会話で直せます。** ⚠️ 自分でコードを直しに行かないでください。
# MAGIC
# MAGIC | ⚠️ 症状 | ⭐ 言い方 |
# MAGIC |---|---|
# MAGIC | `sc is not supported on serverless compute` | 「サーバーレスでは `sc` が使えないので直して」 |
# MAGIC | 直したのに同じエラーが再発 | 「セル全体を書き直して」 |
# MAGIC | ジョブ作成がブロックされる | 「サーバーレスで直接実行して」 |
# MAGIC | クラスタを立てようとする | 「サーバーレスのままで」 |
# MAGIC | GPU が必要と言われる | 「CPU のみで」 |
# MAGIC
# MAGIC ⚠️ **実行には 6〜20 分かかります。** 時間内に終わらなければ、
# MAGIC ⭐ 下のセルで**見本の結果**を見てください。

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. ⭐ 結果を見る
# MAGIC
# MAGIC ⭐⭐ **注目してほしいのは、勝ち数の順位と平均成績の順位が一致しないこと**です。
# MAGIC
# MAGIC ⭐ 「平均でいちばん強いモデル」と「系列ごとに選ばれるモデル」は別物です。
# MAGIC **だから系列ごとに選ぶことに意味があります。**
# MAGIC
# MAGIC ⚠️ 実測では **39 系列のうち 10 系列が「予測しにくい」** と判定され、
# MAGIC 「去年と同じ」に退避されました。⭐ 海外チャネルは全系列が予測困難でした。

# COMMAND ----------

# ⭐ 自分のスキーマ → 見本 の順に MMF の結果を探す
MMF_SCHEMA, found = None, []
for sch in (MY, SAMPLE):
    if spark.catalog.databaseExists(sch):
        found = sorted(t.name for t in spark.catalog.listTables(sch) if t.name.startswith("scm_"))
        if found:
            MMF_SCHEMA = sch
            break

if not MMF_SCHEMA:
    print("⚠️ MMF の結果テーブルがまだありません。")
    print("   ⭐ 最後まで実行するか、講師に見本の場所を確認してください。")
else:
    print(f"⭐ MMF の結果: {MMF_SCHEMA}")
    for t in found:
        print(f"  {t:<32} {spark.table(f'{MMF_SCHEMA}.{t}').count():>8,} 行")

    if "scm_best_models" in found:
        # ⚠️ 列名は MMF のバージョンで変わるため、見てから組み立てます
        cols = {f.name for f in spark.table(f"{MMF_SCHEMA}.scm_best_models").schema.fields}
        sel = ["model AS `選ばれたモデル`", "COUNT(*) AS `勝った系列数`"]
        grp = ["model"]
        if "avg_metric" in cols:
            sel.append("ROUND(AVG(avg_metric), 4) AS `平均スコア`")
        if "forecast_source" in cols:
            sel.insert(1, "forecast_source AS `予測の経路`")
            grp.append("forecast_source")
        display(spark.sql(f"SELECT {', '.join(sel)} FROM {MMF_SCHEMA}.scm_best_models "
                          f"GROUP BY {', '.join(grp)} ORDER BY `勝った系列数` DESC"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6. ⭐ ここから自由に試してください
# MAGIC
# MAGIC ⭐ 時間が余ったら、こんなことも頼めます（⚠️ どれも例文です）。
# MAGIC
# MAGIC | やりたいこと | ⭐ 言い方 |
# MAGIC |---|---|
# MAGIC | 結果をもっと詳しく見る | 「チャネル別・品目別に精度を分けて見せて」 |
# MAGIC | 別のモデルを足す | 「Prophet と LightGBM も加えて比べて」 |
# MAGIC | ⭐ UC に登録する | 「ベストモデルを Unity Catalog に登録したい。入力は `unique_id`、出力は 18 か月分の予測（日付・予測値・使ったモデル名）で」 |
# MAGIC | バッチ推論する | 「登録したモデルで全系列の予測をテーブルに書き出して」 |
# MAGIC | 自動化する | 「毎月これを回すジョブにして」 |
# MAGIC
# MAGIC ⚠️ **UC 登録を頼むときは「入力は何で、出力は何か」を必ず言ってください。**
# MAGIC ⭐ 曖昧に頼むと、予測値を返さない使いにくいモデルが作られます（実際に一度そうなりました）。
# MAGIC
# MAGIC ### ⭐ 内製ロジックとの対応（参考）
# MAGIC
# MAGIC | よく使われる手法 | MMF での名前 |
# MAGIC |---|---|
# MAGIC | 指数平滑 / Theta / ARIMA | `StatsForecastAutoETS` / `AutoTheta` / `AutoArima` |
# MAGIC | Prophet / LightGBM | `SKTimeProphet` / `MLForecastLGBM` |
# MAGIC | ⭐ 間欠需要向け (Croston 系) | `StatsForecastCrostonSBA` / `ADIDA` / `IMAPA` / `TSB` |
# MAGIC | ニューラル予測 / 基盤モデル | `NeuralForecastAutoNHITS` / `ChronosBolt*`（⚠️ GPU） |
# MAGIC
# MAGIC ⚠️ **アンサンブル（複数モデルの合成）に相当する機能はありません。**
# MAGIC 「系列ごとにベストを 1 つ選ぶ」という考え方です。

# COMMAND ----------

# MAGIC %md
# MAGIC ## ✅ ここまでできたら
# MAGIC
# MAGIC 次は **`99_your_own_data`** — ⭐ **自由時間**です。
# MAGIC ⭐ こちらも Genie Code に言葉で頼む形になっています。
