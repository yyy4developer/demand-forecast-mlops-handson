# Databricks notebook source
# MAGIC %md
# MAGIC # 管理者向け — 環境を準備する
# MAGIC
# MAGIC > 🧑‍💼 **これは講師・管理者が事前に実行するノートブックです。** 参加者は実行しません。
# MAGIC >
# MAGIC > 🔑 **必要な権限**: メタストア管理者、またはカタログを作成できる権限
# MAGIC
# MAGIC ## ここでやること
# MAGIC
# MAGIC | # | 内容 | なぜここでやるのか |
# MAGIC |---|---|---|
# MAGIC | 1 | カタログを作る | ⚠️ API 経由の作成が失敗する環境があるため SQL で作ります |
# MAGIC | 2 | ⭐ **SQL ウェアハウスを用意する** | ⭐ **無ければ作ります。** ダッシュボード・Genie Agent・`ai_forecast` がこれを使います |
# MAGIC | 3 | 参加者に権限を付ける | ⭐ **参加者が持つ権限をここで一覧にして固定します** |
# MAGIC | 4 | 付いた権限を確認する | 当日「権限がなくて動かない」を防ぎます |
# MAGIC
# MAGIC ⚠️⚠️ **このノートブックは bundle をデプロイする「前」に実行してください。**
# MAGIC カタログが無いとデプロイが失敗します。
# MAGIC
# MAGIC ## ⚠️ カタログを SQL で作る理由
# MAGIC
# MAGIC Default Storage 構成のメタストアでは、API 経由の `CREATE CATALOG` が
# MAGIC 「storage root がない」と言って失敗します。
# MAGIC SQL 経由なら保存先が自動で決まるため通ります。
# MAGIC ⭐ だからカタログ作成だけは Asset Bundle に含めず、このノートブックに置いています。

# COMMAND ----------

dbutils.widgets.text("catalog", "demand_forecast_handson", "カタログ")
dbutils.widgets.text("sample_schema", "fc_sample", "見本用スキーマ")
dbutils.widgets.text("volume", "landing", "Volume 名")
dbutils.widgets.text("participant_group", "handson-participants", "参加者グループ")

catalog = dbutils.widgets.get("catalog")
sample_schema = dbutils.widgets.get("sample_schema")
volume = dbutils.widgets.get("volume")
group = dbutils.widgets.get("participant_group")

print(f"カタログ       : {catalog}")
print(f"参加者グループ : {group}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. カタログを作る
# MAGIC
# MAGIC ⭐ この後 `databricks bundle deploy` を実行すると、スキーマ・Volume・
# MAGIC パイプライン・ジョブが作られます。**順番を逆にすると失敗します。**

# COMMAND ----------

spark.sql(f"CREATE CATALOG IF NOT EXISTS {catalog} COMMENT '需要予測 x MLOps ハンズオン用'")
print(f"✅ カタログ {catalog} を用意しました")
print("\n⭐ 次にターミナルで bundle をデプロイしてください:")
print("   databricks bundle deploy -t dev -p <profile>")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. ⭐ SQL ウェアハウスを用意する
# MAGIC
# MAGIC ⭐ ダッシュボード / Genie Agent / `ai_forecast` はすべて SQL ウェアハウス上で動きます。
# MAGIC
# MAGIC ⚠️ **`ai_forecast` は Pro または Serverless でしか動きません。** Classic では
# MAGIC 「この環境では無効です」と言われます。だから既存を探すときも種別を確認します。
# MAGIC
# MAGIC ⭐ 使えるものが無ければ、**サーバーレスのウェアハウスを 1 台作ります**。
# MAGIC 参加者全員で共有します（ノートブック実行は軽いため 1 台で足ります）。

# COMMAND ----------

from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
api = w.api_client

listed = api.do("GET", "/api/2.0/sql/warehouses") or {}
warehouses = listed.get("warehouses") or []

# ⭐ Pro か Serverless を優先（Classic では ai_forecast が動きません）
usable = [
    x for x in warehouses
    if x.get("enable_serverless_compute") or x.get("warehouse_type") == "PRO"
]

print(f"ワークスペースのウェアハウス: {len(warehouses)} 台（うち使えるもの {len(usable)} 台）")
for x in warehouses:
    kind = "Serverless" if x.get("enable_serverless_compute") else (x.get("warehouse_type") or "?")
    mark = "⭐" if x in usable else "⚠️"
    print(f"  {mark} {x.get('name'):<32} {kind:<12} {x.get('cluster_size'):<10} {x.get('state')}")

# COMMAND ----------

WAREHOUSE_NAME = "handson-serverless"

if usable:
    wh = usable[0]
    print(f"⭐ 既にあるウェアハウスを使います: {wh.get('name')}")
else:
    print(f"使えるウェアハウスが無いので作成します: {WAREHOUSE_NAME}")
    wh = api.do(
        "POST",
        "/api/2.0/sql/warehouses",
        body={
            "name": WAREHOUSE_NAME,
            # ⚠️ ai_forecast の要件を満たすため PRO + サーバーレスにします
            "warehouse_type": "PRO",
            "enable_serverless_compute": True,
            # 参加者 10 名程度なら X-Small で足ります
            "cluster_size": "X-Small",
            "min_num_clusters": 1,
            "max_num_clusters": 2,
            # ⭐ 30 分使われなければ自動停止（コストを抑える）
            "auto_stop_mins": 30,
        },
    )
    print(f"✅ 作成しました: {wh.get('name')}")

WAREHOUSE_ID = wh["id"]

print()
print("=" * 66)
print(f"  ⭐ SQL ウェアハウス ID : {WAREHOUSE_ID}")
print(f"     名前               : {wh.get('name')}")
print("=" * 66)
print("※ この ID は覚えなくて構いません。")
print("   ノートブックは実行時に自動でウェアハウスを見つけます。")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. ⭐ 参加者に権限を付ける
# MAGIC
# MAGIC ⭐⭐ **参加者が持つ権限はこれだけです。** ここに書かれていない操作は当日できません。
# MAGIC
# MAGIC | 権限 | なぜ必要か |
# MAGIC |---|---|
# MAGIC | `USE CATALOG` | カタログを開くため |
# MAGIC | ⭐ `CREATE SCHEMA` | **自分専用のスキーマを自分で作るため** |
# MAGIC | `USE SCHEMA` / `SELECT`（見本） | 見本を読み、自分のスキーマに再現するため |
# MAGIC | ⭐ `READ VOLUME`（見本） | **見本の CSV を自分の Volume にコピーするため** |
# MAGIC
# MAGIC ⭐ 参加者は**自分のスキーマと Volume を自分で作る**ので、
# MAGIC そこへの書き込み権限は自動的に持ちます（作成者が所有者になります）。
# MAGIC
# MAGIC ⭐ **SQL ウェアハウスの `CAN USE` も、このノートブックが付けます**（下のセル）。
# MAGIC
# MAGIC ⚠️ **これ以外に UI 側で必要なもの**（このノートブックでは付けられません）:
# MAGIC
# MAGIC - サーバーレスコンピュートが使えること
# MAGIC - ⚠️ **パイプラインを作成できること**（`00_setup_my_pipeline` で自分のパイプラインを作ります）
# MAGIC - 見本ダッシュボード / 見本 Genie Agent の `CAN VIEW`

# COMMAND ----------

GRANTS = [
    f"GRANT USE CATALOG ON CATALOG {catalog} TO `{group}`",
    # ⭐ 参加者が自分のスキーマ fc_ws_<user> と Volume を作れるようにする
    f"GRANT CREATE SCHEMA ON CATALOG {catalog} TO `{group}`",
    # 見本スキーマ（読み取りのみ）
    f"GRANT USE SCHEMA ON SCHEMA {catalog}.{sample_schema} TO `{group}`",
    f"GRANT SELECT ON SCHEMA {catalog}.{sample_schema} TO `{group}`",
    # ⭐ 見本の CSV を自分の Volume にコピーするため（読み取りだけで足ります）
    f"GRANT READ VOLUME ON VOLUME {catalog}.{sample_schema}.{volume} TO `{group}`",
]

ok, failed = 0, []
for g in GRANTS:
    try:
        spark.sql(g)
        ok += 1
        print(f"  ✅ {g}")
    except Exception as e:  # noqa: BLE001
        failed.append((g, str(e).splitlines()[0][:160]))
        print(f"  ❌ {g}")

print(f"\n{ok}/{len(GRANTS)} 件の権限を付けました")

# ⭐ SQL ウェアハウスの CAN_USE も付ける
try:
    api.do(
        "PATCH",
        f"/api/2.0/permissions/warehouses/{WAREHOUSE_ID}",
        body={"access_control_list": [{"group_name": group, "permission_level": "CAN_USE"}]},
    )
    print(f"  ✅ SQL ウェアハウス {WAREHOUSE_ID} に CAN_USE を付与")
except Exception as e:  # noqa: BLE001
    print(f"  ❌ SQL ウェアハウスの権限付与に失敗: {str(e).splitlines()[0][:140]}")
if failed:
    print("\n⚠️ 失敗したもの（グループ名が存在するか確認してください）:")
    for g, msg in failed:
        print(f"  {g}\n    → {msg}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. 付いた権限を確認する

# COMMAND ----------

for target, kind in [
    (f"CATALOG {catalog}", "カタログ"),
    (f"SCHEMA {catalog}.{sample_schema}", "見本スキーマ"),
    (f"VOLUME {catalog}.{sample_schema}.{volume}", "見本の Volume"),
]:
    print(f"\n[{kind}] {target}")
    try:
        rows = spark.sql(f"SHOW GRANTS ON {target}").collect()
        for r in rows:
            if group in str(r["Principal"]):
                print(f"  {r['ActionType']}")
    except Exception as e:  # noqa: BLE001
        print(f"  ⚠️ 確認できませんでした: {type(e).__name__}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## ✅ デプロイに必要なものは揃いました
# MAGIC
# MAGIC ⭐ **Databricks CLI は要りません。** 下のセルで「何が揃ったか」を確認して、
# MAGIC そのまま画面からデプロイしてください。

# COMMAND ----------

print("=" * 74)
print("  デプロイの準備状況")
print("=" * 74)

checks = []

# カタログ
try:
    spark.sql(f"DESCRIBE CATALOG {catalog}")
    checks.append(("カタログ", catalog, True))
except Exception:  # noqa: BLE001
    checks.append(("カタログ", f"{catalog}（作成に失敗）", False))

# SQL ウェアハウス
checks.append(("SQL ウェアハウス", f"{wh.get('name')}  (id: {WAREHOUSE_ID})", True))

# 参加者グループ
try:
    found = api.do("GET", "/api/2.0/preview/scim/v2/Groups",
                   query={"filter": f'displayName eq "{group}"'}) or {}
    exists = bool(found.get("Resources"))
    checks.append(("参加者グループ", group if exists else f"{group}（見つかりません）", exists))
except Exception:  # noqa: BLE001
    checks.append(("参加者グループ", f"{group}（確認できませんでした）", False))

# サーバーレスが使えるか（このノートブックがサーバーレスで動いていれば OK）
checks.append(("サーバーレスコンピュート", "このノートブックが動いているので利用可", True))

for label, value, ok in checks:
    print(f"  {'✅' if ok else '⚠️'} {label:<24} {value}")

print()
if all(ok for _, _, ok in checks):
    print("  ⭐ すべて揃っています。デプロイに進んでください。")
else:
    print("  ⚠️ ⚠️ が付いた項目を先に解消してください。")

print()
print("=" * 74)
print("  ⭐ デプロイのときに渡す値: ありません")
print("=" * 74)
print("  この bundle は変数を 1 つも必要としません。")
print("  SQL ウェアハウスの ID もノートブックが実行時に自分で見つけます。")
print("  → 画面の「デプロイ」を押すだけで配置できます。")

# COMMAND ----------

# MAGIC %md
# MAGIC ## ✅ 次の手順
# MAGIC
# MAGIC ⭐ **Databricks CLI は要りません。** 画面だけで進められます。
# MAGIC
# MAGIC 1. ⭐ **この Git フォルダの画面から bundle をデプロイする**
# MAGIC    （`databricks.yml` がある場所を開くと「デプロイ」が出ます）
# MAGIC    ⭐ 渡す変数はありません。そのままデプロイできます
# MAGIC 2. ジョブ `[handson] 01 サンプルデータを Volume に投入` を **`load_set = A`** で実行
# MAGIC 3. パイプライン `[handson] 見本 メダリオンパイプライン` を実行（見本の gold ができます）
# MAGIC 4. `notebooks/_uc_metadata` を **`schema = fc_sample`** で実行
# MAGIC 5. `notebooks/admin/01_deploy_dashboard` を実行（見本ダッシュボード）
# MAGIC 6. `src/setup/run_mmf_reference` を実行（MMF の参考結果）
# MAGIC 7. ジョブ `[handson] 見本 初回のモデル作成` を実行
# MAGIC 8. 見本 Genie Agent を画面から作る（`genie/README.md` 参照）
# MAGIC 9. ⭐ **参加者 1 名で `HANDSON.md` を通しリハーサル**
# MAGIC
# MAGIC ⚠️ **セット B の CSV は当日まで投入しないでください。**
# MAGIC 「新しいデータが届いてテーブルが更新される」を見せるのが当日の山場です。
