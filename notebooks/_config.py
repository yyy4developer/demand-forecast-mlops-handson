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

# MAGIC %md
# MAGIC ## ⭐ 設定は `databricks.yml` の 1 箇所だけ
# MAGIC
# MAGIC ⭐ カタログ名・スキーマ名・Volume 名は、次の順に探して**最初に見つかったもの**を使います。
# MAGIC ⚠️ **参加者がこのファイルを編集する必要はありません。**
# MAGIC
# MAGIC | 優先 | 読み込み元 | 誰が書くか |
# MAGIC |---|---|---|
# MAGIC | ⭐ 1 | `.databricks/bundle/dev/variable-overrides.json` | ⭐ **`admin/00_prepare_environment`** が書き出す |
# MAGIC | 2 | `databricks.yml` の `variables` の `default` | リポジトリの既定値 |
# MAGIC | 3 | このファイル内の `_FALLBACK` | 上の 2 つが読めなかったとき |
# MAGIC
# MAGIC ⚠️⚠️ **1 を見ないと事故ります。** 管理者が既定と違うカタログ名を使った場合、
# MAGIC `databricks.yml` の既定値のままだと `NO_SUCH_CATALOG_EXCEPTION` になります。
# MAGIC
# MAGIC ⭐ どこから読んだかは下のセルが表示します。⚠️ **想定と違ったらそこを直してください。**

# COMMAND ----------

import os
import re

# ⭐ `databricks.yml` から値を読む（このノートブックの 1 階層上にあります）
_nb = dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
_root = os.path.normpath(os.path.join(os.path.dirname(_nb), ".."))
_prefix = "" if _root.startswith("/Workspace") else "/Workspace"
BUNDLE_YAML = f"{_prefix}{_root}/databricks.yml"

# 読めなかったときに使う既定値
_FALLBACK = {"catalog": "demand_forecast_handson", "sample_schema": "fc_sample", "landing_volume": "landing"}


def _read_bundle_variables(path: str) -> dict:
    """`databricks.yml` の variables から default 値を読む。

    ⚠️ PyYAML が入っていない環境でも動くよう、必要な部分だけを行単位で拾います。
    """
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        return {}

    found: dict[str, str] = {}
    in_variables = False
    current = None
    for line in lines:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        # インデントの無い行で variables ブロックの開始・終了を判断する
        if not line.startswith(" "):
            in_variables = line.rstrip().startswith("variables:")
            current = None
            continue
        if not in_variables:
            continue
        # "  <name>:" が変数名、"    default: <value>" がその既定値
        name = line[2:].rstrip()
        if line.startswith("  ") and not line.startswith("   ") and name.endswith(":"):
            current = name[:-1].strip()
            continue
        stripped = line.strip()
        if current and stripped.startswith("default:"):
            found[current] = stripped[len("default:"):].strip().strip('"').strip("'")
            current = None
    return found


# ⭐⭐ 管理者が書き出した上書きファイル。`databricks.yml` の既定値より優先します。
#
# ⚠️ これを見ないと、管理者が既定と違うカタログ名を使ったときに
#    NO_SUCH_CATALOG_EXCEPTION になります（deploy は上書きを読むのに、
#    ノートブックだけ既定値を読んでいる状態）。
BUNDLE_TARGET = "dev"
OVERRIDE_JSON = f"{_prefix}{_root}/.databricks/bundle/{BUNDLE_TARGET}/variable-overrides.json"


def _read_overrides(path: str) -> dict:
    """管理者が書き出した変数の上書きファイルを読む（無ければ空）。"""
    import json

    try:
        with open(path, encoding="utf-8") as f:
            loaded = json.load(f)
    except (OSError, ValueError):
        return {}
    # 値が空文字のものは「未設定」として扱う
    return {k: v for k, v in loaded.items() if isinstance(v, str) and v}


_yaml_vars = _read_bundle_variables(BUNDLE_YAML)
_override_vars = _read_overrides(OVERRIDE_JSON)

# ⭐ 上書きファイルが勝つ
_vars = {**_yaml_vars, **_override_vars}

if _override_vars:
    print(f"⭐ 設定の読み込み元: {OVERRIDE_JSON}")
    print(f"   （管理者が書き出した上書き: {', '.join(sorted(_override_vars))}）")
elif _yaml_vars:
    print(f"設定の読み込み元: {BUNDLE_YAML}")
else:
    print(f"⚠️ {BUNDLE_YAML} が読めなかったので既定値を使います")

# ハンズオンで使うカタログ名
DEFAULT_CATALOG = _vars.get("catalog") or _FALLBACK["catalog"]
# 検証済みの見本が入っているスキーマ
SAMPLE_SCHEMA = _vars.get("sample_schema") or _FALLBACK["sample_schema"]
# CSV を置く Volume 名（見本にも、あなたのスキーマにも同じ名前で作ります）
LANDING_VOLUME = _vars.get("landing_volume") or _FALLBACK["landing_volume"]

# 参加者ごとのスキーマ名のプレフィックス
SCHEMA_PREFIX = "fc_ws"
# False にすると全員が 1 つのスキーマを共有する（一人でデモするとき用）
SCHEMA_PER_USER = True

# COMMAND ----------


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

# ⭐⭐ 指定されたカタログが本当にあるか確かめ、無ければ探す
#
# ⚠️ 設定ファイルの値と実際のカタログ名がずれると、この先すべてが
#    NO_SUCH_CATALOG_EXCEPTION で落ちます。よくある原因は
#    「管理者が既定と違うカタログ名を使ったが、参加者側の Git フォルダには
#    上書きファイルが無い」というものです。
#
# ⭐ そこで、見つからなければ**見本スキーマを持つカタログを探して**使います。
#    参加者に見えるカタログはハンズオン用の 1 つだけなので、ほぼ一意に決まります。
def _resolve_catalog(name: str) -> str:
    try:
        spark.sql(f"DESCRIBE CATALOG {name}")
        return name
    except Exception:  # noqa: BLE001
        pass

    print(f"⚠️ カタログ {name} が見つかりませんでした。{SAMPLE_SCHEMA} を持つカタログを探します。")
    try:
        names = [r[0] for r in spark.sql("SHOW CATALOGS").collect()]
    except Exception:  # noqa: BLE001
        names = []

    hits = []
    for c in names:
        if c in ("system", "samples", "hive_metastore"):
            continue
        try:
            found = spark.sql(f"SHOW SCHEMAS IN {c} LIKE '{SAMPLE_SCHEMA}'").collect()
        except Exception:  # noqa: BLE001
            continue
        if found:
            hits.append(c)

    if len(hits) == 1:
        print(f"⭐ カタログ {hits[0]} を使います（{SAMPLE_SCHEMA} が見つかりました）。")
        print("⚠️ 設定ファイルの値と違っています。講師に伝えてください。")
        return hits[0]

    raise RuntimeError(
        f"カタログ {name} が見つかりません。"
        + (f" 候補が複数あります: {hits}。" if len(hits) > 1 else "")
        + " 講師に正しいカタログ名を確認し、ノートブック上部の widget『カタログ』に入れてください。"
    )


catalog = _resolve_catalog(catalog)

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
