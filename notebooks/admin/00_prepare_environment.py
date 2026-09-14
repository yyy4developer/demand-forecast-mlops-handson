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
# MAGIC | 2b | ⭐⭐ **その ID をデプロイ用の変数ファイルに書き出す** | ⭐ **デプロイ時に渡す値が無くなります**（画面からデプロイできます） |
# MAGIC | 3 | ⚠️⚠️ **参加者グループを確認する** | ⚠️ **ワークスペースローカルグループでは Unity Catalog に使えません**（作り方も載せています） |
# MAGIC | 4 | 参加者に権限を付ける | ⭐ **参加者が持つ権限をここで一覧にして固定します** |
# MAGIC | 5 | 付いた権限を確認する | 当日「権限がなくて動かない」を防ぎます |
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

# COMMAND ----------

# MAGIC %md
# MAGIC ### ⭐⭐ この ID をデプロイに渡す仕組み
# MAGIC
# MAGIC ダッシュボードは SQL ウェアハウスの ID を必要としますが、
# MAGIC ID はワークスペースごとに違うのでリポジトリには書けません。
# MAGIC
# MAGIC ⭐ Databricks Asset Bundle には **変数の上書きファイル**という仕組みがあります。
# MAGIC
# MAGIC ```
# MAGIC .databricks/bundle/<ターゲット>/variable-overrides.json
# MAGIC ```
# MAGIC
# MAGIC ⭐ **デプロイのときに自動で読まれます**（画面からのデプロイでも読まれます）。
# MAGIC 下のセルがこのファイルを書き出すので、**デプロイ時に何も渡す必要がありません**。
# MAGIC
# MAGIC ⚠️ このファイルは Git 管理外（`.gitignore` 済み）です。
# MAGIC 環境ごとの値なので、リポジトリには入りません。

# COMMAND ----------

import json
import os

# このノートブックの 2 階層上が repo のルート（notebooks/admin/ の親の親）
_nb = dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(_nb), "..", ".."))
_prefix = "" if REPO_ROOT.startswith("/Workspace") else "/Workspace"

BUNDLE_TARGET = "dev"
OVERRIDE_DIR = f"{_prefix}{REPO_ROOT}/.databricks/bundle/{BUNDLE_TARGET}"
OVERRIDE_PATH = f"{OVERRIDE_DIR}/variable-overrides.json"

overrides = {"warehouse_id": WAREHOUSE_ID}

try:
    os.makedirs(OVERRIDE_DIR, exist_ok=True)
    with open(OVERRIDE_PATH, "w", encoding="utf-8") as f:
        json.dump(overrides, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"✅ 変数の上書きファイルを書き出しました:")
    print(f"   {OVERRIDE_PATH}")
    print(f"   {json.dumps(overrides, ensure_ascii=False)}")
    print()
    print("⭐ これでデプロイ時に渡す値はありません。画面の「デプロイ」を押すだけです。")
except OSError as e:
    print(f"⚠️ 書き出せませんでした: {e}")
    print()
    print("⭐ 代わりに、デプロイのときに次のようにしてください:")
    print(f"   ・画面のデプロイ: `databricks.yml` の warehouse_id の default を")
    print(f"     \"{WAREHOUSE_ID}\" に書き換える")
    print(f"   ・CLI: --var warehouse_id={WAREHOUSE_ID}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. ⚠️⚠️ 参加者グループを確認する
# MAGIC
# MAGIC ⚠️⚠️ **グループは「アカウントレベル」で作る必要があります。**
# MAGIC
# MAGIC ワークスペースの画面で作れるグループには 2 種類あり、**片方は Unity Catalog に使えません**。
# MAGIC
# MAGIC | 種類 | Unity Catalog の権限付与 | 見分け方 |
# MAGIC |---|---|---|
# MAGIC | ⭐ **アカウントグループ** | ⭐ **使えます** | アカウントコンソールで作ったもの |
# MAGIC | ⚠️ ワークスペースローカルグループ | ⚠️ **使えません** | ワークスペースだけで作ったもの |
# MAGIC
# MAGIC ⚠️ ワークスペースローカルグループに `GRANT` すると、こう言われます。
# MAGIC
# MAGIC ```
# MAGIC PRINCIPAL_DOES_NOT_EXIST: Could not find principal with name <グループ名>
# MAGIC ```
# MAGIC
# MAGIC ⚠️ **グループ名は存在しているのに「見つからない」と言われる**ので、
# MAGIC 原因に気づきにくい種類のエラーです。
# MAGIC
# MAGIC ### ⭐ グループの作り方（画面から）
# MAGIC
# MAGIC #### A. アカウントコンソールから作る（確実な方法）
# MAGIC
# MAGIC 1. **アカウントコンソール**を開く
# MAGIC    - Azure: `https://accounts.azuredatabricks.net`
# MAGIC    - AWS: `https://accounts.cloud.databricks.com`
# MAGIC 2. 左メニュー **「User management」** → **「Groups」** タブ
# MAGIC 3. 右上 **「Add group」** → グループ名を入力（例: `handson-participants`）
# MAGIC 4. 作ったグループを開き、**「Members」** に参加者を追加
# MAGIC 5. 左メニュー **「Workspaces」** → 対象ワークスペースを開く →
# MAGIC    **「Permissions」** タブ → **「Add permissions」** →
# MAGIC    ⭐ **作ったグループを追加**（これを忘れると参加者がワークスペースに入れません）
# MAGIC
# MAGIC ⚠️ **アカウント管理者の権限が必要です。** 持っていない場合は依頼してください。
# MAGIC
# MAGIC #### B. ワークスペースの設定画面から追加する（既にアカウントグループがある場合）
# MAGIC
# MAGIC 1. 右上のアイコン → **「設定」**
# MAGIC 2. **「ID とアクセス」**（Identity and access） → **「グループ」** → **「管理」**
# MAGIC 3. **「グループを追加」** → ⭐ **既存のアカウントグループを選ぶ**
# MAGIC
# MAGIC ⚠️ ここで **「新規作成」を選ぶとワークスペースローカルグループになり、
# MAGIC Unity Catalog に使えません。** 必ず既存のアカウントグループを選んでください。

# COMMAND ----------

found = api.do("GET", "/api/2.0/preview/scim/v2/Groups",
               query={"filter": f'displayName eq "{group}"'}) or {}
resources = found.get("Resources") or []

group_ok = False
if not resources:
    print(f"❌ グループ `{group}` が見つかりません。")
    print("   上の手順（A または B）で作ってから、このノートブックを再実行してください。")
else:
    g = resources[0]
    kind = (g.get("meta") or {}).get("resourceType", "?")
    print(f"グループ `{group}` が見つかりました（id={g.get('id')} / 種類={kind}）")
    print(f"  メンバー数: {len(g.get('members') or [])}")
    if kind == "WorkspaceGroup":
        print()
        print("⚠️⚠️ これは **ワークスペースローカルグループ** です。")
        print("   Unity Catalog の権限付与には使えません。")
        print("   上の手順 A でアカウントグループを作り直してください。")
    else:
        group_ok = True
        print("⭐ アカウントグループです。Unity Catalog の権限付与に使えます。")

    if not (g.get("members") or []):
        print()
        print("⚠️ メンバーがまだ 0 人です。参加者を追加してください。")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. ⭐ 参加者に権限を付ける
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
# MAGIC ### ⚠️ どこで付くかが分かれています
# MAGIC
# MAGIC | 権限 | 付ける場所 | 理由 |
# MAGIC |---|---|---|
# MAGIC | `USE CATALOG` / `CREATE SCHEMA` | ⭐ **このノートブック**（下のセル） | カタログはこのノートブックが作るため |
# MAGIC | SQL ウェアハウスの `CAN USE` | ⭐ **このノートブック**（下のセル） | ウェアハウスは既にあるため |
# MAGIC | ⭐ `USE SCHEMA` / `SELECT`（見本スキーマ） | ⭐ **deploy**（`resources/catalog_schema.yml`） | ⚠️ **スキーマは deploy が作る**ため、今 GRANT すると `SCHEMA_DOES_NOT_EXIST` になります |
# MAGIC | ⭐ `READ VOLUME`（見本の Volume） | ⭐ **deploy**（`resources/volumes.yml`） | ⚠️ 同じ理由。Volume も deploy が作ります |
# MAGIC
# MAGIC ⭐ **bundle 側に `grants:` を書いてあるので、deploy がリソース作成と権限付与を同時にやります。**
# MAGIC 手で追加する作業はありません。
# MAGIC
# MAGIC ⭐ 参加者は**自分のスキーマと Volume を自分で作る**ので、
# MAGIC そこへの書き込み権限は自動的に持ちます（作成者が所有者になります）。
# MAGIC
# MAGIC ⚠️ **これ以外に UI 側で必要なもの**（このノートブックでは付けられません）:
# MAGIC
# MAGIC - サーバーレスコンピュートが使えること
# MAGIC - ⚠️ **パイプラインを作成できること**（`00_setup_my_pipeline` で自分のパイプラインを作ります）
# MAGIC - 見本ダッシュボード / 見本 Genie Agent の `CAN VIEW`

# COMMAND ----------

# ⚠️ ここではカタログレベルの権限だけを付けます。
#
#    見本スキーマ (fc_sample) と その Volume は **DAB deploy が作る**ので、
#    このノートブックの時点では存在せず、GRANT すると
#    SCHEMA_DOES_NOT_EXIST で失敗します。
#
# ⭐ だからスキーマ / Volume の権限は bundle 側に書いてあります:
#      resources/catalog_schema.yml  → USE_SCHEMA, SELECT
#      resources/volumes.yml         → READ_VOLUME
#    deploy がリソースの作成と権限付与をまとめてやってくれます。
GRANTS = [
    f"GRANT USE CATALOG ON CATALOG {catalog} TO `{group}`",
    # ⭐ 参加者が自分のスキーマ fc_ws_<user> と Volume を作れるようにする
    f"GRANT CREATE SCHEMA ON CATALOG {catalog} TO `{group}`",
]

if not group_ok:
    print("⚠️ 参加者グループが使える状態でないため、権限付与を飛ばします。")
    print("   上の手順でアカウントグループを用意してから再実行してください。")

ok, failed = 0, []
for g in ([] if not group_ok else GRANTS):
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
    if not group_ok:
        raise RuntimeError("参加者グループが使える状態ではありません")
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
# MAGIC ## 5. 付いた権限を確認する

# COMMAND ----------

# ⭐ この時点で確認できるのはカタログレベルだけです。
print(f"[カタログ] CATALOG {catalog}")
try:
    rows = spark.sql(f"SHOW GRANTS ON CATALOG {catalog}").collect()
    got = [r["ActionType"] for r in rows if group in str(r["Principal"])]
    for a in sorted(got):
        print(f"  ✅ {a}")
    if not got:
        print("  ⚠️ 権限が見つかりません。上の 3. でグループを用意できているか確認してください。")
except Exception as e:  # noqa: BLE001
    print(f"  ⚠️ 確認できませんでした: {type(e).__name__}")

print()
print("⏭ 見本スキーマと Volume の権限は **deploy 後**に確認します。")
print(f"   deploy が終わったら、この 2 つが {group} に付いているはずです:")
print(f"     SHOW GRANTS ON SCHEMA {catalog}.{sample_schema}   → USE SCHEMA / SELECT")
print(f"     SHOW GRANTS ON VOLUME {catalog}.{sample_schema}.{volume} → READ VOLUME")

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

# 参加者グループ（アカウントグループであること）
checks.append((
    "参加者グループ",
    group if group_ok else f"{group}（アカウントグループが必要）",
    group_ok,
))

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
print("  SQL ウェアハウスの ID は、上のセルが変数の上書きファイルに書き出しました。")
print("  デプロイのときに自動で読まれます（画面からのデプロイでも読まれます）。")
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
# MAGIC 5. `src/setup/run_mmf_reference` を実行（MMF の参考結果）
# MAGIC 6. ジョブ `[handson] 見本 初回のモデル作成` を実行
# MAGIC 7. 見本 Genie Agent を画面から作る（`genie/README.md` 参照）
# MAGIC 8. ⭐ **参加者 1 名で `HANDSON.md` を通しリハーサル**
# MAGIC
# MAGIC ⭐ **見本ダッシュボードはデプロイで一緒に作られます**（手順不要）。
# MAGIC
# MAGIC ⚠️ **セット B の CSV は当日まで投入しないでください。**
# MAGIC 「新しいデータが届いてテーブルが更新される」を見せるのが当日の山場です。
