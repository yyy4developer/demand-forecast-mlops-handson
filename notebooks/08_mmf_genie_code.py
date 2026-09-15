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
# MAGIC ⭐⭐ そして **Genie Code に自然言語で頼むだけ**で、
# MAGIC データ準備からモデル比較・評価まで通せます。
# MAGIC
# MAGIC | ⚠️ | 知っておいてほしいこと |
# MAGIC |---|---|
# MAGIC | サポート | **Databricks の正式サポート対象外**（AS-IS で公開） |
# MAGIC | 実行環境 | ⭐ **サーバーレスで動きます**（統計モデルだけなら GPU 不要） |
# MAGIC | ⚠️⚠️ **1 回の指示では終わらない** | 意図的に**対話しながら進む**作りです（後述） |
# MAGIC
# MAGIC > ⚠️⚠️ **「プロンプト 1 つ投げて完成」ではありません。**
# MAGIC > ⭐ **AI が要件をヒアリングしてくる**体験こそが、今日見てほしいところです。

# COMMAND ----------

# MAGIC %run ./_config

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. ⭐ MMF スキルを入れる（3 分）
# MAGIC
# MAGIC ⭐ MMF は **Genie Code の「スキル」**として配布されています。
# MAGIC ⭐⭐ **インストールも Genie Code に頼めます。** GitHub の URL を渡すだけです。
# MAGIC
# MAGIC ### ⭐ Genie Code に貼るプロンプト
# MAGIC
# MAGIC ```
# MAGIC https://github.com/databricks-industry-solutions/many-model-forecasting
# MAGIC の skills/ を私のワークスペースにインストールしてください。
# MAGIC Genie Code 用の手順（README の Option A）でお願いします。
# MAGIC ```
# MAGIC
# MAGIC ### ⚠️ 入れるものは 2 つあります
# MAGIC
# MAGIC | # | 置き場所 | 中身 |
# MAGIC |---|---|---|
# MAGIC | 1 | `/Workspace/Users/<あなた>/.assistant/skills/` | ⭐ スキル本体（md 6 本 + ノートブック雛形 7 本） |
# MAGIC | 2 | `/Workspace/Users/<あなた>/.assistant_instructions.md` | ⭐ **エージェントへの共通指示**（⚠️ 先頭のドットに注意） |
# MAGIC
# MAGIC ⚠️ **2 が無いと、スキルを無視して勝手に進んでしまう**ことがあると公式に注意書きがあります。
# MAGIC （⭐ ただし当方の検証では、1 だけでも 5 スキルとゲートは正しく動きました）
# MAGIC
# MAGIC ### ⭐ 入ったかどうかの確認
# MAGIC
# MAGIC Genie Code にこう聞いてください。
# MAGIC
# MAGIC ```
# MAGIC What skills do you have access to?
# MAGIC ```
# MAGIC
# MAGIC ⭐ Many-Model Forecasting と 5 つのサブスキルが挙がれば成功です。
# MAGIC ⚠️ 挙がらない場合は**パスが 1 文字でも違う**ことを疑ってください（Genie Code はパスに厳格です）。
# MAGIC
# MAGIC > ⭐ **今日は講師が事前に入れてあります。** この節は「自社でどう始めるか」の参考です。

# COMMAND ----------

from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
api = w.api_client
me = spark.sql("SELECT current_user()").collect()[0][0]

print("MMF スキルの配置状況")
print("=" * 78)
for path, label in [
    (f"/Users/{me}/.assistant/skills", "スキル本体"),
    (f"/Users/{me}/.assistant_instructions.md", "共通指示 (推奨)"),
]:
    try:
        api.do("GET", f"/api/2.0/workspace/get-status?path={path}")
        print(f"  ✅ {label:<18} {path}")
    except Exception:
        print(f"  ⚠️ {label:<18} {path}  ← 見つかりません")
print("=" * 78)
print("⭐ Genie Code で `What skills do you have access to?` と聞くのが確実な確認方法です。")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. ⭐ 5 つのスキルで進みます（2 分）
# MAGIC
# MAGIC ⭐ MMF は 1 つの巨大な処理ではなく、**5 段階**に分かれています。
# MAGIC ⚠️ **各段階の終わりで必ず「次に進みますか？」と聞かれます**（勝手に進みません）。
# MAGIC
# MAGIC ```
# MAGIC   ① データ準備  →  ② 系列プロファイリング  →  ③ モデルとクラスタを決める
# MAGIC        ↓                 （任意）                        ↓
# MAGIC   train_data          予測しやすい/しにくいを分類    使うモデルを選ぶ
# MAGIC                       ⭐ しにくい系列の扱いを 3 択
# MAGIC
# MAGIC                    →  ④ 予測を実行  →  ⑤ 評価とベストモデル選定
# MAGIC                              ↓                    ↓
# MAGIC                       ジョブを生成して実行    系列ごとのベストを決定
# MAGIC ```
# MAGIC
# MAGIC | # | スキル | やること | ⭐ できるもの |
# MAGIC |---|---|---|---|
# MAGIC | 1 | `/prep-and-clean-data` | 列のマッピング / 欠測・異常値の方針 | `scm_train_data` |
# MAGIC | 2 | `/profile-and-classify-series` | ⭐ **系列の性質を統計的に分類** | `scm_series_profile` / `scm_pipeline_config` |
# MAGIC | 3 | `/provision-forecasting-resources` | 使うモデルと計算資源を決める | 設定 |
# MAGIC | 4 | `/execute-mmf-forecast` | バックテストして全モデルを実行 | `scm_evaluation_output` / `scm_scoring_output` |
# MAGIC | 5 | `/post-process-and-evaluate` | ⭐ **系列ごとのベストを選ぶ** | `scm_best_models` / `scm_evaluation_summary` |
# MAGIC
# MAGIC ⭐ **`scm` の部分は「ユースケース名」**です。最初に聞かれます。
# MAGIC ⭐ 同じスキーマに複数の予測プロジェクトを共存させるための接頭辞です。

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. ⭐ 最初に投げるプロンプト（1 分）
# MAGIC
# MAGIC ⭐ 下のセルが出す内容を Genie Code にそのまま貼ってください。

# COMMAND ----------

print("=" * 78)
print("  ⭐ 最初のプロンプト")
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
# MAGIC ## 4. ⭐⭐ 聞かれることと、答え方（4 分）
# MAGIC
# MAGIC ⚠️ **ここが体験の本体です。** AI が要件を 1 つずつ確認してきます。
# MAGIC ⭐ 各質問の前に `Gate state — Skill 1: [✓ …] [→ …] [ ] …` という進捗行が出ます。
# MAGIC **どこまで決まったかが常に見える**作りです。
# MAGIC
# MAGIC ### ⭐ Skill 1（データ準備）
# MAGIC
# MAGIC | 聞かれること | ⭐ 答え方 |
# MAGIC |---|---|
# MAGIC | カタログとスキーマ | 上のプロンプトのとおり |
# MAGIC | ⭐ **何をなぜ予測するのか** | 下のセルに文例があります |
# MAGIC | ノートブックの保存先 | ⭐ **既定でよい**（`/Users/<あなた>/scm/notebooks/`） |
# MAGIC | 列のマッピング確認 | ⭐ **確認して進む**（`unique_id` = 品目\|チャネル / `ds` = ym / `y` = qty） |
# MAGIC | 外部変数を使うか | ⭐ **使わない（単変量）** — 履歴だけで予測します |
# MAGIC | ⭐ **出ない月（ゼロ）の扱い** | ⭐⭐ **ゼロのまま残す** — 「出荷がなかった」という情報なので |
# MAGIC | ⚠️ **異常値の扱い** | ⭐⭐ **丸めない** — 理由は下に書きます |
# MAGIC
# MAGIC #### ⚠️ 異常値の質問は、わざと考えてほしいところです
# MAGIC
# MAGIC 「外れ値は丸めますか？」と聞かれて **つい「はい」と答えたくなります**。
# MAGIC ⚠️ でもこのデータの大口スパイクは、海外代理店の先行注文という**実需**です。
# MAGIC 丸めてしまうと、**いちばん備えたい需要の山が予測から消えます**。
# MAGIC
# MAGIC ⭐ 「何が異常で、何が実需か」は**データを見ただけでは決められません**。
# MAGIC 業務を知っている人が判断するところです。⭐ AI が聞いてくるのは、まさにそれです。

# COMMAND ----------

print("=" * 78)
print("  ⭐ 「何をなぜ予測するのか」の文例（Skill 1 で聞かれます）")
print("=" * 78)
print("""
産業用機器の月次出荷数量を 18 か月先まで予測し、在庫計画に使いたい。
少量多品種で、出ない月がある品目もある。外部変数は使わず、履歴データだけで予測する。
""")
print("=" * 78)
print("  ⭐ Skill 3 で「クラスタ構成」を聞かれたら")
print("=" * 78)
print("""
サーバーレスのままで進めてください。モデルは CPU のみで。
""")
print("⭐ クラスタを立てる必要はありません。⚠️ GPU モデル（ニューラル予測・基盤モデル）を")
print("   選ぶと GPU クラスタが必要になるので、今日は CPU だけにします。")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. ⭐⭐ ここが今日いちばんの見せ場（3 分）
# MAGIC
# MAGIC ⭐ **Skill 2（系列プロファイリング）** が、系列を統計的に調べて
# MAGIC 「**予測しやすい系列**」と「**予測しにくい系列**」に分けます。
# MAGIC
# MAGIC そして、予測しにくい系列をどう扱うか **3 択で聞いてきます**。
# MAGIC
# MAGIC | 選択肢 | 内容 |
# MAGIC |---|---|
# MAGIC | A. 全部一緒に扱う | 予測しにくい系列も同じモデルで回す |
# MAGIC | ⭐⭐ **B. 単純なルールに退避させる** | **「去年と同じ」「平均」「ゼロ」などを当てる** |
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
# MAGIC 「去年と同じ」でも誤差 1 個未満でした。手の込んだモデルを当てる意味は薄いのです。
# MAGIC
# MAGIC ⭐ 選んだ結果は `scm_pipeline_config` に記録され、最終結果に
# MAGIC **どの経路で予測したか**（`forecast_source`）として残ります。
# MAGIC
# MAGIC ### ⭐ Skill 4 でバックテストを聞かれたら
# MAGIC
# MAGIC ⭐ **(b) 標準（ウィンドウ 3 回）** を選んでください。
# MAGIC ⚠️ 80 か月のデータで 18 か月先を予測するので、これが現実的な上限です。

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6. ⭐ 実際に通したときの結果（3 分）
# MAGIC
# MAGIC ⚠️ Skill 4 の実行には **6〜20 分**かかります。
# MAGIC ⭐ 時間内に終わらない場合は、下記の実測値と見本テーブルで結果を確認してください。
# MAGIC
# MAGIC ### ⭐ 系列の分類（Skill 2）
# MAGIC
# MAGIC | 分類 | 系列数 | 特徴 |
# MAGIC |---|---|---|
# MAGIC | 予測できる | ⭐ **29（74%）** | 平均スパース率 15% |
# MAGIC | ⚠️ 予測しにくい | ⚠️ **10（26%）** | 平均スパース率 66%（出ない月が半分以上） |
# MAGIC
# MAGIC ### ⭐⭐ 系列ごとに違うモデルが選ばれた（Skill 5）
# MAGIC
# MAGIC | 選ばれたモデル | 勝った系列数 | 平均 sMAPE |
# MAGIC |---|---|---|
# MAGIC | ⭐ SeasonalNaive（退避） | **10** | — |
# MAGIC | StatsForecastAutoTheta | 7 | 1.06 |
# MAGIC | StatsForecastCrostonSBA | 6 | ⭐ 0.65 |
# MAGIC | StatsForecastAutoETS | 5 | ⭐ **0.39** |
# MAGIC | StatsForecastAutoMfles | 5 | 0.59 |
# MAGIC | StatsForecastAutoArima | 5 | 0.71 |
# MAGIC | StatsForecastADIDA | 1 | 0.75 |
# MAGIC
# MAGIC ⚠️⚠️ **勝ち数の順位と平均成績の順位が一致していません。**
# MAGIC ⭐ 「平均でいちばん強いモデル」と「系列ごとに選ばれるモデル」は別物です。
# MAGIC **だから系列ごとに選ぶことに意味があります。**
# MAGIC
# MAGIC ### ⭐⭐ チャネルで予測の難しさがはっきり分かれた
# MAGIC
# MAGIC | チャネル | 系列数 | 平均 sMAPE |
# MAGIC |---|---|---|
# MAGIC | DOM（国内） | 20 | ⭐ **0.507** |
# MAGIC | ⚠️ EXP（海外） | 9 | ⚠️ **1.152** |
# MAGIC
# MAGIC ⭐ 国内は良好、⚠️ **海外は全系列 sMAPE > 1.0** で予測困難でした。
# MAGIC 出ない月が 40〜50% あり、大口スパイクが立つためです。
# MAGIC
# MAGIC ⭐ 勝ちパターンも分かれます: **国内は CrostonSBA / AutoETS、海外は AutoTheta**。

# COMMAND ----------

# ⭐ MMF の結果テーブルを探す（自分のスキーマ → 見本 の順）
def mmf_tables(sch: str) -> list:
    if not spark.catalog.databaseExists(sch):
        return []
    return sorted(t.name for t in spark.catalog.listTables(sch) if t.name.startswith("scm_"))


MMF_SCHEMA, found = None, []
for sch, label in [(MY, "あなたのスキーマ"), (SAMPLE, "見本")]:
    found = mmf_tables(sch)
    if found:
        MMF_SCHEMA = sch
        print(f"⭐ MMF の結果が見つかりました（{label}）: {sch}")
        break

if MMF_SCHEMA:
    for t in found:
        print(f"  {t:<38} {spark.table(f'{MMF_SCHEMA}.{t}').count():>8,} 行")
else:
    print("⚠️ MMF の結果テーブルがまだありません。")
    print("   ⭐ Skill 4 まで進めるか、講師に見本の場所を確認してください。")

# COMMAND ----------

# MAGIC %md
# MAGIC ### ⭐⭐ 需要の性質ごとに、選ばれる手法が変わる
# MAGIC
# MAGIC ⭐ **これが今日いちばん見てほしい表です。**
# MAGIC ⚠️ 1 つのモデルで全部を賄おうとすると、どこかの品目で必ず損をします。

# COMMAND ----------

# ⚠️ このテーブルは MMF（外部ツール）が作るため、列名がバージョンで変わりえます。
#    ⭐ そこで列を見てからクエリを組み立てます。
if MMF_SCHEMA and "scm_best_models" in found:
    cols = {f.name for f in spark.table(f"{MMF_SCHEMA}.scm_best_models").schema.fields}
    parts = ["model AS `選ばれたモデル`", "COUNT(*) AS `勝った系列数`"]
    if "avg_metric" in cols:
        parts.append("ROUND(AVG(avg_metric), 4) AS `平均スコア`")
    group = ["model"]
    # ⭐ どの経路で予測したか（本パイプライン / 退避）が分かると Skill 2 の判断が効いて見える
    if "forecast_source" in cols:
        parts.insert(1, "forecast_source AS `予測の経路`")
        group.append("forecast_source")
    display(spark.sql(f"""
        SELECT {', '.join(parts)}
        FROM {MMF_SCHEMA}.scm_best_models
        GROUP BY {', '.join(group)}
        ORDER BY `勝った系列数` DESC
    """))
else:
    print("⚠️ scm_best_models が見つかりませんでした（上のセルの案内を参照）。")

# COMMAND ----------

# ⚠️ 列構成は MMF のバージョンによって変わるため、そのまま表示します。
if MMF_SCHEMA and "scm_evaluation_summary" in found:
    display(spark.table(f"{MMF_SCHEMA}.scm_evaluation_summary"))
else:
    print("⚠️ scm_evaluation_summary が見つかりませんでした。")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 7. ⚠️ 実際に踏んだ落とし穴（知っておくと詰まりません）
# MAGIC
# MAGIC ⭐ 当方の検証で実際に起きたものです。
# MAGIC
# MAGIC | ⚠️ 症状 | ⭐ 対処 |
# MAGIC |---|---|
# MAGIC | ⚠️⚠️ `NotImplementedError: sc is not supported on serverless compute` | ⭐ 生成されたノートブックが `sc.defaultParallelism` を使っています。**「サーバーレスでは sc が使えないので直して」と伝える**と修正してくれます |
# MAGIC | ⚠️ 直したはずなのに同じエラーが再発 | ⭐ 編集が反映されていないことがあります。**「セル全体を書き直して」と伝える** |
# MAGIC | ⚠️ ジョブ作成がブロックされる | ⭐ 系列数が少なければ **「サーバーレスで直接実行して」** と伝えれば通ります |
# MAGIC | ⚠️ クラスタを立てようとする | ⭐ **「サーバーレスのままで」** と伝える |
# MAGIC | ⚠️ GPU が必要と言われる | ⭐ **「CPU のみで」** と伝える（統計モデルだけで十分比較できます） |
# MAGIC
# MAGIC ⭐ どれも **会話で直せます。** ⚠️ 自分でコードを直しに行かないでください。

# COMMAND ----------

# MAGIC %md
# MAGIC ## 8. ⚠️ おまけ — Unity Catalog に登録して推論する
# MAGIC
# MAGIC ⚠️ **時間が余ったら**の内容です。⭐ ここまでで十分です。
# MAGIC
# MAGIC ⭐ MMF の結果を `04`〜`05` と同じように **UC 登録 → バッチ推論**につなげられます。
# MAGIC
# MAGIC ### ⭐ Genie Code に頼む例文
# MAGIC
# MAGIC ```
# MAGIC scm_best_models のベストモデルを Unity Catalog に登録したい。
# MAGIC 入力が unique_id、出力が 18 か月分の予測（日付・予測値・使ったモデル名）に
# MAGIC なるようにしてください。
# MAGIC ```
# MAGIC
# MAGIC ### ⚠️ ここで引っかかる点（実測）
# MAGIC
# MAGIC | ⚠️ | 内容 |
# MAGIC |---|---|
# MAGIC | ⚠️ `model_uri` が空 | ⭐ 代わりに **`model_pickle`**（学習済みモデル本体）が入っています。これを使います |
# MAGIC | ⚠️ 系列ごとに 29 個登録すると管理が煩雑 | ⭐ **1 つの pyfunc にまとめて**、`unique_id` で内部ルーティングさせます |
# MAGIC | ⚠️⚠️ **最初の版が「ルーティングだけ」返してきた** | ⭐ **「入力は unique_id、出力は予測値そのもの」と明示**して作り直させました |
# MAGIC
# MAGIC ### ⭐ 最終的な形（これが正解）
# MAGIC
# MAGIC | | |
# MAGIC |---|---|
# MAGIC | 入力 | `unique_id`（例: `K350A\|DOM`） |
# MAGIC | 出力 | ⭐ **1 系列あたり 18 行** — `unique_id` / `ds` / `forecast` / `model` |
# MAGIC | 依存 | pandas と numpy だけ（⭐ statsforecast 不要） |
# MAGIC
# MAGIC ⭐ 39 系列で **702 行**（39 × 18 か月）の予測が得られました。
# MAGIC
# MAGIC ⚠️ **「入力は何で、出力は何か」を最初に指定する**のがコツです。
# MAGIC ⭐ 曖昧なまま頼むと、使いにくい形で作られます。

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
# MAGIC | 多重季節性 | `StatsForecastAutoMfles` | CPU |
# MAGIC | Prophet | `SKTimeProphet` | CPU |
# MAGIC | LightGBM | `MLForecastLGBM` / `MLForecastAutoLGBM` | CPU |
# MAGIC | ⭐ 間欠需要向け | `StatsForecastCrostonSBA` / `ADIDA` / `IMAPA` / `TSB` | CPU |
# MAGIC | ニューラル予測 (NHITS など) | `NeuralForecastAutoNHITS` など | ⚠️ GPU |
# MAGIC | 基盤モデル (Chronos / TimesFM) | `ChronosBolt*` / `Chronos2` / `TimesFM_2_5_200m` | ⚠️ GPU |
# MAGIC | ⭐⭐ **精度の出ない系列を見切る仕組み** | ⭐ **系列プロファイリング + 退避ルール** | CPU |
# MAGIC
# MAGIC ⭐ **ニューラル予測と基盤モデル以外は CPU だけで動きます。**
# MAGIC ⚠️ 一方で **アンサンブル（複数モデルの重み付き合成）に相当する機能はありません**。
# MAGIC 「系列ごとにベストを 1 つ選ぶ」という考え方です。

# COMMAND ----------

# MAGIC %md
# MAGIC ## ✅ ここまでできたら
# MAGIC
# MAGIC 次は **`99_your_own_data`** — ⭐ **自由時間**です。
# MAGIC 自分の手元のデータを取り込んで、今日やったことを試してみてください。
# MAGIC
# MAGIC ⭐ `99` も同じく **Genie Code に言葉で頼む**形になっています。
