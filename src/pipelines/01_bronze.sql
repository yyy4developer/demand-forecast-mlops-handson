-- =============================================================================
-- Bronze 層 — Volume に届いた CSV をそのまま取り込む
-- =============================================================================
-- Auto Loader (`STREAM read_files`) を使って、Volume に置かれた CSV を
-- 増分で取り込みます。**一度取り込んだファイルは二度読まれません。**
--
-- ⭐ だから「新しい CSV を置く → パイプラインを実行する」だけで、
--    差分だけがテーブルに追加されます。
--
-- ⚠️ 逆に言うと、**同じ名前のファイルを上書きしても取り込まれません**。
--    新しい月のデータは必ず新しいファイル名で置いてください。
--
-- この層では型変換もクレンジングも**しません**。
-- 「届いたものをそのまま残す」のが Bronze の役割です。
-- (元データに戻って調べ直せる状態を必ず残しておく、という考え方)
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 月次出荷実績 ← ★ ハンズオン当日、ここに新しい CSV が追加される
-- -----------------------------------------------------------------------------
CREATE OR REFRESH STREAMING TABLE bronze_shipments
COMMENT 'Bronze: 月次出荷実績の生データ。Volume の shipments/ を Auto Loader で増分取り込み。'
AS SELECT
  *,
  _metadata.file_path AS _source_file,
  _metadata.file_modification_time AS _source_modified_at,
  current_timestamp() AS _ingested_at
FROM STREAM read_files(
  '${landing_path}/shipments/',
  format => 'csv',
  header => true,
  -- 型を明示しておくと、CSV の中身から推論を外して事故を防げる
  schemaHints => 'item_code STRING, channel STRING, ym DATE, qty INT'
);

-- -----------------------------------------------------------------------------
-- 品目マスタ
-- -----------------------------------------------------------------------------
CREATE OR REFRESH STREAMING TABLE bronze_items
COMMENT 'Bronze: 品目マスタの生データ。'
AS SELECT
  *,
  _metadata.file_path AS _source_file,
  current_timestamp() AS _ingested_at
FROM STREAM read_files(
  '${landing_path}/items/',
  format => 'csv',
  header => true,
  schemaHints => 'item_code STRING, item_name STRING, item_category STRING, item_type STRING, unit_price INT, demand_class STRING, adi DOUBLE, cv2 DOUBLE, is_domestic_only BOOLEAN, launch_ym DATE'
);

-- -----------------------------------------------------------------------------
-- チャネル定義
-- -----------------------------------------------------------------------------
CREATE OR REFRESH STREAMING TABLE bronze_channels
COMMENT 'Bronze: チャネル定義の生データ。'
AS SELECT
  *,
  _metadata.file_path AS _source_file,
  current_timestamp() AS _ingested_at
FROM STREAM read_files(
  '${landing_path}/channels/',
  format => 'csv',
  header => true,
  schemaHints => 'channel_code STRING, channel_name STRING, description STRING'
);

-- -----------------------------------------------------------------------------
-- 拠点別の月末在庫
-- -----------------------------------------------------------------------------
CREATE OR REFRESH STREAMING TABLE bronze_inventory
COMMENT 'Bronze: 拠点別の月末在庫・安全在庫・欠品フラグの生データ。'
AS SELECT
  *,
  _metadata.file_path AS _source_file,
  current_timestamp() AS _ingested_at
FROM STREAM read_files(
  '${landing_path}/inventory/',
  format => 'csv',
  header => true,
  schemaHints => 'item_code STRING, site_code STRING, ym DATE, closing_qty INT, safety_stock_qty INT, stockout_flag INT'
);

-- -----------------------------------------------------------------------------
-- 標準リードタイム
-- -----------------------------------------------------------------------------
CREATE OR REFRESH STREAMING TABLE bronze_lead_time
COMMENT 'Bronze: 品目 × 拠点の標準リードタイムの生データ。'
AS SELECT
  *,
  _metadata.file_path AS _source_file,
  current_timestamp() AS _ingested_at
FROM STREAM read_files(
  '${landing_path}/lead_time/',
  format => 'csv',
  header => true,
  schemaHints => 'item_code STRING, site_code STRING, standard_lead_time_days INT'
);

-- -----------------------------------------------------------------------------
-- ベースライン予測（前年同月ナイーブ）
-- -----------------------------------------------------------------------------
-- ⭐ 「去年と同じ数量を予測値とする」だけの、最も単純な予測です。
--    機械学習モデルを作ったら、まずこれと比べます。
--    ⚠️ 単純なのに意外と強く、これに勝てない品目も珍しくありません。
CREATE OR REFRESH STREAMING TABLE bronze_forecast_baseline
COMMENT 'Bronze: 前年同月ナイーブによるベースライン予測の生データ。'
AS SELECT
  *,
  _metadata.file_path AS _source_file,
  current_timestamp() AS _ingested_at
FROM STREAM read_files(
  '${landing_path}/forecast_baseline/',
  format => 'csv',
  header => true,
  schemaHints => 'item_code STRING, channel STRING, target_ym DATE, forecast_run_ym DATE, model_name STRING, p50 DOUBLE, lower_bound DOUBLE, upper_bound DOUBLE'
);
