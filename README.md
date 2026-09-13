# 需要予測 × MLOps ハンズオン

架空の産業用機器メーカー **「アクアテック工業」** の月次需要予測を題材に、
Databricks の **ダッシュボード / Genie Agent / MLflow / Unity Catalog / Lakeflow Jobs** を
手を動かしながら一通り体験するハンズオン教材です。

## 👉 参加者向けの手順は [HANDSON.md](./HANDSON.md) へ

| | 内容 |
|---|---|
| **対象** | 業務データの分析に関心のある方。Databricks の経験は不問 |
| **所要** | 約 3 時間（説明 40 分 + ハンズオン 105 分 + 自由時間 30 分） |
| **前提** | Unity Catalog が有効な Databricks ワークスペース + Serverless SQL ウェアハウス |
| **進め方** | ノートブックを上から順に実行 + 画面操作（UI）を組み合わせる |
| **複数人** | スキーマが**参加者ごとに自動で分かれる**ので、同じワークスペースで同時に実施できる |

## このハンズオンで扱うこと

```
   CSV ──▶ bronze ──▶ silver ──▶ gold ──┬──▶ ① ダッシュボード（AI/BI）
        （事前構築済み・仕組みだけ紹介）      │
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
| 0 | `00_gold_tables_walkthrough` | 事前構築済みテーブルの成り立ちを読む（実行なし） |
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

23 品目 × 2 チャネル（国内 / 海外）の月次出荷実績を **2020-01 〜 2026-08 の 80 ヶ月分**（39 系列）
持っています。品目マスタ・在庫・リードタイム・ベースライン予測も付属します。

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

## 管理者向け — 事前準備

⭐ **参加者手順（`HANDSON.md`）とは完全に分かれています。** 手順は [docs/SETUP.md](./docs/SETUP.md) へ。

事前構築物はすべて Databricks Asset Bundle で作られます。

```bash
databricks bundle validate -t dev -p <profile>
databricks bundle deploy   -t dev -p <profile>
```

| 作られるもの | リソース |
|---|---|
| カタログ / 共有スキーマ | `resources/catalog_schema.yml` |
| CSV 投入先の Volume | `resources/volumes.yml` |
| サンプルデータ投入ジョブ | `resources/job_setup.yml` |
| bronze → silver → gold パイプライン | `resources/pipeline_medallion.yml` |
| 完成見本のダッシュボード | `resources/dashboard_sample.yml` |
| 完成見本の Genie Agent | `resources/genie_sample.yml` |
| バッチ推論 / 再学習ジョブの見本 | `resources/jobs_mlops.yml` |

⚠️ ワークスペースの URL は **プロファイルから解決される**ため `databricks.yml` には書いていません。
別のワークスペースで使う場合は `databricks auth login` でプロファイルを作り、`-p` を差し替えてください。

## ライセンス

[MIT](./LICENSE)
