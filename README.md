# 需要予測 × MLOps ハンズオン

架空の産業用機器メーカー **「アクアテック工業」** の月次需要予測を題材に、
Databricks の **ダッシュボード / Genie Agent / MLflow / Unity Catalog / Lakeflow Jobs** を
手を動かしながら一通り体験するハンズオン教材です。

## 👉 参加者向けの手順は [HANDSON.md](./HANDSON.md) へ

| | 内容 |
|---|---|
| **対象** | 業務データの分析に関心のある方。Databricks の経験は不問 |
| **所要** | 約 3 時間（説明 40 分 + ハンズオン 105 分 + 自由時間 30 分） |
| **前提** | Unity Catalog が有効な Databricks ワークスペース + **Pro または Serverless** の SQL ウェアハウス |
| **進め方** | ノートブックを上から順に実行 + 画面操作（UI）を組み合わせる |
| **複数人** | スキーマが**参加者ごとに自動で分かれる**ので、同じワークスペースで同時に実施できる |

## このハンズオンで扱うこと

```
   CSV ──▶ bronze ──▶ silver ──▶ gold ──┬──▶ ① ダッシュボード（AI/BI）
   （共有）  （参加者ごとに自分で作る）        │
                                          ├──▶ ② Genie Agent（自然言語で聞く）
                                          │
                                          ├──▶ ③ ai_forecast（SQL 1 文で予測）
                                          │
                                          └──▶ ④ MLflow ─▶ Unity Catalog ─▶ バッチ推論
                                                              │              ─▶ 再学習・昇格
                                                              └──▶ ⑤ Lakeflow Jobs で自動化

                                               ⑥ MMF を自然言語で動かす（Genie Code）
```

| # | ノートブック | 内容 |
|---|---|---|
| 0 | ⭐ `00_setup_my_pipeline` | **自分の作業場所とパイプラインを作り、CSV を取り込む** |
| 1 | `01_dashboard` | AI/BI ダッシュボードを作る + Genie Code で作らせる + スケジュール配信 |
| 2 | `02_genie_agent` | Genie Agent を作って自然言語で質問する |
| 3 | `03_ai_forecast` | `ai_forecast()` で SQL 1 文だけで 18 ヶ月先を予測する |
| 4 | `04_train_register` | 特徴量 → 学習 → MLflow で実験管理 → Unity Catalog に登録 |
| 5 | `05_batch_inference` | 登録したモデルでバッチ推論する |
| 6 | `06_retrain` | 新しいデータで再学習し、良ければ本番モデルを入れ替える |
| 7 | `07_jobs` | Lakeflow Jobs で推論と再学習を自動実行にする |
| 8 | `08_mmf_genie_code` | Many Models Forecasting を自然言語の指示で動かす |
| 99 | `99_your_own_data` | ⭐ 自由時間 — 自分のデータを取り込んで試す |

## サンプルデータ

23 品目 × 2 チャネル（国内 / 海外）の月次出荷実績を **2020-01 〜 2026-08 の 80 ヶ月分**持っています。
**系列数は 39** — 国内専用の 7 品目には海外の出荷がないためです。
品目マスタ・在庫・リードタイム・ベースライン予測も付属します。

⭐ **品目ごとに需要の性質が意図的に作り分けられている**のがポイントです。

| 需要分類 | 品目数 | 性質 |
|---|---|---|
| smooth | 15 | 毎月安定して出る |
| erratic | 4 | 毎月出るが数量が振れる |
| lumpy_severe | 2 | 出ない月があり、出ると数量が大きく振れる |
| lumpy | 1 | 同上（さらに需要間隔が長い） |
| intermittent | 1 | 出ない月がある / 数量は比較的安定 |

→ ⭐ **「どの品目にも同じモデルが最適、とはならない」**ことが実際に起きるので、
モデル比較・ベストモデル選択の学習効果が出ます。

### データは完全に再現できます

`data/` 配下の CSV は生成済みの状態で commit されています。
仕様は [`src/setup/item_master_spec.yaml`](./src/setup/item_master_spec.yaml) にあり、
乱数シードが固定されているため **誰がどの環境で実行しても同じ CSV** になります。

```bash
uv run src/setup/generate_sample_data.py
git diff --stat data/          # 差分が出なければ再現できている
```

目標値（需要分類 / ADI / CV²/ 平均数量）と実測値の対比は
[`data/_generation_report.csv`](./data/_generation_report.csv) で確認できます。

## スキーマ構成

スキーマは **2 つだけ**です。

| スキーマ | 中身 | 誰が書くか |
|---|---|---|
| `fc_sample` | ⭐ **検証済みの見本すべて**（CSV の Volume / bronze→gold / メトリクスビュー / モデル / MMF 結果 / ダッシュボード） | 管理者 |
| ⭐ `fc_ws_<user>` | ⭐ **各参加者が同じものを作る場所**（Volume も含む） | ⭐ 参加者自身 |

⭐⭐ **ハンズオンのゴールは「見本を自分のスキーマに再現すること」です。**
見本には完成形が全部入っているので、詰まったら中を見比べられます。
参加者は見本の CSV を**自分の Volume にコピー**してから取り込みます。

⭐ 本来のデータ基盤なら bronze → silver → gold は**共通スキーマに 1 セット**作ります。
今回は「取り込みから自分の手で体験する」ことを目的に、参加者ごとに一式を作る構成にしています。
⚠️ この点はノートブックの冒頭でも明示しています（本番でこの形にする必要はありません）。

## ⚠️ 環境の注意点（実機検証で判明）

| # | 注意点 |
|---|---|
| 1 | ⚠️⚠️ **サーバーレスの既定環境バージョンは 1**（Python 3.10）で `mlflow` が入っていません。ML 系ノートブックは先頭で `environment_version = "5"` を宣言しています |
| 2 | ⚠️ **`ai_forecast` はノートブックの計算資源では動きません。** Pro / Serverless の SQL ウェアハウスが必要です（ノートブックが自動でそちらに投げます） |
| 3 | ⚠️ **マテリアライズドビューには列コメントも主キーも付けられません。** 列の意味と結合条件はメトリクスビューの定義に持たせています |
| 4 | ⚠️ **メトリクスビューは 1 本にファクト 1 つ**なので、需要用と予測精度用の 2 本に分けています |
| 5 | ⚠️ **日本語の識別子はバッククォートが必須**です（`` `品目カテゴリ` ``） |
| 6 | ⚠️ 作りたてのパイプラインは 1 回目の実行が失敗することがあります。ノートブックが自動で 3 回まで再試行します |

## 管理者向け — 事前準備

⭐ **参加者手順（`HANDSON.md`）とは完全に分かれています。** 手順は [docs/SETUP.md](./docs/SETUP.md) へ。

⭐⭐ **Databricks CLI は必要ありません。** Git フォルダに取り込んで、
**画面からデプロイ**できます（`databricks.yml` は YAML のみ・変数ゼロ）。

⚠️ **先に参加者グループを「アカウントレベル」で作っておいてください**
（`00` では作れません。詳細は [docs/SETUP.md](./docs/SETUP.md)）。

1. Git フォルダにこのリポジトリを clone
2. ⭐ `notebooks/admin/00_prepare_environment` を実行
   - カタログ / SQL ウェアハウス / 参加者権限を作ります
   - ⭐⭐ ウェアハウス ID を **`.databricks/bundle/dev/variable-overrides.json`** に書き出すので、
     デプロイ時に渡す値がなくなります
3. ⭐ `databricks.yml` があるフォルダを開き、画面の **「デプロイ」** を押す
4. ⚠️ **データはまだ入っていません。** サンプルデータの投入・パイプライン実行・
   メタデータ適用・MMF・初回モデルを [docs/SETUP.md](./docs/SETUP.md) の手順で実行します

### ⭐ 設定ファイルを触る必要はありません

カタログ名などは **`databricks.yml` の `variables` が唯一の設定場所**です。
⭐ ノートブックも同じファイルを読むので、変えたいときは 1 箇所だけ直します。

> 💡 CLI がある場合はこちらでも同じです。
>
> ```bash
> databricks bundle validate -t dev -p <profile>
> databricks bundle deploy   -t dev -p <profile>
> ```

| 作られるもの | リソース |
|---|---|
| 見本スキーマ | `resources/catalog_schema.yml` |
| 見本の CSV を置く Volume | `resources/volumes.yml` |
| サンプルデータ投入ジョブ | `resources/job_setup.yml` |
| 見本用の bronze → silver → gold パイプライン | `resources/pipeline_medallion.yml` |
| 完成見本のダッシュボード | `resources/dashboard_sample.yml` |
| ⭐ 完成見本の Genie Agent | `resources/genie_sample.yml` |
| 見本の月次ジョブ / 初回モデル作成ジョブ | `resources/jobs_mlops.yml` |

⚠️ **カタログと SQL ウェアハウスはこの bundle では作りません。**
`notebooks/admin/00_prepare_environment` が作ります。⭐ **デプロイの前**に実行してください。

⭐ ダッシュボードが必要とする SQL ウェアハウス ID は、同じノートブックが
`.databricks/bundle/dev/variable-overrides.json`（Git 管理外）に書き出します。
⭐ デプロイ時に自動で読まれるため、**渡す値はありません**。

⚠️ ワークスペースの URL は **プロファイルから解決される**ため `databricks.yml` には書いていません。
別のワークスペースで使う場合は `databricks auth login` でプロファイルを作り、`-p` を差し替えてください。

## ライセンス

[MIT](./LICENSE)
