# Databricks notebook source
# MAGIC %md
# MAGIC # 07 — 自動実行にする（Lakeflow Jobs）
# MAGIC
# MAGIC > ⏱ **目安 16 分**
# MAGIC
# MAGIC ⭐ ここまで全部、**手で 1 つずつ実行してきました**。
# MAGIC ⚠️ このままだと来月も同じ手作業が必要です。今日の話が「便利な道具の紹介」で
# MAGIC 終わってしまうのはここです。
# MAGIC
# MAGIC ## ⭐ 目指す形
# MAGIC
# MAGIC ```
# MAGIC   ① 新しい CSV を置く          （人がやるのはここだけ）
# MAGIC        ↓
# MAGIC   ② パイプラインが動く         （bronze → silver → gold が更新される）
# MAGIC        ↓
# MAGIC   ③ 再学習して比べる           （勝ったら本番を入れ替える / 負けたら据え置き）
# MAGIC        ↓
# MAGIC   ④ 予測を作り直し、精度を記録  （評価テーブルが更新される）
# MAGIC        ↓
# MAGIC      ダッシュボードが更新され、メールが届く
# MAGIC ```
# MAGIC
# MAGIC ⭐⭐ **このパートでは、これを実際に通します。**
# MAGIC 講師から受け取った**新しい月の CSV** を自分の置き場に置いて、
# MAGIC ②〜④ が自動で動くところまで見ます。
# MAGIC
# MAGIC ## このパートでやること
# MAGIC
# MAGIC | | 内容 | 目安 |
# MAGIC |---|---|---|
# MAGIC | 1 | ⭐ **画面からジョブを作る**（タスクを 3 つ繋げる） | 6 分 |
# MAGIC | 2 | ⭐ **CSV が置かれたら動く**ように設定する | 2 分 |
# MAGIC | 3 | ⭐⭐ **新しい月の CSV を手で置く** | 2 分 |
# MAGIC | 4 | ⭐⭐ **一連の更新を確認する** | 5 分 |
# MAGIC | 5 | 失敗したときの通知を設定する | 1 分 |
# MAGIC
# MAGIC > ⭐ **動くお手本があります。**
# MAGIC > `[handson] 見本 需要予測の月次更新` というジョブが既に作られていて、
# MAGIC > 上の ①〜④ がそのまま 4 つのタスクになっています。
# MAGIC > **迷ったら開いて中を見てください**（答え合わせに使えます）。

# COMMAND ----------

# MAGIC %run ./_config

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. ⭐ 画面からジョブを作る（6 分）
# MAGIC
# MAGIC ⭐ **ノートブックからではなく画面で作ります。** 業務の担当者が自分で組めることを
# MAGIC 体験してほしいためです。
# MAGIC
# MAGIC ### 手順
# MAGIC
# MAGIC 1. 左メニュー **「ジョブとパイプライン」** → **「作成」** → **「ジョブ」**
# MAGIC 2. ⚠️ **ジョブ名は下のセルに出る名前をそのままコピーしてください**
# MAGIC    （後の確認セルがこの名前でジョブを探します）
# MAGIC 3. **タスク 1** を作る
# MAGIC    | 項目 | 値 |
# MAGIC    |---|---|
# MAGIC    | タスク名 | `pipeline` |
# MAGIC    | 種類 | **パイプライン** |
# MAGIC    | パイプライン | ⭐ `00` で作った**自分のパイプライン**（下のセルに名前が出ます） |
# MAGIC 4. **タスク 2** を追加する（**「＋タスクを追加」**）
# MAGIC    | 項目 | 値 |
# MAGIC    |---|---|
# MAGIC    | タスク名 | `retrain` |
# MAGIC    | 種類 | **ノートブック** |
# MAGIC    | パス | ⭐ `06_retrain`（下のセルにパスが出ます） |
# MAGIC    | 依存 | `pipeline` |
# MAGIC 5. **タスク 3** を追加する
# MAGIC    | 項目 | 値 |
# MAGIC    |---|---|
# MAGIC    | タスク名 | `inference` |
# MAGIC    | 種類 | **ノートブック** |
# MAGIC    | パス | ⭐ `05_batch_inference` |
# MAGIC    | 依存 | `retrain` |
# MAGIC 6. 右上 **「保存」**。⚠️ **まだ実行しません**（次で自動起動を設定します）
# MAGIC
# MAGIC > ⭐ **タスク 3 が「評価の更新」も担っています。**
# MAGIC > `05` は予測を作り直したあと、**予測と実績を突き合わせた結果**を
# MAGIC > `fct_forecast_accuracy_all` に書き出します。
# MAGIC > ⚠️ ここが無いと「精度は誰かが手でクエリを書いたときにしか分からない」状態になり、
# MAGIC > 「気づいたら 3 か月ずれ続けていた」が起きます。
# MAGIC
# MAGIC > ⭐ **タスクの依存関係が絵で見える**のがポイントです。
# MAGIC > 「パイプラインが終わってから再学習する」という順序が、コードを読まなくても分かります。

# COMMAND ----------

import os

JOB_NAME = f"需要予測の月次更新_{USER_SUFFIX}"
PIPELINE_NAME = f"[handson] {USER_SUFFIX} のメダリオンパイプライン"

_nb_path = dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
NB_DIR = os.path.dirname(_nb_path)

print("ジョブの設定でコピーして使う値")
print("=" * 78)
print(f"  ⭐ ジョブ名               : {JOB_NAME}")
print(f"  タスク 1（パイプライン）  : {PIPELINE_NAME}")
print(f"  タスク 2（ノートブック）  : {NB_DIR}/06_retrain")
print(f"  タスク 3（ノートブック）  : {NB_DIR}/05_batch_inference")
print("=" * 78)

from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
displayHTML(f'<a href="{w.config.host}/jobs" target="_blank">▶ ジョブの画面を開く</a>')

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. ⭐ 「CSV が置かれたら動く」ように設定する（2 分）
# MAGIC
# MAGIC ⭐ ジョブは**決めた時刻**にも動かせますが、今回は
# MAGIC **「新しいファイルが置かれたら動く」**にします。これが目指す形の ① です。
# MAGIC
# MAGIC ### 手順
# MAGIC
# MAGIC 1. ジョブ画面の右側 **「スケジュールとトリガー」** → **「トリガーを追加」**
# MAGIC 2. トリガーの種類で **「ファイル到着」** を選ぶ
# MAGIC 3. **ストレージの場所**に、下のセルに出るパスを貼る
# MAGIC 4. **「保存」**
# MAGIC
# MAGIC | 種類 | いつ動くか | 使いどころ |
# MAGIC |---|---|---|
# MAGIC | スケジュール | 決めた日時 | 「毎月 1 日の朝 6 時に回す」 |
# MAGIC | ⭐ **ファイル到着** | 指定の場所に**新しいファイルが来たとき** | ⭐ **今回これを使います** |
# MAGIC | テーブル更新 | 上流のテーブルが更新されたとき | 他チームのデータに追随する |
# MAGIC | 連続 | 常に動かし続ける | リアルタイム処理 |
# MAGIC
# MAGIC ### ⚠️ ファイル到着トリガーの癖
# MAGIC
# MAGIC | ⚠️ 注意点 | 内容 |
# MAGIC |---|---|
# MAGIC | ⚠️⚠️ **同名ファイルの上書きでは発火しない** | 「毎月同じ `demand.csv` を上書き」では動きません。**新しいファイル名**が必要 |
# MAGIC | 検知の間隔 | 約 1 分ごとの確認 |
# MAGIC | ⚠️⚠️ **設定直後の 1 本目は発火しないことがある** | 設定した時点の中身を「基準」として記録するため。⭐ **2 本目からは 1 分以内に反応します**（実測 40 秒） |
# MAGIC | ファイル数の上限 | 監視対象が 1 万ファイルを超えると使えません（古いものは移動する運用が必要） |
# MAGIC
# MAGIC ⭐ **だからこのハンズオンでは CSV を月ごとに別ファイル名にしています。**
# MAGIC （`shipments_2020_2026_07.csv` と `shipments_2026_08.csv`）

# COMMAND ----------

WATCH_PATH = f"{LANDING_PATH}/shipments/"
print("ファイル到着トリガーの「ストレージの場所」に貼る値")
print("=" * 78)
print(f"  {WATCH_PATH}")
print("=" * 78)
print()
print("⭐ ここは 00 で作った自分の CSV 置き場です。")
print("   パイプラインが取り込んでいる場所と同じなので、")
print("   置いたファイルがそのまま bronze に流れます。")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. ⭐⭐ 新しい月の CSV を置く（2 分）
# MAGIC
# MAGIC ⭐ **ここが今日の締めです。** 講師から `shipments_2026_08.csv` を受け取ってください
# MAGIC （2026 年 8 月の出荷実績です）。
# MAGIC
# MAGIC ### 手順
# MAGIC
# MAGIC 1. 受け取ったファイルを自分の PC に保存する
# MAGIC 2. 左メニュー **「カタログ」** → 下のセルに出る場所まで降りる
# MAGIC 3. 右上 **「このボリュームにアップロード」** → `shipments_2026_08.csv` を選ぶ
# MAGIC
# MAGIC ⚠️ **`shipments/` フォルダの中に置いてください。** 1 つ上に置くと取り込まれません。

# COMMAND ----------

print("アップロード先")
print("=" * 78)
print(f"  {WATCH_PATH}")
print("=" * 78)
print()
print("カタログ画面での場所:")
print(f"  {catalog} → {schema} → ボリューム → {LANDING_VOLUME} → shipments")
print()

import os

_before = sorted(os.listdir(f"{LANDING_PATH}/shipments")) if os.path.isdir(f"{LANDING_PATH}/shipments") else []
print("今ある出荷実績ファイル:")
for f in _before:
    print(f"  {f}")

displayHTML(
    f'<a href="{w.config.host}/explore/data/volumes/{catalog}/{schema}/{LANDING_VOLUME}" '
    'target="_blank">▶ アップロード画面を開く</a>'
)

# COMMAND ----------

# MAGIC %md
# MAGIC ### 置けたか確認する
# MAGIC
# MAGIC ⭐ アップロードしたら下のセルを実行してください。

# COMMAND ----------

files = sorted(os.listdir(f"{LANDING_PATH}/shipments"))
print("出荷実績ファイル:")
for f in files:
    mark = "⭐ 新規" if f not in _before else "  "
    print(f"  {mark} {f}")

if "shipments_2026_08.csv" in files:
    print("\n✅ 置けました。ジョブが自動で起動するのを待ちます（次のセクション）。")
else:
    print("\n⚠️ shipments_2026_08.csv が見つかりません。")
    print("   置き場所が shipments/ の中になっているか確認してください。")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. ⭐⭐ 一連の更新を確認する（5 分）
# MAGIC
# MAGIC ⭐ **ジョブ画面を開いて、勝手に実行が始まるのを見てください。**
# MAGIC
# MAGIC ```
# MAGIC   CSV を置いた
# MAGIC      ↓ （約 1 分で検知）
# MAGIC   pipeline   … 2026-08 を取り込む      ⚠️ 4〜6 分（サーバーレスの起動時間）
# MAGIC      ↓
# MAGIC   retrain    … 再学習して比べる
# MAGIC      ↓
# MAGIC   inference  … 予測を作り直し、精度を記録
# MAGIC ```
# MAGIC
# MAGIC ### ⚠️ 3 分待っても始まらなかったら
# MAGIC
# MAGIC ⭐ **トリガーの設定直後は検知に数分かかることがあります。** 待てない場合は、
# MAGIC ジョブ画面の右上 **「今すぐ実行」** で手動起動してください。
# MAGIC ⚠️ **手で起動しても、この後の結果は同じです。**
# MAGIC （置いたファイルはもう `shipments/` にあるので、パイプラインが取り込みます）
# MAGIC
# MAGIC > ⭐ **待っている間に 5.（通知の設定）を読んでおいてください。**

# COMMAND ----------

# ⭐ 自分のジョブの実行状況を出す
#    ⚠️ SDK の引数名はバージョンで変わることがあるため REST を直接呼びます（00 と同じ方針）
import time
import urllib.parse

api = w.api_client

_found = api.do("GET", f"/api/2.1/jobs/list?name={urllib.parse.quote(JOB_NAME)}&limit=5") or {}
_jobs = _found.get("jobs") or []

if not _jobs:
    print(f"⚠️ ジョブ「{JOB_NAME}」が見つかりません。")
    print("   1. の手順で、ジョブ名を上のセルの出力からそのままコピーして作ってください。")
else:
    job_id = _jobs[0]["job_id"]
    print(f"ジョブ: {JOB_NAME}  (id={job_id})")
    print(f"{w.config.host}/jobs/{job_id}")
    print()
    _runs = (api.do("GET", f"/api/2.1/jobs/runs/list?job_id={job_id}&limit=5") or {}).get("runs") or []
    if not _runs:
        print("まだ実行されていません。")
        print("⭐ もう少し待つか、ジョブ画面の「今すぐ実行」で起動してください。")
    for r in _runs:
        st = r.get("state", {})
        started = time.strftime("%H:%M:%S", time.localtime((r.get("start_time") or 0) / 1000))
        # ⭐ きっかけが FILE_ARRIVAL なら「CSV を置いたから動いた」ということ
        print(f"  {started}  きっかけ={r.get('trigger', '-'):<14} "
              f"{st.get('life_cycle_state', '')} {st.get('result_state') or ''}")

# COMMAND ----------

# MAGIC %md
# MAGIC ### ⭐⭐ ジョブが終わったら、3 つを確認してください
# MAGIC
# MAGIC ⭐ **人がやったのは「CSV を置く」だけ**なのに、この 3 つが全部更新されています。

# COMMAND ----------

display(spark.sql(f"""
    SELECT '① データ'          AS `確認するもの`,
           CAST(MAX(ym) AS STRING) AS `結果`,
           '2026-08-31 になっていれば取り込み成功' AS `見かた`
    FROM {MY}.fct_shipments
    UNION ALL
    SELECT '③ 評価テーブル',
           CAST(MAX(ym) AS STRING),
           '2026-08-31 まで精度が記録されている'
    FROM {MY}.fct_forecast_accuracy_all
"""))

# COMMAND ----------

# MAGIC %md
# MAGIC #### ② モデルのバージョン
# MAGIC
# MAGIC ⭐ **バージョンが 1 つ増えています。** 再学習が走った証拠です。
# MAGIC ⚠️ 昇格したかどうかは `@champion` がどのバージョンを指しているかで分かります。

# COMMAND ----------

print("⭐ 下のリンクから Unity Catalog を開いて、次の 2 つを見てください。")
print()
print("  1. バージョンが 1 つ増えている        → 再学習が走った証拠")
print("  2. @champion がどのバージョンにあるか")
print("       最新バージョン → ⭐ 昇格した")
print("       前のバージョン → ⚠️ 見送り（どちらも正しい結果です）")
print()
print("⭐ ジョブのタスク retrain のログにも、判定の内容がそのまま出ています。")

displayHTML(
    f'<a href="{w.config.host}/explore/data/models/{catalog}/{schema}/demand_forecast" '
    'target="_blank">▶ Unity Catalog でバージョンとエイリアスを見る</a>'
)

# COMMAND ----------

# MAGIC %md
# MAGIC #### ⭐ ダッシュボードも更新されています
# MAGIC
# MAGIC ⭐ `01` で作ったダッシュボードを開き直してください。
# MAGIC **2026-08 が増えているはずです。** 何も手を加えていません。
# MAGIC
# MAGIC ⭐⭐ **これが「毎月確実に回る」の中身です。**

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. 失敗したときの通知を設定する（1 分）
# MAGIC
# MAGIC ⚠️ **自動化でいちばん怖いのは「止まっているのに誰も気づかない」ことです。**
# MAGIC
# MAGIC ⭐ 手作業なら「今月やってないな」と気づけますが、自動化すると気づけません。
# MAGIC だから通知を必ず入れます。
# MAGIC
# MAGIC ### 手順
# MAGIC
# MAGIC 1. ジョブ画面の右側 **「ジョブ通知」** → **「通知を編集」**
# MAGIC 2. **「＋通知を追加」**
# MAGIC 3. 自分のメールアドレスを入れて、**「失敗時」** にチェック
# MAGIC
# MAGIC ⭐ メール以外に Slack や Teams にも送れます（通知先を先に登録しておく必要があります）。
# MAGIC
# MAGIC ### ⭐ 「長時間かかりすぎ」も通知できます
# MAGIC
# MAGIC 「失敗」だけでなく **「想定より時間がかかっている」** でも通知を出せます。
# MAGIC ⚠️ 止まっていないけれど終わらない、というのが実務では一番厄介なので、
# MAGIC これも入れておくと安心です。

# COMMAND ----------

# MAGIC %md
# MAGIC ## ⭐ ここまでで何が変わったか
# MAGIC
# MAGIC | | 今まで | ⭐ これから |
# MAGIC |---|---|---|
# MAGIC | データの取り込み | 毎月 CSV を手でダウンロード | ⭐ 置くだけ / 自動で取り込まれる |
# MAGIC | 予測の実行 | 手でスクリプトを実行 | ⭐ ジョブが自動実行 |
# MAGIC | モデルの管理 | ファイル名と記憶に頼る | ⭐ バージョンとエイリアスで明確 |
# MAGIC | 良くなったかの確認 | やっていない | ⭐ **毎回「去年と同じ」と比べる** |
# MAGIC | 本番の切り替え | 人が判断して差し替え | ⭐ 基準を満たしたら自動で昇格 |
# MAGIC | 結果の共有 | HTML をメールに添付 | ⭐ ダッシュボードが自動更新・自動配信 |
# MAGIC | 異常の検知 | 気づいたら | ⭐ 失敗したら通知が飛ぶ |
# MAGIC
# MAGIC ⭐⭐ **精度が上がったのではありません。**
# MAGIC **同じことを、手を動かさずに、毎月確実に回せるようになった**のが今日の成果です。
# MAGIC そして空いた時間を、モデルの改良そのものに使えるようになります。
# MAGIC
# MAGIC > ⭐ **見本ジョブ `[handson] 見本 需要予測の月次更新` との違い**
# MAGIC >
# MAGIC > 見本は CSV の投入まで含めた **4 タスク**になっています。
# MAGIC > 実際の運用では「基幹システムから CSV を出す」処理がここに入り、
# MAGIC > ⭐ **人が触る場所がゼロ**になります。

# COMMAND ----------

# MAGIC %md
# MAGIC ## ✅ ここまでできたら
# MAGIC
# MAGIC 次は **`08_mmf_genie_code`** に進みます。
# MAGIC
# MAGIC ⚠️ 今日作ったモデルは **全品目に 1 つ**でした。
# MAGIC でも `00` で見たとおり、**品目ごとに需要の性質はまったく違います**。
# MAGIC ⭐ 次は「**品目ごとに最適な手法を選ぶ**」を、自然言語の指示だけでやってみます。
