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
# MAGIC | 2 | 参加者に権限を付ける | ⭐ **参加者が持つ権限をここで一覧にして固定します** |
# MAGIC | 3 | 付いた権限を確認する | 当日「権限がなくて動かない」を防ぎます |
# MAGIC
# MAGIC ## ⚠️ カタログを SQL で作る理由
# MAGIC
# MAGIC Default Storage 構成のメタストアでは、API 経由の `CREATE CATALOG` が
# MAGIC 「storage root がない」と言って失敗します。
# MAGIC SQL 経由なら保存先が自動で決まるため通ります。
# MAGIC ⭐ だからカタログ作成だけは Asset Bundle に含めず、このノートブックに置いています。

# COMMAND ----------

dbutils.widgets.text("catalog", "demand_forecast_handson", "カタログ")
dbutils.widgets.text("shared_schema", "fc_shared", "CSV 用スキーマ")
dbutils.widgets.text("sample_schema", "fc_sample", "見本用スキーマ")
dbutils.widgets.text("volume", "landing", "Volume 名")
dbutils.widgets.text("participant_group", "handson-participants", "参加者グループ")

catalog = dbutils.widgets.get("catalog")
shared_schema = dbutils.widgets.get("shared_schema")
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
# MAGIC ## 2. ⭐ 参加者に権限を付ける
# MAGIC
# MAGIC ⭐⭐ **参加者が持つ権限はこれだけです。** ここに書かれていない操作は当日できません。
# MAGIC
# MAGIC | 権限 | なぜ必要か |
# MAGIC |---|---|
# MAGIC | `USE CATALOG` | カタログを開くため |
# MAGIC | ⭐ `CREATE SCHEMA` | **自分専用のスキーマを自分で作るため** |
# MAGIC | `USE SCHEMA` / `SELECT`（CSV 用・見本用） | 共有データと見本を読むため |
# MAGIC | `READ VOLUME` | CSV を読むため |
# MAGIC | ⭐ `WRITE VOLUME` | **自由時間に自分のデータを置くため** |
# MAGIC
# MAGIC ⚠️ **これ以外に UI 側で必要なもの**（このノートブックでは付けられません）:
# MAGIC
# MAGIC - SQL ウェアハウスの `CAN USE`
# MAGIC - サーバーレスコンピュートが使えること
# MAGIC - ⚠️ **パイプラインを作成できること**（`00_setup_my_pipeline` で自分のパイプラインを作ります）
# MAGIC - 見本ダッシュボード / 見本 Genie Agent の `CAN VIEW`

# COMMAND ----------

GRANTS = [
    f"GRANT USE CATALOG ON CATALOG {catalog} TO `{group}`",
    # 参加者が自分のスキーマ fc_ws_<user> を作れるようにする
    f"GRANT CREATE SCHEMA ON CATALOG {catalog} TO `{group}`",
    # CSV 用スキーマ（Volume を読むため）
    f"GRANT USE SCHEMA ON SCHEMA {catalog}.{shared_schema} TO `{group}`",
    f"GRANT READ VOLUME ON VOLUME {catalog}.{shared_schema}.{volume} TO `{group}`",
    # 自由時間に自分の CSV を置くため
    f"GRANT WRITE VOLUME ON VOLUME {catalog}.{shared_schema}.{volume} TO `{group}`",
    # 見本用スキーマ（読み取りのみ）
    f"GRANT USE SCHEMA ON SCHEMA {catalog}.{sample_schema} TO `{group}`",
    f"GRANT SELECT ON SCHEMA {catalog}.{sample_schema} TO `{group}`",
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
if failed:
    print("\n⚠️ 失敗したもの（グループ名が存在するか確認してください）:")
    for g, msg in failed:
        print(f"  {g}\n    → {msg}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. 付いた権限を確認する

# COMMAND ----------

for target, kind in [
    (f"CATALOG {catalog}", "カタログ"),
    (f"SCHEMA {catalog}.{shared_schema}", "CSV 用スキーマ"),
    (f"SCHEMA {catalog}.{sample_schema}", "見本用スキーマ"),
    (f"VOLUME {catalog}.{shared_schema}.{volume}", "Volume"),
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
# MAGIC ## ✅ 次の手順
# MAGIC
# MAGIC 1. ターミナルで `databricks bundle deploy -t dev -p <profile>`
# MAGIC 2. ジョブ `[handson] 01 サンプルデータを Volume に投入` を **`load_set = A`** で実行
# MAGIC 3. パイプライン `[handson] 見本 メダリオンパイプライン` を実行（見本の gold ができます）
# MAGIC 4. 見本ダッシュボード / 見本 Genie Agent を作る（`docs/SETUP.md` 参照）
# MAGIC 5. ⭐ **参加者 1 名で `HANDSON.md` を通しリハーサル**
# MAGIC
# MAGIC ⚠️ **セット B の CSV は当日まで投入しないでください。**
# MAGIC 「新しいデータが届いてテーブルが更新される」を見せるのが当日の山場です。
