# 管理者向け 事前準備

⚠️ **これは講師・管理者が事前に実施する手順です。** 参加者向けは [HANDSON.md](../HANDSON.md)。

⭐ **参加者手順と物理的に分離しています。** 管理者だけが持つ権限に無自覚に依存すると、
当日参加者が権限エラーで止まります。**必ず最後に「参加者 1 名での通しリハーサル」を行ってください。**

---

## STEP 0 — 事前チェック

- [ ] 参加者全員のアカウントが対象ワークスペースに追加されている
- [ ] 参加者を 1 つのグループにまとめている（個別付与を避けるため）
- [ ] ⚠️ **Pro または Serverless の SQL ウェアハウス**がある（`ai_forecast` は Classic では動きません）
- [ ] ⚠️ 参加者が **サーバーレスコンピュート**を使える
- [ ] ⚠️ 参加者が **パイプラインを作成できる**（`00_setup_my_pipeline` で各自が自分のパイプラインを作ります）

## STEP 1 — 認証

```bash
databricks auth login --host <workspace-url> --profile <profile>
```

## STEP 2 — ⚠️ カタログを作る（bundle より先に）

⚠️ **順番を逆にすると失敗します。**

ノートブック `notebooks/admin/00_prepare_environment` を実行してください。
カタログ作成と参加者への権限付与をまとめて行います。

> ⚠️ **なぜ bundle でカタログを作らないのか**
>
> Default Storage 構成のメタストアでは、API 経由の `CREATE CATALOG` が
> 「storage root がない」と言って失敗します。SQL 経由なら保存先が自動で決まるため通ります。

## STEP 3 — bundle をデプロイ

```bash
databricks bundle validate -t dev -p <profile>
databricks bundle deploy   -t dev -p <profile>
```

作られるもの: 見本スキーマ `fc_sample` / その Volume `landing` /
データ投入ジョブ / 見本用パイプライン / 見本ダッシュボード / 見本の月次ジョブ

⚠️ **参加者ごとのスキーマと Volume は作りません。** 参加者が `00` を実行したときに
自分で作ります（`notebooks/_config.py` が担当）。

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

## STEP 7 — 見本のダッシュボードと Genie Agent を作る

⚠️ **画面から手で作ります**（自動化できません）。

1. `fc_sample` を参照するダッシュボードを作り、名前に **「見本」** を入れる
   （`01_dashboard` が名前で探します）
2. `fc_sample.mv_demand` と `fc_sample.mv_forecast_accuracy` を渡した Genie Agent を作り、
   名前に **「見本」** を入れる
3. どちらも参加者グループに **`CAN VIEW`** を付ける

⭐ 作ったあと、リポジトリに取り込んでおくと次回から配布できます。

```bash
databricks bundle generate dashboard   --existing-path "<見本ダッシュボードのパス>" --key demand_overview
databricks bundle generate genie-space --key demand_agent
```

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

⭐ 実測 **5 分半**で 4 タスクが通ります。

## STEP 9 — 当日直前のウォームアップ

- [ ] SQL ウェアハウスを起動しておく
- [ ] 見本パイプラインを 1 回空実行しておく
- [ ] ⚠️ **セット B はまだ投入しない**

## STEP 10 — ⭐ 参加者 1 名での通しリハーサル

⚠️⚠️ **最重要。** 管理者アカウントではなく、**参加者グループの権限だけを持つアカウント**で
`HANDSON.md` を上から読み、書かれている通りにだけ操作して最後まで通してください。

- [ ] 各 Part の所要時間を実測する
- [ ] 権限エラーが出た箇所を STEP 2 の GRANT に反映する
- [ ] ⚠️ ML 系ノートブック（`04`〜`06`）で **環境バージョンが 5 になっているか**確認する

---

## 当日の進め方（セット B の投入タイミング）

⭐ **`07_jobs` の直前**が良いタイミングです。

1. 参加者が `06_retrain` まで終わったら、講師が
   ジョブ `[handson] 01 サンプルデータを Volume に投入` を **`load_set = B`** で実行
2. 参加者に `00_setup_my_pipeline` の実行セルをもう一度回してもらう
   → ⭐ **2026-08 のデータが増えます**
3. `06_retrain` をもう一度回してもらう
   → ⭐ **新しいデータで再学習し、勝てば本番が入れ替わります**

⚠️ 同名ファイルの上書きでは Auto Loader が取り込まないため、
セット B は**別ファイル名**（`shipments_2026_08.csv`）になっています。

### ⚠️ 「昇格」は必ず起きるわけではありません

1 か月分データが増えただけでは挑戦者と本番の差はわずかで、**見送りになることもあります**。
⭐ 見送りも正しい結果です（「作り直しても良くならないことがある」が伝わります）が、
当日「昇格」を見せたい場合は次のどちらかを使ってください。

| 方法 | やり方 |
|---|---|
| ⭐ 推奨 | **セット B を投入する前に `04` を実行**しておく（本番モデルが古いデータで学習された状態を作る） |
| 代替 | `06` の判定基準（MAE と MASE）を実行結果を見ながら口頭で説明し、**両方の分岐**を見せる |

⚠️ **どちらの結果になっても説明できるよう、事前に一度通しておいてください。**

---

## 後片付け

```bash
# 参加者のスキーマとパイプライン
#   → notebooks/admin/99_cleanup を dry_run=false で実行

# 共有スキーマ・見本・Volume・パイプライン・ジョブ
databricks bundle destroy -t dev -p <profile>
```

⚠️ カタログ自体は意図せず消さないよう手動で削除してください。
