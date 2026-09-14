# 管理者向け 事前準備

⚠️ **これは講師・管理者が事前に実施する手順です。** 参加者向けは [HANDSON.md](../HANDSON.md)。

⭐ **参加者手順と物理的に分離しています。** 管理者だけが持つ権限に無自覚に依存すると、
当日参加者が権限エラーで止まります。**必ず最後に「参加者 1 名での通しリハーサル」を行ってください。**

---

## ⭐ 全体の順番（先に眺めてください）

```
⚠️ STEP 0  参加者グループを「アカウントレベル」で作る（アカウント管理者）
              └─ 00 では作れません。ここだけ先に依頼が必要です

   STEP 1  Git フォルダにこのリポジトリを clone
   STEP 2  notebooks/admin/00_prepare_environment を実行
              └─ カタログ / SQL ウェアハウス / 権限 / 変数ファイル
   STEP 3  ⭐ 画面から「デプロイ」          ← 渡す値なし
              └─ ここで作られるのは「器」。データはまだ入っていません
              └─ ⚠️ Genie Agent だけ失敗します（想定どおり / STEP 6.5 で作ります）
   STEP 4  サンプルデータを Volume に投入（load_set = A）
   STEP 5  見本パイプラインを実行
   STEP 6  _uc_metadata を schema = fc_sample で実行
   STEP 6.5 ⭐⭐ もう一度デプロイ  ← ここで初めて Genie Agent が作られる
   STEP 7  ダッシュボード / Genie Agent に CAN VIEW を付ける
   STEP 8  MMF の参考結果を作る / 初回モデルを作る
   STEP 9  当日直前のウォームアップ
   STEP 10 ⭐ 参加者 1 名で通しリハーサル
```

⚠️⚠️ **STEP 3 のデプロイでデータは入りません。** STEP 4〜8 が必要です。

## ⭐ 設定ファイルを触る必要はありません

⭐ カタログ名・スキーマ名・Volume 名は **`databricks.yml` の `variables` が唯一の設定場所**です。
既定値のままなら **何も編集する必要はありません**。

| 変数 | 既定値 |
|---|---|
| `catalog` | `demand_forecast_handson` |
| `sample_schema` | `fc_sample` |
| `landing_volume` | `landing` |
| `participant_group` | `handson-participants` |
| `warehouse_id` | ⭐ 空（`00` が変数ファイルに書き出します） |

⭐ **ノートブックも同じ `databricks.yml` を読みます**（`notebooks/_config.py`）。
⚠️ 同じ値を 2 箇所に書くと食い違って事故るため、1 箇所に寄せています。
変えたいときは `databricks.yml` だけを直してください。

---

## STEP 0 — 事前チェック

- [ ] 参加者全員のアカウントが対象ワークスペースに追加されている
- [ ] 参加者を 1 つのグループにまとめている（個別付与を避けるため）
- [ ] ⚠️ **Pro または Serverless の SQL ウェアハウス**がある（`ai_forecast` は Classic では動きません）
- [ ] ⚠️ 参加者が **サーバーレスコンピュート**を使える
- [ ] ⚠️ 参加者が **パイプラインを作成できる**（`00_setup_my_pipeline` で各自が自分のパイプラインを作ります）

## ⭐⭐ Databricks CLI は必要ありません

⭐ **ワークスペースの画面だけで完結します。**
Git フォルダにこのリポジトリを取り込み、画面から bundle をデプロイします。

| 前提 | 内容 |
|---|---|
| ワークスペースファイル | 有効になっていること |
| ⭐ **サーバーレスコンピュート** | ⭐ **有効になっていること**（画面からのデプロイに必要） |
| Git フォルダ | このリポジトリを clone できること |

⚠️ **`databricks.yml` を Python で書いた bundle は画面からデプロイできません。**
このリポジトリは YAML だけなので問題ありません。

## STEP 1 — Git フォルダにリポジトリを取り込む

1. 左メニュー **「ワークスペース」** → 右上 **「作成」** → **「Git フォルダ」**
2. このリポジトリの URL を入れて作成

## STEP 2 — ⚠️⚠️ 環境準備のノートブックを先に実行する

⚠️ **デプロイより先に実行してください。** 順番を逆にすると失敗します。

ノートブック **`notebooks/admin/00_prepare_environment`** を実行します。
これ 1 本で、デプロイに必要なものが全部揃います。

| # | 作られるもの |
|---|---|
| 1 | ⭐ **カタログ** |
| 2 | ⭐ **SQL ウェアハウス**（無ければ Pro + サーバーレスで新規作成） |
| 2b | ⭐⭐ **`.databricks/bundle/dev/variable-overrides.json`**（⭐ **`00` が使った値を全部**デプロイに渡すため） |
| 3 | ⚠️ **参加者グループの種類の判定**（アカウントグループかどうか） |
| 4 | ⭐ **参加者グループへの権限**（⚠️ **カタログとウェアハウスだけ**）|
| 5 | ⭐ **デプロイ準備状況のサマリ**（何が揃ったか / 渡す値は無いこと） |

> ⚠️ **なぜ bundle でカタログを作らないのか**
>
> Default Storage 構成のメタストアでは、API 経由の `CREATE CATALOG` が
> 「storage root がない」と言って失敗します。SQL 経由なら保存先が自動で決まるため通ります。

> ⭐⭐ **なぜウェアハウスをここで作るのか**
>
> ダッシュボードは SQL ウェアハウスの ID を必要としますが、ID はワークスペースごとに違うので
> リポジトリには書けません。
>
> ⭐ Databricks Asset Bundle には **変数の上書きファイル**という仕組みがあります。
>
> ```
> .databricks/bundle/<ターゲット>/variable-overrides.json
> ```
>
> ⭐ **デプロイのときに自動で読まれます**（画面からのデプロイでも読まれます）。
> ⚠️ このファイルは Git 管理外なので、リポジトリには入りません。
>
> ⭐⭐ **`00` が使った値が全部書き出されます。**
>
> ```json
> { "catalog": "...", "warehouse_id": "...", "sample_schema": "fc_sample",
>   "landing_volume": "landing", "participant_group": "..." }
> ```
>
> ⚠️⚠️ **カタログ名やグループ名をウィジェットで変えたら、`00` を必ず再実行してください。**
> このファイルが古いままだと、デプロイは `databricks.yml` の**既定値**を使い、
> 「そんなカタログは無い」というエラーになります。
>
> ⚠️ ウィジェット名と bundle 変数名が 1 か所だけ違います:
> ウィジェット `volume` → bundle 変数 `landing_volume`（`00` が変換して書き出します）。

> ⚠️⚠️ **見本スキーマと Volume の権限は `00` では付きません。**
>
> `fc_sample` とその Volume は **STEP 3 のデプロイが作る**ので、`00` の時点では
> 存在せず、GRANT すると `SCHEMA_DOES_NOT_EXIST` で失敗します。
>
> ⭐ そこで bundle 側に `grants:` を書いてあります。
>
> | ファイル | 付く権限 |
> |---|---|
> | `resources/catalog_schema.yml` | `USE_SCHEMA` / `SELECT` |
> | `resources/volumes.yml` | `READ_VOLUME` |
>
> ⭐ **デプロイがリソースの作成と権限付与を同時にやる**ので、手作業はありません。

## STEP 3 — ⭐ 画面から bundle をデプロイする

1. Git フォルダの中の **`databricks.yml` があるフォルダ**を開く
2. 画面に出る **「デプロイ」** を押す
3. ⭐ **渡す値はありません。** そのままデプロイできます

> ⚠️⚠️⚠️ **1 回目は Genie Agent だけ失敗します。想定どおりなので進んでください。**
>
> ```
> Error: cannot create resources.genie_spaces.demand_agent_sample:
>   Failed to fetch tables for the agent.
>   Table '<catalog>.fc_sample.mv_demand' does not exist  (403 PERMISSION_DENIED)
> ```
>
> ⭐ Genie Agent の作成 API は**参照テーブルが実在するかを検証します**。
> ところが `mv_demand` / `mv_forecast_accuracy` は
> **デプロイ → CSV 投入 → パイプライン実行 → gold → メトリクスビュー**
> の順にできるので、⚠️ デプロイの時点では存在しません。
>
> ⚠️ `403 PERMISSION_DENIED` と出ますが、**権限の問題ではありません**（中身は「テーブルが無い」）。
>
> ⭐⭐ **他のリソースは 1 回目で全部作られます**（実機で確認済み）:
> スキーマ / Volume / パイプライン / ジョブ 3 本 / ダッシュボード / ⭐ **権限付与も**。
>
> ⭐ Genie Agent は **STEP 6.5 でもう一度デプロイ**すると作られます。

⭐ 作られるもの: 見本スキーマ `fc_sample` / その Volume `landing` /
データ投入ジョブ / 見本パイプライン / ⭐ **見本ダッシュボード** /
見本の月次ジョブ / 初回モデル作成ジョブ

> 💡 CLI を持っている場合は次でも同じです（CI/CD や別ワークスペースへの配置はこちら）。
>
> ```bash
> databricks bundle validate -t dev -p <profile>
> databricks bundle deploy   -t dev -p <profile>
> ```

作られるもの: 見本スキーマ `fc_sample` / その Volume `landing` /
データ投入ジョブ / 見本用パイプライン / 見本ダッシュボード / 見本の月次ジョブ

⚠️ **参加者ごとのスキーマと Volume は作りません。** 参加者が `00` を実行したときに
自分で作ります（`notebooks/_config.py` が担当）。

### ⭐ デプロイ直後に権限を確認する

```sql
SHOW GRANTS ON SCHEMA <catalog>.fc_sample;          -- USE SCHEMA / SELECT
SHOW GRANTS ON VOLUME <catalog>.fc_sample.landing;  -- READ VOLUME
```

⚠️ 付いていない場合は、参加者グループ名（`participant_group`）が
**アカウントグループとして実在するか**を確認してください。
⚠️ ワークスペースローカルのグループは UC の GRANT に使えません。

## STEP 4 — サンプルデータを投入（⚠️ セット A だけ）

ジョブ **`[handson] 01 サンプルデータを Volume に投入`** を **`load_set = A`** で実行。

⚠️⚠️ **セット B（`shipments_2026_08.csv`）は当日まで投入しないでください。**
「新しいデータが届いてテーブルが更新される」を見せるのが当日の山場です。

## STEP 5 — 見本の gold を作る

パイプライン **`[handson] 見本 メダリオンパイプライン`** を実行。
`fc_sample` に gold 7 テーブルができます。

⚠️ サーバーレスの初回起動に **4〜6 分**かかります。

## STEP 6 — 見本用のメタデータとメトリクスビュー

ノートブック `notebooks/_uc_metadata` を **`schema = fc_sample`** で実行。
⭐ 単体で動くようになっているので、ジョブから `base_parameters` で渡しても構いません。

⚠️ これを飛ばすと、見本 Genie Agent の回答精度が出ません。

## STEP 6.5 — ⭐⭐ もう一度デプロイして Genie Agent を作る

⭐ **STEP 6 でメトリクスビューができたので、ここで初めて Genie Agent が作れます。**

1. Git フォルダの **`databricks.yml` があるフォルダ**を開く
2. **「デプロイ」** をもう一度押す

⭐ 今度は成功します。作られるのは Genie Agent 1 つだけで、
他のリソースは変更なしとして扱われます。

### ⭐ 成功したか確認する

```bash
databricks api get "/api/2.0/genie/spaces?page_size=20" -p <profile>
```

⭐ `[handson] 見本 需要分析エージェント` が 1 件返れば完了です。

> ⚠️ ここで失敗する場合は、STEP 6 のメトリクスビューが本当にできているか確認してください。
>
> ```sql
> SHOW TABLES IN <catalog>.fc_sample LIKE 'mv_*';   -- mv_demand / mv_forecast_accuracy
> ```

> 💡 **なぜ 2 回に分かれるのか（設計上の制約）**
>
> Genie Agent は参照テーブルの実在を要求し、そのテーブルはデプロイが作った
> パイプラインを**実行してから**できます。⚠️ 1 回のデプロイでは順序を満たせません。
> ⭐ Genie Agent を bundle の外（ノートブックから REST で作成）に出せば 1 回で済みますが、
> ⭐ **「Genie Agent も DAB で管理できる」ことを示すため** bundle に残しています。

---

## STEP 7 — 見本のダッシュボードと Genie Agent

⭐ **ダッシュボードは STEP 3 のデプロイで、Genie Agent は STEP 6.5 のデプロイで作られています。**
作成作業は不要です。

⚠️ **参加者グループに `CAN VIEW` を付けてください**（それぞれの画面の「共有」から）。
⚠️ どちらも**開いた人の権限**でクエリを実行するため、
参加者が見本スキーマを読めないと開いてもエラーになります
（⭐ **STEP 3 のデプロイ**が `USE SCHEMA` / `SELECT` を付けています）。

> ⭐ Genie Agent の定義（`resources/genie_sample.yml`）は公開ドキュメントに形式が無く、
> API を試して特定しました。要点は同ファイルのコメントに書いてあります。

## STEP 8 — MMF のスキルを配置（`08` を触らせる場合）

⚠️ **参加者全員のフォルダに配置**が必要です。配置しないとスキルが読み込まれず、
AI が手順を無視して勝手に進みます。

```bash
# MMF のリポジトリに公式のインストーラがあります
python skills/install.py

# または手動で
databricks workspace import-dir skills/databricks-skills/many-model-forecasting \
  /Users/${USER}/.assistant/skills --overwrite
databricks workspace import skills/assistant_instructions.md \
  /Users/${USER}/.assistant_instructions.md --format AUTO --language MARKDOWN --overwrite
```

⭐ MMF を最後まで通した結果を **`fc_sample` に `scm_*` として残しておく**と、
当日は結果を見せるだけで済みます（`08` がそこを読みます）。

⚠️ MMF は Databricks の正式サポート対象外（AS-IS）で、**DBR 18 for ML 以上**が必要です。
⭐ CPU だけで動くモデルに絞れば GPU は不要です。

## STEP 8.5 — ⭐ 見本ジョブを一度動かしておく

⭐ `07_jobs` の答え合わせ用に、動くお手本を用意してあります。

```bash
# ① 初回だけ: 本番モデル（@champion）を作る
databricks bundle run initial_train_sample -t dev -p <profile> --var warehouse_id=<id>

# ② 月次サイクルを通しで動かす（CSV 取り込み → パイプライン → 再学習 → 予測と評価）
databricks bundle run monthly_forecast_cycle_sample -t dev -p <profile> --var warehouse_id=<id>
```

⚠️ **順番が大事です。** ② は「今の本番と比べる」処理なので、① を先に実行して
比べる相手を作っておかないと失敗します。

⭐ 実測 **5.8 分**で 4 タスクが通ります（内訳: CSV 投入 0.6 / パイプライン 2.1 / 再学習 1.7 / 評価 1.3 分）。

⭐ **通ったときに確認できること**（実測値）

| | 結果 |
|---|---|
| `fc_sample.fct_shipments` | 3,081 → ⭐ **3,120 行**（2026-08 が入る） |
| `fc_sample.fct_forecast_accuracy_all` | ⭐ **5,343 行 / 3 手法**、`target_ym` が 2026-08-31 まで |
| `fc_sample.demand_forecast` | ⭐ **v2 が登録され `@champion` に昇格** |

⚠️⚠️ **試し実行したら、必ず `fc_sample` をセット A の状態に戻してください。**

```bash
# ① 見本 Volume からセット B を削除
databricks fs rm dbfs:/Volumes/<catalog>/fc_sample/landing/shipments/shipments_2026_08.csv -p <profile>

# ② 見本パイプラインをフルリフレッシュ（gold が 3,081 行に戻る）
databricks api post "/api/2.0/pipelines/<pipeline_id>/updates" --json '{"full_refresh": true}' -p <profile>
```

⚠️ **戻し忘れると `00` の「見本と見比べる」が全テーブルで「ずれています」になり、
さらに参加者の `00` が CSV を両方コピーして `07` の見せ場が消えます。**

> 💡 見本のモデル (`v2 @champion`) と `fct_forecast_accuracy_all` は 1 か月分先の
> ままになりますが、⭐ **参加者はどちらも参照しません**
> （`00` が比べるのは gold 7 テーブルの行数、`08` が読むのは `scm_*` だけ）。

## STEP 9 — 当日直前のウォームアップ

- [ ] SQL ウェアハウスを起動しておく
- [ ] 見本パイプラインを 1 回空実行しておく
- [ ] ⚠️ **セット B はまだ投入しない**（`fc_sample.fct_shipments` の最終月が **2026-07-31** であることを確認）
- [ ] ⭐ `data/shipments_2026_08.csv` を参加者に配る準備（Slack の下書きまで作っておく）

## STEP 10 — ⭐ 参加者 1 名での通しリハーサル

⚠️⚠️ **最重要。** 管理者アカウントではなく、**参加者グループの権限だけを持つアカウント**で
`HANDSON.md` を上から読み、書かれている通りにだけ操作して最後まで通してください。

- [ ] 各 Part の所要時間を実測する
- [ ] 権限エラーが出た箇所を反映する（カタログ＝`00` / スキーマ・Volume＝bundle の `grants:`）
- [ ] ⚠️ ML 系ノートブック（`04`〜`06`）で **環境バージョンが 5 になっているか**確認する

---

## 当日の進め方（新しい月の CSV の配布と投入）

⭐⭐ **投入は参加者が `07_jobs` の中で自分の手で行います。** 講師はファイルを配るだけです。
⚠️ notebook（`load_csv_to_volume`）で投入するのは**検証用**で、当日の参加者向けには使いません。

### 前日までに

- [ ] ⭐ `data/shipments_2026_08.csv`（**928 バイト / 39 行**）を Slack かメールで配れる状態にする
- [ ] ⚠️⚠️ **`fc_sample` にセット B を投入しないこと**
      → 参加者の `00` が A と B の両方をコピーしてしまい、⭐ `07` の見せ場が消えます

### 当日（参加者が `06_retrain` を終えたタイミング）

1. ⭐ 講師が `shipments_2026_08.csv` を参加者に配布する（Slack / メール）
2. 参加者が `07_jobs` の手順で進める
   - ジョブを作る（`pipeline` → `retrain` → `inference`）
   - ⭐ **ファイル到着トリガー**を設定する（監視パス = 自分の Volume の `landing/shipments/`）
   - ⭐ カタログ画面から CSV をアップロードする
   - ⭐ 自動起動を確認する（⚠️ 3 分待って動かなければ「今すぐ実行」）
3. ⭐ 講師は同じタイミングで見本ジョブ **`[handson] 見本 需要予測の月次更新`** を実行する
   → ⭐ 見本 (`fc_sample`) も 2026-08 になり、参加者が自分のスキーマと見比べられます
   → ⭐ **こちらは CSV 投入まで含めた 4 タスク**なので「人が触る場所がゼロ」の完成形になります

### ⚠️ 実測で分かったファイル到着トリガーの癖

| 事象 | 実測 |
|---|---|
| ⚠️ **設定直後に置いた 1 本目** | **発火しない**（設定した時点の中身を「基準」として記録するため） |
| ⭐ 2 本目以降 | ⭐ **約 40 秒で発火**（`trigger=FILE_ARRIVAL` を確認） |
| 監視先 | ⭐ **UC Volume のサブディレクトリを直接指定できる** |

⭐ **だから「トリガーを設定 → 説明を 2〜3 分挟む → アップロード」の順にしてください。**
⚠️ それでも発火しない場合は「今すぐ実行」で手動起動すれば**結果は同じ**です
（CSV はすでに `shipments/` にあるので、パイプラインが取り込みます）。

### ⚠️ 「昇格」はいつ起きるか（整理）

| 実行 | データ | 学習期間の伸び | 昇格 |
|---|---|---|---|
| ⭐ **参加者が `06_retrain` を手で実行** | 2026-07 まで | ⭐ **+6 か月**（`04` の目隠しを外す） | ⭐ **確実に昇格**（検証済み） |
| `07` のジョブ内の `06`（CSV 投入後） | 2026-08 まで | +1 か月だけ | ⚠️ **見送りになることがある** |

⭐ **昇格は `06` を手で回した時点で必ず見えます。** `04` が
`MODEL_BUILT_MONTHS_AGO = 6` で「半年前に作られた本番モデル」を意図的に作っているためです。

⚠️ `07` のジョブでは 1 か月しか増えないので、**見送りが出ます。**
⭐ **これは失敗ではありません。** 「作り直しても良くならないことがある / だから比べる」という
`06` のメッセージがそのまま実演される場面です。当日はそう説明してください。

### notebook による CSV 投入の位置づけ

| 使い方 | 位置づけ |
|---|---|
| `load_set = A`（STEP 4） | ⭐ **必須** — 見本データの事前投入 |
| `load_set = B`（見本ジョブのタスク 1） | ⭐ 見本ジョブ用 / ⭐ **e2e 検証用**。⚠️ 参加者向けには使わない |

⚠️ **検証で見本ジョブを試し実行した場合は、当日前に `fc_sample` をセット A の状態に戻してください。**
（`fc_sample` の Volume から `shipments_2026_08.csv` を削除し、見本パイプラインを
**フルリフレッシュ**で再実行）

---

## 後片付け

```bash
# 参加者のスキーマとパイプライン
#   → notebooks/admin/99_cleanup を dry_run=false で実行

# 共有スキーマ・見本・Volume・パイプライン・ジョブ
databricks bundle destroy -t dev -p <profile>
```

⚠️ カタログ自体は意図せず消さないよう手動で削除してください。
