# Databricks notebook source
# MAGIC %md
# MAGIC # 00 — 自分の作業場所とパイプラインを作る
# MAGIC
# MAGIC > 🔑 **必要な権限**: カタログへの `USE CATALOG` と `CREATE SCHEMA` / Volume の `READ VOLUME`
# MAGIC >
# MAGIC > ⏱ **目安 8 分**（うちパイプラインの初回実行に 4〜6 分かかります）
# MAGIC
# MAGIC ## このノートブックでやること
# MAGIC
# MAGIC 1. **あなた専用のスキーマと Volume** を作る
# MAGIC 2. ⭐ **見本の CSV を自分の Volume にコピーする**
# MAGIC 3. **あなた専用のパイプライン**を作る（CSV → bronze → silver → gold）
# MAGIC 4. 実行して、**あなたのスキーマに gold テーブルができる**のを確認する
# MAGIC
# MAGIC ```
# MAGIC   fc_sample/landing/          ← 見本の CSV（読み取り専用）
# MAGIC          │  ② コピー
# MAGIC          ▼
# MAGIC   fc_ws_<あなた>/landing/      ← あなたの CSV 置き場
# MAGIC          │  ③④ あなたのパイプライン
# MAGIC          ▼
# MAGIC   fc_ws_<あなた>/
# MAGIC      bronze_*  ← 届いたまま
# MAGIC      silver_*  ← 重複排除・月末日に正規化
# MAGIC      gold      ← fct_shipments / dim_item / fct_inventory / ...
# MAGIC ```
# MAGIC
# MAGIC ⭐⭐ **ゴールは「見本 (`fc_sample`) を自分のスキーマに再現すること」です。**
# MAGIC 見本には完成形が全部入っているので、詰まったら中を見比べてください。
# MAGIC
# MAGIC > ⭐ **なぜ一人ずつパイプラインを作るのか**
# MAGIC >
# MAGIC > 本来のデータ基盤なら、bronze → silver → gold は**共通のスキーマに 1 セット**作り、
# MAGIC > 全員がそれを参照します。今回は「**取り込みから自分の手で体験する**」ことが目的なので、
# MAGIC > 一人ひとりが自分のスキーマに一式を作ります。⚠️ 本番でこの形にする必要はありません。
# MAGIC
# MAGIC > ⚠️ **パイプラインの「作り方」は今日の対象外です。**
# MAGIC > ここでは「すでに書かれた SQL を、自分のスキーマ向けに動かす」だけをやります。
# MAGIC > SQL の中身は最後のセルで読めるようにしてあります。
# MAGIC
# MAGIC ## ⚠️ 「予測」のテーブルが最初からある理由
# MAGIC
# MAGIC gold の中に `fct_forecast_baseline` という予測のテーブルが最初から入っています。
# MAGIC まだ何もモデルを作っていないのに、なぜ予測があるのか——
# MAGIC
# MAGIC ⭐ これは **機械学習の予測ではありません**。
# MAGIC 「**去年の同じ月と同じ数量が出る**」というルールだけの予測です。
# MAGIC
# MAGIC ```
# MAGIC   2026年7月の予測値  =  2025年7月の実績値      ← これだけ
# MAGIC ```
# MAGIC
# MAGIC 実績データから機械的に計算しているので、架空の数字ではありません。
# MAGIC これを最初から置いてある理由は 2 つあります。
# MAGIC
# MAGIC | # | 理由 |
# MAGIC |---|---|
# MAGIC | 1 | このあとダッシュボードと Genie Agent で「**予測は当たっているのか**」を扱いたいので、その時点で予測が存在している必要があるため |
# MAGIC | 2 | ⭐⭐ **モデルを作ったら、必ずこれと比べるため** |
# MAGIC
# MAGIC ⭐ **2 が本題です。** 「モデルを作りました」だけでは価値が測れません。
# MAGIC ⚠️ そして「去年と同じ」は、実際にやってみると**意外に強い**予測です。
# MAGIC 手の込んだモデルがこれに負けることは珍しくありません。
# MAGIC
# MAGIC ⭐ 多くの現場で実質的な予測が「Excel で去年の数字を写す」であることを踏まえると、
# MAGIC これは「**今の運用**」そのものだと考えてください。
# MAGIC 今日つくるモデルの相手は、これです。

# COMMAND ----------

# MAGIC %run ./_config

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. ⭐ 見本の CSV を自分の Volume にコピーする
# MAGIC
# MAGIC ⭐ 見本の Volume は**読み取り専用**なので、自分の Volume にコピーしてから取り込みます。
# MAGIC
# MAGIC ⚠️ **すでにあるファイルは上書きしません**（何度実行しても安全です）。
# MAGIC ⭐ ハンズオン中に見本へ**新しい月の CSV が追加**されたら、
# MAGIC このセルをもう一度実行すれば差分だけコピーされます。

# COMMAND ----------

import os
import shutil

copied, skipped = [], []
for sub in sorted(os.listdir(SAMPLE_LANDING)):
    src_dir = f"{SAMPLE_LANDING}/{sub}"
    if not os.path.isdir(src_dir):
        continue
    dst_dir = f"{LANDING_PATH}/{sub}"
    dbutils.fs.mkdirs(dst_dir)
    for name in sorted(os.listdir(src_dir)):
        src, dst = f"{src_dir}/{name}", f"{dst_dir}/{name}"
        if os.path.exists(dst):
            skipped.append(f"{sub}/{name}")
            continue
        shutil.copyfile(src, dst)
        copied.append(f"{sub}/{name}")

if copied:
    print("コピーしました:")
    for c in copied:
        print(f"  ✅ {c}")
if skipped:
    print("\nすでにあるので飛ばしました:")
    for s in skipped:
        print(f"  ⏭  {s}")
if not copied and not skipped:
    print("⚠️ 見本の CSV が見つかりませんでした。講師に確認してください。")

# COMMAND ----------

# MAGIC %md
# MAGIC ### 自分の Volume の中身を確認する

# COMMAND ----------

for sub in sorted(os.listdir(LANDING_PATH)):
    d = f"{LANDING_PATH}/{sub}"
    if os.path.isdir(d):
        entries = sorted(os.listdir(d))
        print(f"  {sub + '/':<22} {', '.join(entries) if entries else '(空)'}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. パイプラインを作る
# MAGIC
# MAGIC ⭐ 画面から作ることもできますが、ここでは **API を 1 回呼ぶだけ**にしています。
# MAGIC 「同じ SQL を、書き込み先のスキーマだけ変えて動かす」ことが分かれば十分です。
# MAGIC
# MAGIC > 💡 同じ名前のパイプラインが既にあれば作り直しません（何度実行しても安全です）。

# COMMAND ----------

import time
import urllib.parse

from databricks.sdk import WorkspaceClient

# ⭐ パイプラインの作成・実行は REST API を直接呼びます。
#    SDK の引数名はバージョンによって変わることがあるため（例: `schema` と `target`）、
#    ランタイムに同梱された SDK のバージョンに左右されない形にしています。
w = WorkspaceClient()
api = w.api_client

# このノートブックの 1 階層上が repo のルート（notebooks/ の親）
_nb_path = dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(_nb_path), ".."))

SQL_FILES = ["01_bronze.sql", "02_silver.sql", "03_gold.sql"]
PIPELINE_NAME = f"[handson] {USER_SUFFIX} のメダリオンパイプライン"

print(f"パイプライン名 : {PIPELINE_NAME}")
print(f"書き込み先     : {MY}")
print(f"読み取り元     : {LANDING_PATH}")
print("\n使う SQL:")
for f in SQL_FILES:
    print(f"  {REPO_ROOT}/src/pipelines/{f}")

# COMMAND ----------

# 同じ名前のパイプラインが既にあれば作り直さない（何度実行しても安全）
_filter = urllib.parse.quote(f"name LIKE '{PIPELINE_NAME}'")
found = api.do("GET", f"/api/2.0/pipelines?filter={_filter}") or {}
existing = [p for p in (found.get("statuses") or []) if p.get("name") == PIPELINE_NAME]

if existing:
    pipeline_id = existing[0]["pipeline_id"]
    print(f"✅ 既存のパイプラインを使います: {pipeline_id}")
else:
    created = api.do(
        "POST",
        "/api/2.0/pipelines",
        body={
            "name": PIPELINE_NAME,
            "catalog": catalog,
            # 書き込み先のスキーマ。ここを自分のスキーマにするだけで、
            # 同じ SQL が「自分専用のパイプライン」になります。
            "schema": schema,
            "serverless": True,
            "continuous": False,
            "development": True,
            # SQL 側から ${landing_path} として参照される
            "configuration": {"landing_path": LANDING_PATH},
            "libraries": [
                {"file": {"path": f"{REPO_ROOT}/src/pipelines/{f}"}} for f in SQL_FILES
            ],
        },
    )
    pipeline_id = created["pipeline_id"]
    print(f"✅ パイプラインを作成しました: {pipeline_id}")
    # ⚠️ 作成直後は内部の初期化が終わっていないことがあり、すぐ実行すると失敗します。
    #    少し待ってから実行に進みます（下の実行セルにもリトライを入れてあります）。
    time.sleep(15)

pipeline_url = f"{w.config.host}/pipelines/{pipeline_id}"
displayHTML(f'<a href="{pipeline_url}" target="_blank">▶ パイプラインを画面で開く</a>')

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. 実行する
# MAGIC
# MAGIC ⚠️ **初回は 4〜6 分かかります**（サーバーレスの計算資源が立ち上がるため）。
# MAGIC 上のリンクからパイプラインの画面を開くと、bronze → silver → gold が
# MAGIC 順に緑になっていく様子が見られます。
# MAGIC
# MAGIC > 💡 待っている間に、いちばん下のセルで SQL の中身を読んでみてください。

# COMMAND ----------

TERMINAL = {"COMPLETED", "FAILED", "CANCELED"}
MAX_TRIES = 3


def run_pipeline_once() -> str:
    """パイプラインを 1 回実行し、終了状態を返す。"""
    started_update = api.do("POST", f"/api/2.0/pipelines/{pipeline_id}/updates", body={})
    update_id = started_update["update_id"]
    print(f"    実行開始 (update_id={update_id[:12]}…)")

    t0 = time.time()
    state = None
    while True:
        info = api.do("GET", f"/api/2.0/pipelines/{pipeline_id}/updates/{update_id}")
        new_state = (info.get("update") or {}).get("state", "UNKNOWN")
        if new_state != state:
            print(f"      [{int(time.time() - t0):>4}秒] {new_state}")
            state = new_state
        if state in TERMINAL:
            return state
        time.sleep(15)


# ⚠️ 作ったばかりのパイプラインは、1 回目の実行がまれに失敗します
#    （内部の初期化と実行が重なるため）。数十秒待って再実行すれば通るので、
#    ここでは自動で 3 回まで試します。
started = time.time()
final_state = None
for attempt in range(1, MAX_TRIES + 1):
    print(f"  試行 {attempt}/{MAX_TRIES}")
    final_state = run_pipeline_once()
    if final_state == "COMPLETED":
        break
    if attempt < MAX_TRIES:
        print(f"  ⚠️ {final_state} で終了しました。30 秒待って再実行します…\n")
        time.sleep(30)

elapsed = int(time.time() - started)
if final_state == "COMPLETED":
    print(f"\n✅ 完了しました（合計 {elapsed} 秒）")
else:
    raise RuntimeError(
        f"パイプラインが {MAX_TRIES} 回とも {final_state} で終了しました。"
        "上のリンクから画面を開いてエラー内容を確認してください。"
    )

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. できたテーブルを確認する
# MAGIC
# MAGIC ⭐ 以降のパートで使うのは **gold の 7 テーブル**です。

# COMMAND ----------

GOLD_TABLES = [
    ("fct_shipments", "月次出荷実績（需要予測の入力になる中心テーブル）"),
    ("dim_item", "品目マスタ（カテゴリ / 需要分類 / 国内専用フラグ）"),
    ("dim_channel", "チャネル定義（DOM = 国内 / EXP = 海外）"),
    ("dim_lead_time", "品目 × 拠点の標準リードタイム"),
    ("fct_inventory", "拠点別の月末在庫・安全在庫・欠品フラグ"),
    ("fct_forecast_baseline", "「去年と同じ」というルールだけの予測（機械学習ではありません）"),
    ("fct_forecast_accuracy", "上の予測と実績の突き合わせ（誤差を率と個数の両方で持つ）"),
]

print(f"{'テーブル':<26} {'行数':>10}   説明")
print("-" * 100)
for name, desc in GOLD_TABLES:
    n = spark.table(f"{MY}.{name}").count()
    print(f"{name:<26} {n:>10,}   {desc}")

# COMMAND ----------

# MAGIC %md
# MAGIC ### 中身を少し見てみましょう

# COMMAND ----------

# MAGIC %sql
# MAGIC -- 品目ごとの需要の性質。⭐ 品目によって「需要の出方」がまったく違うことに注目してください。
# MAGIC --   smooth       = 毎月安定して出る
# MAGIC --   erratic      = 毎月出るが数量が振れる
# MAGIC --   intermittent = 出ない月がある
# MAGIC --   lumpy        = 出ない月があり、出ると数量も大きく振れる
# MAGIC -- ⚠️ だから「全品目に同じモデル」ではうまくいきません。
# MAGIC -- ⚠️ 日本語の別名は必ずバッククォートで囲みます（囲まないと INVALID_IDENTIFIER になります）
# MAGIC SELECT
# MAGIC   demand_class            AS `需要分類`,
# MAGIC   COUNT(*)                AS `品目数`,
# MAGIC   ROUND(MIN(adi), 2)      AS `ADI最小`,
# MAGIC   ROUND(MAX(adi), 2)      AS `ADI最大`,
# MAGIC   ROUND(MIN(cv2), 2)      AS `CV2最小`,
# MAGIC   ROUND(MAX(cv2), 2)      AS `CV2最大`
# MAGIC FROM dim_item
# MAGIC GROUP BY demand_class
# MAGIC ORDER BY `品目数` DESC

# COMMAND ----------

# MAGIC %sql
# MAGIC -- ⭐ 「去年と同じ」というだけの予測（前年同月ナイーブ）が、どれくらい当たっているか。
# MAGIC -- ⚠️ 率(APE)で見ると酷い数字ですが、これは**数量の少ない品目が率を押し上げている**ためです。
# MAGIC --    個数(絶対誤差)で見ると印象が変わります。「どの指標で見るか」で結論が変わる好例です。
# MAGIC SELECT
# MAGIC   i.demand_class                         AS `需要分類`,
# MAGIC   COUNT(*)                               AS `件数`,
# MAGIC   ROUND(AVG(a.ape) * 100, 1)             AS `平均誤差率_pct`,
# MAGIC   ROUND(AVG(a.abs_error), 1)             AS `平均誤差_個数`,
# MAGIC   ROUND(AVG(a.within_interval) * 100, 1) AS `予測区間に収まった率_pct`
# MAGIC FROM fct_forecast_accuracy a
# MAGIC JOIN dim_item i USING (item_code)
# MAGIC GROUP BY i.demand_class
# MAGIC ORDER BY `平均誤差率_pct` DESC

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. （待ち時間用）パイプラインの SQL を読んでみる
# MAGIC
# MAGIC ⚠️ 書き方を覚える必要はありません。**3 層に分ける考え方**だけ持ち帰ってください。
# MAGIC
# MAGIC | 層 | 役割 | なぜ分けるのか |
# MAGIC |---|---|---|
# MAGIC | **bronze** | 届いた CSV をそのまま残す | ⭐ 元データに戻って調べ直せる状態を必ず残す |
# MAGIC | **silver** | 重複排除・型変換・月末日に正規化 | ⭐ 下流が「汚れ」を気にしなくてよくなる |
# MAGIC | **gold** | 業務でそのまま使える形 | ⭐ ダッシュボード / Genie / モデルが直接読む |
# MAGIC
# MAGIC ⭐ ポイントは **Auto Loader**（`FROM STREAM read_files(...)`）です。
# MAGIC 一度取り込んだファイルは二度読まれないので、**新しい CSV を置いて実行し直すだけで差分が入ります**。
# MAGIC ⚠️ 逆に、同じ名前のファイルを上書きしても取り込まれません。

# COMMAND ----------

for f in SQL_FILES:
    path = f"/Workspace{REPO_ROOT}/src/pipelines/{f}" if not REPO_ROOT.startswith("/Workspace") else f"{REPO_ROOT}/src/pipelines/{f}"
    print("=" * 78)
    print(f"  {f}")
    print("=" * 78)
    try:
        with open(path, encoding="utf-8") as fh:
            print(fh.read())
    except OSError as e:
        print(f"  （ファイルを開けませんでした: {e}）")
        print(f"  画面左の Workspace から {REPO_ROOT}/src/pipelines/{f} を開いてください。")

# COMMAND ----------

# MAGIC %md
# MAGIC ## ⭐ 見本と見比べる
# MAGIC
# MAGIC ⭐ 見本 (`fc_sample`) と自分のスキーマで、**同じ行数になっているか**を確認します。
# MAGIC ⚠️ 合っていなければ、どこかでコピーか実行が抜けています。

# COMMAND ----------

print(f"{'テーブル':<26} {'あなた':>10} {'見本':>10}   一致")
print("-" * 62)
for name, _ in GOLD_TABLES:
    mine = spark.table(f"{MY}.{name}").count()
    try:
        ref = spark.table(f"{SAMPLE}.{name}").count()
        mark = "✅" if mine == ref else "⚠️ ずれています"
    except Exception:  # noqa: BLE001
        ref, mark = -1, "（見本が見つかりません）"
    print(f"{name:<26} {mine:>10,} {ref:>10,}   {mark}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## ✅ ここまでできたら
# MAGIC
# MAGIC 次は **`01_dashboard`** に進みます。
# MAGIC いま作った gold テーブルを使って、ダッシュボードを作ります。
