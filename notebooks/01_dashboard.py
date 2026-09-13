# Databricks notebook source
# MAGIC %md
# MAGIC # 01 — ダッシュボードを作る
# MAGIC
# MAGIC > ⏱ **目安 20 分**
# MAGIC >
# MAGIC > 🔑 **必要な権限**: SQL ウェアハウスの `CAN USE`
# MAGIC
# MAGIC ## このパートでやること
# MAGIC
# MAGIC | | 内容 | 目安 |
# MAGIC |---|---|---|
# MAGIC | 1 | **完成見本を見る** — 20 分後にこれが自分で作れます | 2 分 |
# MAGIC | 2 | **画面から手で作る** — グラフ 3 つ + フィルタ 2 つ | 9 分 |
# MAGIC | 3 | ⭐ **Genie Code に作らせる** — 言葉で指示するだけ | 6 分 |
# MAGIC | 4 | ⭐ **自動配信を設定する** — 毎朝メールで届くようにする | 3 分 |
# MAGIC
# MAGIC > ⭐ **今日いちばん実務が変わるのは 4 です。**
# MAGIC > 「毎月レポートを作ってメールに添付する」作業がまるごと消えます。

# COMMAND ----------

# MAGIC %run ./_config

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. 完成見本を見る（2 分）
# MAGIC
# MAGIC まず「出来上がり」を見ておきます。下のセルを実行するとリンクが出ます。
# MAGIC
# MAGIC ⭐ 見本は共有の `fc_sample` を参照しています。
# MAGIC これから作るのは、**あなたのスキーマ**を参照する自分専用のダッシュボードです。

# COMMAND ----------

from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
host = w.config.host

samples = [d for d in w.lakeview.list() if d.display_name and "見本" in d.display_name]
if samples:
    for d in samples:
        displayHTML(f'<a href="{host}/dashboardsv3/{d.dashboard_id}/published" target="_blank">▶ {d.display_name}</a>')
else:
    print("⚠️ 見本ダッシュボードが見つかりませんでした。講師に確認してください。")
    print(f"   （ダッシュボード一覧: {host}/dashboards）")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. 画面から手で作る（9 分）
# MAGIC
# MAGIC ⭐ **ノートブックではなく画面で作ります。** SQL を書かなくても作れることを体験してください。
# MAGIC
# MAGIC ### 手順
# MAGIC
# MAGIC 1. 左メニュー **「ダッシュボード」** → 右上 **「ダッシュボードを作成」**
# MAGIC 2. 右上で **SQL ウェアハウス**を選ぶ（当日指示されたもの）
# MAGIC 3. 名前を付ける — 例: `需要ダッシュボード_山田太郎`
# MAGIC 4. **「データ」** タブ → **「データソースを追加する」** → 下のセルで出力される
# MAGIC    テーブル名を検索して追加
# MAGIC    - `fct_shipments`（出荷実績）
# MAGIC    - `dim_item`（品目マスタ）
# MAGIC 5. **「キャンバス」** タブに戻り、グラフを 3 つ作る
# MAGIC    | グラフ | 中身 |
# MAGIC    |---|---|
# MAGIC    | 折れ線 | 月ごとの出荷数量の推移 |
# MAGIC    | 横棒 | 品目別の出荷数量（上位 10 件） |
# MAGIC    | 円 | チャネル別（国内 / 海外）の構成比 |
# MAGIC 6. **フィルタ**を 2 つ追加する
# MAGIC    - 品目カテゴリ
# MAGIC    - チャネル
# MAGIC 7. 右上 **「公開」**
# MAGIC 8. ⭐ **グラフの一部をクリック**してみる — 他のグラフも連動して絞り込まれます
# MAGIC    （クロスフィルタリング。設定は不要で、最初から効きます）
# MAGIC
# MAGIC > 💡 グラフを作るとき、**プロンプト欄に日本語で書くだけ**でも作れます。
# MAGIC > 例: 「月ごとの出荷数量の推移を折れ線で」

# COMMAND ----------

print("ダッシュボードで検索するテーブル名（コピーして使ってください）")
print("=" * 64)
for t in ["fct_shipments", "dim_item", "dim_channel", "fct_inventory", "fct_forecast_accuracy"]:
    print(f"  {MY}.{t}")
print("=" * 64)
print("\n⭐ 指標の定義がまとまった「メトリクスビュー」もあります（3 で使います）")
for t in ["mv_demand", "mv_forecast_accuracy"]:
    print(f"  {MY}.{t}")

# COMMAND ----------

# MAGIC %md
# MAGIC ### どんなデータが入っているか（作る前の確認）

# COMMAND ----------

# MAGIC %sql
# MAGIC -- 月ごとの出荷数量と金額。まずはこれをグラフにします。
# MAGIC SELECT ym, SUM(qty) AS qty, SUM(amount) AS amount
# MAGIC FROM fct_shipments
# MAGIC GROUP BY ym
# MAGIC ORDER BY ym

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. ⭐ Genie Code に作らせる（6 分）
# MAGIC
# MAGIC ⭐ **ここが今日の目玉のひとつです。** 言葉で指示するだけでページごと作られます。
# MAGIC
# MAGIC ### 手順
# MAGIC
# MAGIC 1. ダッシュボードを開いたまま、右上の **ランプのアイコン**（または下メニュー）から
# MAGIC    **「Genie Code」** を起動する
# MAGIC 2. ダッシュボードと接続されていることを確認する
# MAGIC 3. 下のプロンプトを **コピーして貼り付ける**（`<あなたのスキーマ>` は下のセルの出力に置き換え）
# MAGIC
# MAGIC ⚠️ 一度に多くを頼むと的が外れます。**1 ページずつ**頼むのがコツです。
# MAGIC
# MAGIC > 💡 プロンプトは `prompts/genie_code_dashboard.md` にもまとめてあります。

# COMMAND ----------

print("=" * 78)
print("  プロンプト①  多角的な分析ページを追加する")
print("=" * 78)
print(f"""
このダッシュボードにページを 1 つ追加し、
{MY}.mv_demand メトリクスビューを使った分析グラフを追加してください。

- 月ごとの出荷数量の推移（折れ線）
- 品目カテゴリ別の出荷数量（棒）
- チャネル別の構成比（円）
- 品目カテゴリ別の月平均出荷数量（棒）

タイトルはすべて日本語にしてください。
""")

print("=" * 78)
print("  プロンプト②  ⭐ 予測と実績を突き合わせるページを追加する")
print("=" * 78)
print(f"""
ページを 1 つ追加し、予測と実績の比較を見られるようにしてください。

- {MY}.fct_forecast_accuracy を使う
- 対象月ごとの平均誤差率の推移（折れ線）
- 品目ごとの平均誤差個数 上位 10 件（横棒）
- 需要分類ごとの平均誤差率と平均誤差個数を並べた表

⭐ 誤差率と誤差個数は必ず両方見せてください。
  数量の少ない品目は誤差率が大きく出るため、率だけ見ると判断を誤ります。
""")

print("=" * 78)
print("  プロンプト③  ⭐ 在庫の健全性を見るページを追加する")
print("=" * 78)
print(f"""
ページを 1 つ追加し、在庫の状況を見られるようにしてください。

- {MY}.fct_inventory と {MY}.dim_lead_time と {MY}.dim_item を使う
- 拠点別の月末在庫と安全在庫の比較（棒）
- 欠品が発生した品目の一覧（最新月）
- リードタイムが長い品目 上位 10 件（横棒）
""")

# COMMAND ----------

# MAGIC %md
# MAGIC ### ⭐ ③ が答えられる質問
# MAGIC
# MAGIC 「良いダッシュボードは多くの質問に答えてくれる」と言われますが、
# MAGIC 実際に現場から出てくる質問はこういうものです。
# MAGIC
# MAGIC - **欠品が発生している製品は？**
# MAGIC - **余剰在庫がある拠点は？**
# MAGIC - **需要予測の精度は？**
# MAGIC - **リードタイムが最も長い品目は？**
# MAGIC
# MAGIC ⭐ ③ のページを作ると、この 4 つに答えられる状態になります。
# MAGIC ⚠️ ただし「じゃあ来月どうする？」には、ダッシュボードだけでは答えられません。
# MAGIC それが次のパート（Genie Agent）の役割です。

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. ⭐ 自動配信を設定する（3 分）
# MAGIC
# MAGIC ⭐⭐ **「毎月レポートを作ってメールに添付する」作業がまるごと消えるのはここです。**
# MAGIC
# MAGIC ### 手順
# MAGIC
# MAGIC 1. ダッシュボードを **「公開」** した状態にする（未公開だとスケジュールを設定できません）
# MAGIC 2. 右上 **「スケジュール」** を押す
# MAGIC 3. **更新のタイミング**を決める — 例: 毎日 8:00
# MAGIC 4. **「サブスクライバー」** に自分のメールアドレスを追加する
# MAGIC 5. 保存して、**「今すぐ実行」** で 1 通届くか確認する
# MAGIC
# MAGIC ### 押さえておきたいこと
# MAGIC
# MAGIC | 項目 | 内容 |
# MAGIC |---|---|
# MAGIC | 届く形 | ⭐ **PDF が添付されたメール** |
# MAGIC | 社外の宛先 | 通知先（notification destination）を経由すれば送れます |
# MAGIC | 宛先の上限 | 100 件 |
# MAGIC | 添付の上限 | 9 MB |
# MAGIC | データの更新 | スケジュールのタイミングでダッシュボードのクエリが再実行されます |
# MAGIC
# MAGIC > ⚠️ **権限は引き継がれません。** 受け取った人が元のテーブルを見られなくても、
# MAGIC > PDF の中身は見えます。逆にダッシュボードを開くとエラーになります。
# MAGIC > 社外に送るときは特に、**何が写っているか**を確認してください。

# COMMAND ----------

# MAGIC %md
# MAGIC ## ✅ ここまでできたら
# MAGIC
# MAGIC 次は **`02_genie_agent`** に進みます。
# MAGIC
# MAGIC ダッシュボードは「**決めた問い**に速く答える」道具でした。
# MAGIC 次は「**その場で出てきた問い**に答える」道具を作ります。
