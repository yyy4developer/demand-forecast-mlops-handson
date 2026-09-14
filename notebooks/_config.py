# Databricks notebook source
# MAGIC %md
# MAGIC # _config — 共通設定
# MAGIC
# MAGIC 各ノートブックの冒頭で `%run ./_config` して読み込みます。
# MAGIC
# MAGIC ## 🧑‍🤝‍🧑 あなた専用の作業場所が自動で用意されます
# MAGIC
# MAGIC ハンズオンでは複数の参加者が同じワークスペースで同時に作業します。
# MAGIC お互いの作業がぶつからないよう、**スキーマは参加者ごとに自動で分かれます**。
# MAGIC
# MAGIC - スキーマ名は**ログインユーザー名から自動生成**されます
# MAGIC   （例: `taro.yamada@example.com` → `fc_ws_taro_yamada`）
# MAGIC - 手で名前を決める必要はありません。**このファイルは編集せずそのまま実行**してください
# MAGIC - 自分のスキーマ名は各ノートブック冒頭の出力で確認できます
# MAGIC
# MAGIC ## 📦 スキーマは 2 つだけ
# MAGIC
# MAGIC | スキーマ | 中身 | あなたの権限 |
# MAGIC |---|---|---|
# MAGIC | `fc_sample` | ⭐ **検証済みの見本すべて**（CSV / テーブル / メトリクスビュー / モデル / ダッシュボード） | 読み取りのみ |
# MAGIC | ⭐ `fc_ws_<あなた>` | ⭐ **あなたが同じものを作る場所**（Volume も含む） | 自由に読み書き |
# MAGIC
# MAGIC > ⭐⭐ **今日のゴールは「見本を自分のスキーマに再現すること」です。**
# MAGIC >
# MAGIC > 見本 (`fc_sample`) には、これから作るものが**全部すでに入っています**。
# MAGIC > 困ったら中を見て、同じものを自分のスキーマに作ってください。
# MAGIC
# MAGIC > ⭐ **なぜ一人ずつ全部作るのか**
# MAGIC >
# MAGIC > 本来のデータ基盤なら、bronze → silver → gold は**共通のスキーマに 1 セット**作り、
# MAGIC > 全員がそれを参照します。今回は「**取り込みから自分の手で体験する**」ことが目的なので、
# MAGIC > 一人ひとりが自分のスキーマに一式を作ります。
# MAGIC > ⚠️ 本番でこの形にする必要はありません。

# COMMAND ----------

# ★★★ 管理者が環境に合わせて設定する箇所 ★★★
# ハンズオンで使うカタログ名
DEFAULT_CATALOG = "demand_forecast_handson"

# 検証済みの見本が入っているスキーマ
SAMPLE_SCHEMA = "fc_sample"
# CSV を置く Volume 名（見本にも、あなたのスキーマにも同じ名前で作ります）
LANDING_VOLUME = "landing"

# 参加者ごとのスキーマ名のプレフィックス
SCHEMA_PREFIX = "fc_ws"
# False にすると全員が 1 つのスキーマを共有する（一人でデモするとき用）
SCHEMA_PER_USER = True

# COMMAND ----------

import re


def _user_suffix() -> str:
    """ログインユーザー名からスキーマ名に使える識別子を作る。

    例: taro.yamada@example.com -> taro_yamada
    """
    try:
        email = spark.sql("SELECT current_user()").collect()[0][0]
    except Exception:
        email = "shared"
    local = (email or "shared").split("@")[0]
    # 英数字以外は _ に寄せ、先頭が数字なら u を付ける（識別子として安全な形にする）
    ident = re.sub(r"[^0-9a-zA-Z]+", "_", local).strip("_").lower()
    if not ident:
        ident = "shared"
    if ident[0].isdigit():
        ident = f"u{ident}"
    return ident[:40]


USER_SUFFIX = _user_suffix()
DEFAULT_SCHEMA = f"{SCHEMA_PREFIX}_{USER_SUFFIX}" if SCHEMA_PER_USER else SCHEMA_PREFIX

# COMMAND ----------

# ジョブから実行された場合は widget の値を優先し、
# ノートブックを直接開いた場合は上の既定値を使う
try:
    dbutils.widgets.text("catalog", DEFAULT_CATALOG, "カタログ")
    dbutils.widgets.text("schema", DEFAULT_SCHEMA, "あなたのスキーマ")
    catalog = dbutils.widgets.get("catalog") or DEFAULT_CATALOG
    schema = dbutils.widgets.get("schema") or DEFAULT_SCHEMA
except Exception:
    catalog, schema = DEFAULT_CATALOG, DEFAULT_SCHEMA

# よく使うパスをまとめておく
MY = f"{catalog}.{schema}"
SAMPLE = f"{catalog}.{SAMPLE_SCHEMA}"
# 見本の CSV（読み取り専用）
SAMPLE_LANDING = f"/Volumes/{catalog}/{SAMPLE_SCHEMA}/{LANDING_VOLUME}"
# ⭐ あなた専用の CSV 置き場（自分で読み書きできます）
LANDING_PATH = f"/Volumes/{catalog}/{schema}/{LANDING_VOLUME}"

# ⭐ 自分のスキーマと Volume を作る（何度実行しても安全）
spark.sql(f"USE CATALOG {catalog}")
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {MY}")
spark.sql(f"USE SCHEMA {schema}")
spark.sql(f"CREATE VOLUME IF NOT EXISTS {MY}.{LANDING_VOLUME} "
          f"COMMENT 'あなたの CSV 置き場。見本からコピーしたものと、自分で持ち込んだものを置きます。'")

# ⭐ SQL ウェアハウスの ID を自動で見つける。
#    一部の機能（ai_forecast など）は SQL ウェアハウス上でしか動かないため、
#    ノートブックからそこへクエリを投げるのに使います。
def _find_warehouse_id() -> str:
    try:
        from databricks.sdk import WorkspaceClient

        listed = WorkspaceClient().api_client.do("GET", "/api/2.0/sql/warehouses") or {}
        whs = listed.get("warehouses") or []
        # Pro か Serverless を優先（Classic では動かない機能があるため）
        preferred = [
            x for x in whs
            if x.get("enable_serverless_compute") or x.get("warehouse_type") == "PRO"
        ]
        pick = (preferred or whs)
        return pick[0]["id"] if pick else ""
    except Exception:
        return ""


WAREHOUSE_ID = _find_warehouse_id()

print("=" * 74)
print(f"  ⭐ あなたの作業スキーマ : {MY}")
print(f"     あなたの CSV 置き場 : {LANDING_PATH}")
print(f"  ⭐ 見本（読み取り専用） : {SAMPLE}")
print(f"     見本の CSV          : {SAMPLE_LANDING}")
print(f"     SQL ウェアハウス    : {WAREHOUSE_ID or '(見つかりませんでした)'}")
print("=" * 74)
print("※ 以降のノートブックは、あなたの作業スキーマに対して実行されます")
print("※ 詰まったら見本スキーマの中身を見てください。同じものが入っています")
