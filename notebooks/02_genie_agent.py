# Databricks notebook source
# MAGIC %md
# MAGIC # 02 — Genie Agent に自然言語で聞く
# MAGIC
# MAGIC > ⏱ **目安 20 分**
# MAGIC >
# MAGIC > 🔑 **必要な権限**: SQL ウェアハウスの `CAN USE`
# MAGIC
# MAGIC ## ダッシュボードとの違い
# MAGIC
# MAGIC | | ダッシュボード | ⭐ Genie Agent |
# MAGIC |---|---|---|
# MAGIC | 得意なこと | **決めた問い**に速く答える | **その場で出てきた問い**に答える |
# MAGIC | 準備 | グラフを作り込む | データと文脈を渡す |
# MAGIC | 聞けること | 作った分だけ | 聞きたいことを聞ける |
# MAGIC
# MAGIC ⭐ 現場の問いは、作ったグラフの数よりずっと多いはずです。
# MAGIC 「欠品しているのは？」「余っているのは？」「予測は当たってる？」「リードタイムは？」——
# MAGIC こういう問いに**その場で**答えられるようにします。
# MAGIC
# MAGIC ## このパートでやること
# MAGIC
# MAGIC | | 内容 | 目安 |
# MAGIC |---|---|---|
# MAGIC | 1 | ⭐ **データに「意味」を付ける**（Genie の精度はここで決まる） | 4 分 |
# MAGIC | 2 | Genie Agent を作る | 4 分 |
# MAGIC | 3 | 質問してみる | 8 分 |
# MAGIC | 4 | 指示を足して精度を上げる | 4 分 |

# COMMAND ----------

# MAGIC %run ./_config

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. ⭐ データに「意味」を付ける（4 分）
# MAGIC
# MAGIC ⚠️⚠️ **ここを飛ばすと、この後の Genie Agent はまともに答えません。**
# MAGIC
# MAGIC Genie Agent は Unity Catalog に登録された「意味」を読んで SQL を組み立てます。
# MAGIC `qty` が何の数量なのか、`ym` が年月なのか年度なのか、テーブル同士がどう繋がるのか——
# MAGIC **人間に説明していないことは、Genie にも分かりません。**
# MAGIC
# MAGIC ⭐ **順番が大事です**: Unity Catalog を整える → その上で Genie Agent を作る。
# MAGIC 逆にすると「Genie は精度が出ない」で終わってしまいます。
# MAGIC
# MAGIC 下のセルで、テーブルの説明と **メトリクスビュー**（指標の定義）を作ります。

# COMMAND ----------

# MAGIC %run ./_uc_metadata

# COMMAND ----------

# MAGIC %md
# MAGIC ### 何が作られたか確認する
# MAGIC
# MAGIC ⭐ **メトリクスビュー**は「出荷数量とはこの式のこと」「予測誤差率とはこの式のこと」を
# MAGIC 1 箇所に固定する仕組みです。ダッシュボードでも Genie Agent でも**同じ数字**が出ます。

# COMMAND ----------

# MAGIC %sql
# MAGIC -- ⚠️ 日本語の軸・指標名は必ずバッククォートで囲みます
# MAGIC SELECT
# MAGIC   `品目カテゴリ`,
# MAGIC   MEASURE(`出荷数量`)                       AS `qty`,
# MAGIC   ROUND(MEASURE(`月平均出荷数量`), 1)        AS `avg_monthly_qty`,
# MAGIC   MEASURE(`出荷金額`)                       AS `amount`
# MAGIC FROM mv_demand
# MAGIC GROUP BY `品目カテゴリ`
# MAGIC ORDER BY `qty` DESC

# COMMAND ----------

# MAGIC %sql
# MAGIC -- ⭐⭐ このパートで一番大事な表です。
# MAGIC -- 「去年と同じ」という予測が、需要の性質ごとにどれくらい当たっているか。
# MAGIC --
# MAGIC -- ⚠️ 率(誤差率)で並べると intermittent や lumpy が上位に来ますが、
# MAGIC --    個数で見ると 1 個も外していません。本当に困るのは erratic です。
# MAGIC -- ⭐ 「どの指標で並べるか」で優先順位がまるごと入れ替わります。
# MAGIC SELECT
# MAGIC   `需要分類`,
# MAGIC   ROUND(MEASURE(`平均誤差率`) * 100, 1)       AS `err_rate_pct`,
# MAGIC   ROUND(MEASURE(`平均誤差個数`), 1)           AS `err_qty`,
# MAGIC   ROUND(MEASURE(`予測区間的中率`) * 100, 1)   AS `in_interval_pct`,
# MAGIC   MEASURE(`予測件数`)                        AS `n`
# MAGIC FROM mv_forecast_accuracy
# MAGIC GROUP BY `需要分類`
# MAGIC ORDER BY `err_rate_pct` DESC

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Genie Agent を作る（4 分）
# MAGIC
# MAGIC ### 手順
# MAGIC
# MAGIC 1. 左メニュー **「Genie Agents」** を押す
# MAGIC 2. 右上 **「New」** を押す
# MAGIC 3. **データを選ぶ** — 下のセルで出力される **2 つのメトリクスビューだけ**を選んで **「Create」**
# MAGIC 4. タイトルを付ける — 例: `需要分析エージェント_山田太郎`
# MAGIC 5. **SQL ウェアハウス**を選ぶ（当日指示されたもの）
# MAGIC
# MAGIC > ⚠️⚠️ **生のテーブルは渡さないでください。**
# MAGIC >
# MAGIC > `fct_shipments` や `dim_item` を直接渡すと、Genie が結合を間違えやすくなり、
# MAGIC > 体験がかえって悪くなります。
# MAGIC > ⭐ メトリクスビューには**結合条件も指標の定義も既に書いてある**ので、
# MAGIC > これだけ渡すのがいちばん精度が出ます。
# MAGIC >
# MAGIC > ⭐ 「たくさん渡せば賢くなる」ではなく「**絞るほど正確になる**」と覚えてください。

# COMMAND ----------

print("Genie Agent に渡すデータ（この 2 つだけ）")
print("=" * 64)
print(f"  {MY}.mv_demand")
print(f"  {MY}.mv_forecast_accuracy")
print("=" * 64)

from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
displayHTML(f'<a href="{w.config.host}/genie" target="_blank">▶ Genie Agents を開く</a>')

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. 質問してみる（8 分）
# MAGIC
# MAGIC ⭐ まずは **「チャット」モード**で聞いてみてください。
# MAGIC
# MAGIC ### ウォームアップ（答えられて当然の質問）
# MAGIC
# MAGIC ```
# MAGIC 品目カテゴリごとの出荷数量を教えて
# MAGIC ```
# MAGIC ```
# MAGIC 直近 12 か月の出荷数量の推移をグラフにして
# MAGIC ```
# MAGIC ```
# MAGIC 国内と海外で出荷数量の構成比はどうなっている？
# MAGIC ```
# MAGIC
# MAGIC ### ⭐ 本番（実務の問い）
# MAGIC
# MAGIC ```
# MAGIC 予測が当たっていない品目カテゴリはどこ？誤差率と誤差個数の両方で教えて
# MAGIC ```
# MAGIC ```
# MAGIC 需要の性質（需要分類）ごとに予測精度を比べて、
# MAGIC どのグループを優先して改善すべきか意見を聞かせて
# MAGIC ```
# MAGIC ```
# MAGIC 国内専用の品目で、月平均の出荷数量が多い順に教えて
# MAGIC ```
# MAGIC
# MAGIC ### ⚠️ わざと意地悪な質問（Genie の限界を知る）
# MAGIC
# MAGIC ```
# MAGIC 来月いちばん売れる品目は？
# MAGIC ```
# MAGIC
# MAGIC ⚠️ これは **Genie が答えられない質問**です。過去のデータしか持っていないので、
# MAGIC 「過去の傾向」しか返せません。
# MAGIC ⭐ **「未来を当てる」のは次のパート（予測モデル）の仕事**です。
# MAGIC この線引きを掴んでおくと、社内で使うときに期待値を外しません。
# MAGIC
# MAGIC ### 答えの確かめ方
# MAGIC
# MAGIC ⭐ Genie の回答には **生成された SQL** が付いています。必ず開いてみてください。
# MAGIC 「どのテーブルをどう集計したか」が読めるので、**鵜呑みにせず検算できます**。
# MAGIC
# MAGIC 👍 / 👎 のフィードバックも付けてください。
# MAGIC 管理者は「モニタリング」タブでそれを見て、Agent を改善できます。

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. 指示を足して精度を上げる（4 分）
# MAGIC
# MAGIC 期待と違う答えが返ってきたら、**Agent に「指示」を足します**。
# MAGIC
# MAGIC ### 手順
# MAGIC
# MAGIC 1. Genie Agent の画面で **設定（鉛筆アイコン）** を開く
# MAGIC 2. **「指示」** に下の 3 行を貼る
# MAGIC 3. さっき期待と違った質問をもう一度投げて、変化を見る
# MAGIC
# MAGIC ```
# MAGIC - 回答は必ず日本語で返してください。
# MAGIC - 数量は整数、比率は小数第 1 位までに丸めてください。
# MAGIC - 予測精度について質問されたときは、誤差率と誤差個数を必ず両方示してください。
# MAGIC   数量の少ない品目は誤差率が大きく出るため、率だけでは判断を誤ります。
# MAGIC ```
# MAGIC
# MAGIC ### ⚠️ 指示を書くときのコツ
# MAGIC
# MAGIC | ✅ すること | ❌ しないこと |
# MAGIC |---|---|
# MAGIC | 短く、断定的に書く | 長文を詰め込む（かえって精度が落ちます） |
# MAGIC | 出力の形（言語・丸め方）を指定する | 矛盾することを 2 つ書く |
# MAGIC | 迷ったら確認させる指示を入れる | 列の値を全部列挙する |
# MAGIC | ⭐ 計算ロジックはメトリクスビューに書く | ⭐ 計算ロジックを指示文で説明する |
# MAGIC
# MAGIC ⭐ **最後の行が今日の要点です。**
# MAGIC 「売上とはこういう計算」を文章で説明するより、**メトリクスビューに定義を書く**方が
# MAGIC 確実で、しかもダッシュボードでも同じ定義が使われます。
# MAGIC
# MAGIC > 💡 **今日は触らないもの**: ナレッジストア（スペース固有の補足情報）や
# MAGIC > UC 関数（複雑な計算を関数として登録）。もっと精度を上げたいときの次の一手です。

# COMMAND ----------

# MAGIC %md
# MAGIC ## ✅ ここまでできたら
# MAGIC
# MAGIC 次は **`03_ai_forecast`** に進みます。
# MAGIC
# MAGIC ⚠️ Genie Agent は「**過去**に何が起きたか」には答えられますが、
# MAGIC 「**来月どうなるか**」には答えられませんでした。
# MAGIC ⭐ 次はそこを、SQL 1 文だけでやってみます。
