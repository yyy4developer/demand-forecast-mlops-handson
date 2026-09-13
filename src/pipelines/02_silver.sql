-- =============================================================================
-- Silver 層 — 重複を排除し、使える形に整える
-- =============================================================================
-- Bronze は「届いたものをそのまま」なので、同じデータが 2 回入りうる
-- （同じファイルを別名で置き直した、月次ファイルが再送された、など）。
-- Silver では **キーごとに最新の 1 行だけを残す**ことで、
-- 下流が「重複を気にしなくてよい」状態を作ります。
--
-- ⭐ なぜマテリアライズドビュー（MV）なのか
--
--   Bronze はストリーミングテーブル（追記専用）でした。
--   Silver は「キーごとに最新を残す」= **過去の行を上書きする**必要があるため、
--   毎回まとめて作り直す MV が向いています。
--   ⚠️ ストリーミングテーブルは追記しかできないので、重複排除には使えません。
--
-- ⭐ もう 1 つの役割: **月末日への正規化**
--
--   月次データは「2026年8月」を 2026-08-01 と書く人もいれば 2026-08-31 と書く人もいます。
--   ここで必ず月末日 (`last_day`) に揃えておくと、下流の結合が破綻しません。
--   ⚠️ 特に後半で使う Many Models Forecasting は月末日での揃えを要求します。
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 月次出荷実績
-- -----------------------------------------------------------------------------
-- 品目 × チャネル × 月 で 1 行になるように重複排除します。
-- データ品質のルール（Expectations）も付けます:
--   ⭐ ルールに反した行は「落とす」ではなく「記録して通す」設定にしています。
--      落としてしまうと、後から「なぜ数が合わないのか」を追えなくなるためです。
--      違反件数はパイプラインの画面で確認できます。
CREATE OR REFRESH MATERIALIZED VIEW silver_shipments (
  -- 制約名は ASCII のみ（日本語の識別子は SQL パーサが受け付けない）
  CONSTRAINT item_code_not_null   EXPECT (item_code IS NOT NULL),          -- 品目コードが空でない
  CONSTRAINT channel_is_known     EXPECT (channel IN ('DOM', 'EXP')),      -- チャネルが既知の値
  CONSTRAINT ym_not_null          EXPECT (ym IS NOT NULL),                 -- 年月が空でない
  CONSTRAINT qty_not_negative     EXPECT (qty >= 0)                        -- 数量がマイナスでない
)
COMMENT 'Silver: 重複排除し月末日に正規化した月次出荷実績。品目 × チャネル × 月で一意。'
CLUSTER BY (ym, item_code)
AS
WITH ranked AS (
  SELECT
    item_code,
    channel,
    -- 月のどこを指していても必ず月末日に揃える
    last_day(ym) AS ym,
    qty,
    _source_file,
    _ingested_at,
    ROW_NUMBER() OVER (
      PARTITION BY item_code, channel, last_day(ym)
      -- 同じキーが複数あれば、後から取り込んだものを採用する
      ORDER BY _ingested_at DESC, _source_file DESC
    ) AS rn
  FROM bronze_shipments
)
SELECT item_code, channel, ym, qty, _source_file, _ingested_at
FROM ranked
WHERE rn = 1;

-- -----------------------------------------------------------------------------
-- 品目マスタ
-- -----------------------------------------------------------------------------
CREATE OR REFRESH MATERIALIZED VIEW silver_items (
  CONSTRAINT item_code_not_null      EXPECT (item_code IS NOT NULL),   -- 品目コードが空でない
  CONSTRAINT demand_class_is_known   EXPECT (demand_class IN ('smooth', 'erratic', 'intermittent', 'lumpy', 'lumpy_severe'))  -- 需要分類が既知の値
)
COMMENT 'Silver: 重複排除した品目マスタ。品目コードで一意。'
AS
WITH ranked AS (
  SELECT *, ROW_NUMBER() OVER (PARTITION BY item_code ORDER BY _ingested_at DESC) AS rn
  FROM bronze_items
)
SELECT
  item_code, item_name, item_category, item_type, unit_price,
  demand_class, adi, cv2, is_domestic_only, last_day(launch_ym) AS launch_ym
FROM ranked
WHERE rn = 1;

-- -----------------------------------------------------------------------------
-- チャネル定義
-- -----------------------------------------------------------------------------
CREATE OR REFRESH MATERIALIZED VIEW silver_channels
COMMENT 'Silver: 重複排除したチャネル定義。'
AS
WITH ranked AS (
  SELECT *, ROW_NUMBER() OVER (PARTITION BY channel_code ORDER BY _ingested_at DESC) AS rn
  FROM bronze_channels
)
SELECT channel_code, channel_name, description
FROM ranked
WHERE rn = 1;

-- -----------------------------------------------------------------------------
-- 拠点別の月末在庫
-- -----------------------------------------------------------------------------
CREATE OR REFRESH MATERIALIZED VIEW silver_inventory (
  CONSTRAINT closing_qty_not_negative EXPECT (closing_qty >= 0)   -- 在庫がマイナスでない
)
COMMENT 'Silver: 重複排除し月末日に正規化した拠点別在庫。品目 × 拠点 × 月で一意。'
CLUSTER BY (ym, item_code)
AS
WITH ranked AS (
  SELECT
    item_code, site_code, last_day(ym) AS ym,
    closing_qty, safety_stock_qty, stockout_flag, _ingested_at,
    ROW_NUMBER() OVER (
      PARTITION BY item_code, site_code, last_day(ym) ORDER BY _ingested_at DESC
    ) AS rn
  FROM bronze_inventory
)
SELECT item_code, site_code, ym, closing_qty, safety_stock_qty, stockout_flag
FROM ranked
WHERE rn = 1;

-- -----------------------------------------------------------------------------
-- 標準リードタイム
-- -----------------------------------------------------------------------------
CREATE OR REFRESH MATERIALIZED VIEW silver_lead_time
COMMENT 'Silver: 重複排除した品目 × 拠点の標準リードタイム。'
AS
WITH ranked AS (
  SELECT *, ROW_NUMBER() OVER (PARTITION BY item_code, site_code ORDER BY _ingested_at DESC) AS rn
  FROM bronze_lead_time
)
SELECT item_code, site_code, standard_lead_time_days
FROM ranked
WHERE rn = 1;

-- -----------------------------------------------------------------------------
-- ベースライン予測
-- -----------------------------------------------------------------------------
CREATE OR REFRESH MATERIALIZED VIEW silver_forecast_baseline
COMMENT 'Silver: 重複排除したベースライン予測。品目 × チャネル × 対象月 × 予測実行月で一意。'
CLUSTER BY (target_ym, item_code)
AS
WITH ranked AS (
  SELECT
    item_code, channel,
    last_day(target_ym) AS target_ym,
    last_day(forecast_run_ym) AS forecast_run_ym,
    model_name, p50, lower_bound, upper_bound, _ingested_at,
    ROW_NUMBER() OVER (
      PARTITION BY item_code, channel, last_day(target_ym), last_day(forecast_run_ym), model_name
      ORDER BY _ingested_at DESC
    ) AS rn
  FROM bronze_forecast_baseline
)
SELECT item_code, channel, target_ym, forecast_run_ym, model_name, p50, lower_bound, upper_bound
FROM ranked
WHERE rn = 1;
