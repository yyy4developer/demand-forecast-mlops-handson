# Databricks notebook source
# MAGIC %md
# MAGIC # 見本の Genie Agent を作る（管理者向け）
# MAGIC
# MAGIC > 🧑‍💼 **これは管理者が事前に実行するノートブックです**。参加者は実行しません。
# MAGIC
# MAGIC ## ⚠️ なぜ DAB ではなくノートブックなのか
# MAGIC
# MAGIC ⭐ Genie Agent は **DAB のリソースとしても書けます**（`resources.genie_spaces`）。
# MAGIC 書き方は `docs/reference/genie_space_in_dab.yml` に残してあります。
# MAGIC
# MAGIC ⚠️⚠️ **ただし deploy 1 回では作れません。**
# MAGIC 作成 API は**参照テーブルが実在するかを検証する**のに、
# MAGIC 参照先のメトリクスビューは
# MAGIC
# MAGIC ```
# MAGIC deploy → CSV 投入 → パイプライン実行 → gold → メトリクスビュー
# MAGIC ```
# MAGIC
# MAGIC という順でできるため、deploy の時点では存在しません。
# MAGIC ⚠️ 1 回目の deploy は必ず失敗し、2 回目の deploy が必要になります。
# MAGIC
# MAGIC ⭐ そこで **メトリクスビューを作った直後にこのノートブックで作る**形にしました。
# MAGIC これで **deploy は 1 回**で済みます。
# MAGIC
# MAGIC ## ⭐ 冪等です
# MAGIC
# MAGIC 同じタイトルの Genie Agent が既にあれば**作り直さずに更新**します。
# MAGIC 何度実行しても増えません。

# COMMAND ----------

dbutils.widgets.text("catalog", "demand_forecast_handson", "カタログ")
dbutils.widgets.text("schema", "fc_sample", "見本スキーマ")
dbutils.widgets.text("warehouse_id", "", "SQL ウェアハウス ID")
dbutils.widgets.text("title", "[handson] 見本 需要分析エージェント", "タイトル")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
warehouse_id = dbutils.widgets.get("warehouse_id")
title = dbutils.widgets.get("title")

DESCRIPTION = (
    "アクアテック工業の需要と予測精度を自然言語で分析するための見本。"
    "参加者は同じものを自分のスキーマで作ります。"
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. 前提の確認
# MAGIC
# MAGIC ⚠️ **メトリクスビューが無いと作成に失敗します**（API がテーブルの実在を検証します）。
# MAGIC 先に `notebooks/_uc_metadata` を `schema = fc_sample` で実行してください。

# COMMAND ----------

TABLES = [f"{catalog}.{schema}.mv_demand", f"{catalog}.{schema}.mv_forecast_accuracy"]

missing = []
for t in TABLES:
    try:
        spark.sql(f"SELECT 1 FROM {t} LIMIT 0")
        print(f"  ✅ {t}")
    except Exception as e:  # noqa: BLE001
        missing.append(t)
        print(f"  ❌ {t}  ({type(e).__name__})")

if missing:
    raise RuntimeError(
        "メトリクスビューがありません: "
        + ", ".join(missing)
        + " → 先に notebooks/_uc_metadata を schema="
        + schema
        + " で実行してください。"
    )

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. ウェアハウス ID を決める
# MAGIC
# MAGIC ⭐ 渡されていなければ、使える SQL ウェアハウス（Pro / サーバーレス）を自動で選びます。

# COMMAND ----------

from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
api = w.api_client

if not warehouse_id:
    _whs = (api.do("GET", "/api/2.0/sql/warehouses") or {}).get("warehouses") or []
    _pref = [
        x for x in _whs
        if x.get("enable_serverless_compute") or x.get("warehouse_type") == "PRO"
    ]
    if not (_pref or _whs):
        raise RuntimeError("使える SQL ウェアハウスが見つかりません。")
    warehouse_id = (_pref or _whs)[0]["id"]

print(f"使うウェアハウス: {warehouse_id}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Genie Agent を作る / 更新する
# MAGIC
# MAGIC ⭐ 渡しているのは**メトリクスビュー 2 本だけ**です。
# MAGIC ⚠️ 生のファクトテーブルを渡すと結合を誤りやすく、回答精度が落ちます。
# MAGIC
# MAGIC ### ⚠️ `serialized_space` の形式（公開ドキュメントに無いため実測で確認）
# MAGIC
# MAGIC | 要点 | 内容 |
# MAGIC |---|---|
# MAGIC | `version` | **1 か 2**。省略すると `ExportConverter supports versions 1 and 2, but got 0` |
# MAGIC | テーブル | `data_sources.tables[].identifier`（⚠️ `full_name` / `name` は不可） |
# MAGIC | 指示 | `instructions.text_instructions[].content`（⚠️ **文字列の配列**。単体文字列は不可） |
# MAGIC | ⚠️ 紛らわしいエラー | `Expected 'START_OBJECT' not 'VALUE_STRING'` は「そのフィールドは在るが、値がオブジェクト/配列であるべき」 |

# COMMAND ----------

SERIALIZED_SPACE = {
    "version": 2,
    "data_sources": {"tables": [{"identifier": t} for t in TABLES]},
    "instructions": {
        "text_instructions": [
            {
                "content": [
                    "回答は必ず日本語で返してください。",
                    "数量は整数、比率は小数第 1 位までに丸めてください。",
                    (
                        "予測精度について質問されたときは、誤差率と誤差個数を必ず両方示してください。"
                        "数量の少ない品目は誤差率が大きく出るため、率だけでは判断を誤ります。"
                    ),
                ]
            }
        ]
    },
}

body = {
    "title": title,
    "description": DESCRIPTION,
    "warehouse_id": warehouse_id,
    "serialized_space": SERIALIZED_SPACE,
}

# COMMAND ----------

# ⭐ 同じタイトルのものが既にあれば更新する（何度実行しても増えません）
existing = [
    s for s in ((api.do("GET", "/api/2.0/genie/spaces?page_size=100") or {}).get("spaces") or [])
    if s.get("title") == title
]

if existing:
    space_id = existing[0]["space_id"]
    api.do("PATCH", f"/api/2.0/genie/spaces/{space_id}", body=body)
    print(f"✅ 既存の Genie Agent を更新しました: {space_id}")
else:
    created = api.do("POST", "/api/2.0/genie/spaces", body=body)
    space_id = created.get("space_id")
    print(f"✅ Genie Agent を作成しました: {space_id}")

print(f"   タイトル: {title}")
for t in TABLES:
    print(f"   データ  : {t}")

displayHTML(
    f'<a href="{w.config.host}/genie/rooms/{space_id}" target="_blank">▶ Genie Agent を開く</a>'
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 次のステップ
# MAGIC
# MAGIC ⚠️ **参加者グループに `CAN VIEW` を付けてください**（Genie Agent の画面の「共有」から）。
# MAGIC ⚠️ Genie Agent は**開いた人の権限**でクエリを実行するため、
# MAGIC 参加者が見本スキーマを読めないと開いてもエラーになります
# MAGIC （⭐ スキーマの `USE SCHEMA` / `SELECT` は deploy が付けています）。
