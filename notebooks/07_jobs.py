# Databricks notebook source
# MAGIC %md
# MAGIC # 07 — 自動実行にする（Lakeflow Jobs）
# MAGIC
# MAGIC > ⏱ **目安 9 分**
# MAGIC
# MAGIC ⭐ ここまで全部、**手で 1 つずつ実行してきました**。
# MAGIC ⚠️ このままだと来月も同じ手作業が必要です。今日の話が「便利な道具の紹介」で
# MAGIC 終わってしまうのはここです。
# MAGIC
# MAGIC ## ⭐ 目指す形
# MAGIC
# MAGIC ```
# MAGIC   ① 新しい CSV を取り込む      （Volume に置く）
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
# MAGIC ⭐ ①〜④ をつなげて 1 本のジョブにします。
# MAGIC **人がやることは「CSV を置く」だけ**になります。
# MAGIC
# MAGIC > ⭐ **動くお手本があります。**
# MAGIC > `[handson] 見本 需要予測の月次更新` というジョブが既に作られていて、
# MAGIC > 上の ①〜④ がそのまま 4 つのタスクになっています。
# MAGIC > **迷ったら開いて中を見てください**（答え合わせに使えます）。
# MAGIC
# MAGIC ## このパートでやること
# MAGIC
# MAGIC | | 内容 | 目安 |
# MAGIC |---|---|---|
# MAGIC | 1 | ⭐ **画面からジョブを作る**（タスクを 3 つ繋げる） | 6 分 |
# MAGIC | 2 | 実行のきっかけ（トリガー）を眺める | 2 分 |
# MAGIC | 3 | 失敗したときの通知を設定する | 1 分 |

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
# MAGIC 2. ジョブ名を付ける — 例: `需要予測の月次更新_山田太郎`
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
# MAGIC 6. 右上 **「今すぐ実行」** で通しで動くか確認する
# MAGIC
# MAGIC > ⭐ **タスク 3 が「評価の更新」も担っています。**
# MAGIC > `05` は予測を作り直したあと、**予測と実績を突き合わせた結果**を
# MAGIC > `fct_forecast_accuracy_all` に書き出します。
# MAGIC > ⚠️ ここが無いと「精度は誰かが手でクエリを書いたときにしか分からない」状態になり、
# MAGIC > 「気づいたら 3 か月ずれ続けていた」が起きます。
# MAGIC
# MAGIC > ⭐ **タスクの依存関係が絵で見える**のがポイントです。
# MAGIC > 「パイプラインが終わってから再学習する」という順序が、コードを読まなくても分かります。
# MAGIC
# MAGIC > ⚠️ 実行に数分かかります。待っている間に **2 と 3 を読んでおいてください。**

# COMMAND ----------

print("ジョブの設定でコピーして使う値")
print("=" * 78)
print(f"  タスク 1（パイプライン）: [handson] {USER_SUFFIX} のメダリオンパイプライン")
print()

import os

_nb_path = dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
NB_DIR = os.path.dirname(_nb_path)
print(f"  タスク 2（ノートブック）: {NB_DIR}/06_retrain")
print(f"  タスク 3（ノートブック）: {NB_DIR}/05_batch_inference")
print("=" * 78)

from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
displayHTML(f'<a href="{w.config.host}/jobs" target="_blank">▶ ジョブの画面を開く</a>')

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. 実行のきっかけ（トリガー）を眺める（2 分）
# MAGIC
# MAGIC ⭐ ジョブ画面の右側 **「スケジュールとトリガー」** → **「トリガーを追加」** を開いて、
# MAGIC **どんな種類があるかだけ見てください**（設定は不要です）。
# MAGIC
# MAGIC | 種類 | いつ動くか | 今回の使いどころ |
# MAGIC |---|---|---|
# MAGIC | **スケジュール** | 決めた日時 | ⭐ 「毎月 1 日の朝 6 時に回す」 |
# MAGIC | ⭐ **ファイル到着** | 指定の場所に**新しいファイルが来たとき** | ⭐ 「CSV が置かれたら動く」 |
# MAGIC | テーブル更新 | 上流のテーブルが更新されたとき | 他チームのデータに追随する |
# MAGIC | 連続 | 常に動かし続ける | リアルタイム処理 |
# MAGIC
# MAGIC ### ⚠️ ファイル到着トリガーの落とし穴
# MAGIC
# MAGIC ⭐ 「CSV を置いたら自動で全部動く」は理想的に聞こえますが、⚠️ 癖があります。
# MAGIC
# MAGIC | ⚠️ 注意点 | 内容 |
# MAGIC |---|---|
# MAGIC | ⚠️⚠️ **同名ファイルの上書きでは発火しない** | 「毎月同じ `demand.csv` を上書き」では動きません。**新しいファイル名**が必要 |
# MAGIC | 検知の間隔 | 約 1 分ごとの確認。即座ではありません |
# MAGIC | ファイル数の上限 | 監視対象が 1 万ファイルを超えると使えません（古いものは移動する運用が必要） |
# MAGIC
# MAGIC ⭐ **だからこのハンズオンでは CSV を月ごとに別ファイル名にしています。**
# MAGIC （`shipments_2020_2026_07.csv` と `shipments_2026_08.csv`）
# MAGIC
# MAGIC > ⭐ **今日は設定だけ眺めて、実際の実行は「今すぐ実行」で行いました。**
# MAGIC > サーバーレスのパイプラインは初回起動に 4〜6 分かかるため、
# MAGIC > トリガー待ちにすると当日の時間が読めなくなるためです。

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. 失敗したときの通知を設定する（1 分）
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

# COMMAND ----------

# MAGIC %md
# MAGIC ## ✅ ここまでできたら
# MAGIC
# MAGIC 次は **`08_mmf_genie_code`** に進みます。
# MAGIC
# MAGIC ⚠️ 今日作ったモデルは **全品目に 1 つ**でした。
# MAGIC でも `00` で見たとおり、**品目ごとに需要の性質はまったく違います**。
# MAGIC ⭐ 次は「**品目ごとに最適な手法を選ぶ**」を、自然言語の指示だけでやってみます。
