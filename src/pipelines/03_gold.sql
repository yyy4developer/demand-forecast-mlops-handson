-- =============================================================================
-- Gold 層 — 業務でそのまま使える形にする
-- =============================================================================
-- ダッシュボード・Genie Agent・機械学習モデルが直接読むのはこの層です。
--
-- ⭐ 設計の方針: **必要な軸を落とさない**
--
--   Gold で集計しすぎると、後から「チャネル別で見たい」「カテゴリ別で見たい」と
--   言われても戻せません。ダッシュボードで絞り込みたい項目は必ず列として残します。
--   ⭐ 「後から足し合わせる」のは簡単ですが、「失った軸を取り戻す」のは不可能です。
--
-- ⭐ ファクトとディメンションは分けたまま持ちます
--
--   出荷実績（ファクト）に品目名やカテゴリを埋め込んでしまうこともできますが、
--   分けておくと ① マスタの修正が 1 箇所で済む ② 主キー・外部キーの関係を
--   Unity Catalog に登録でき、Genie Agent が結合を正しく理解できる、という利点があります。
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 月次出荷実績（ファクト）
-- -----------------------------------------------------------------------------
-- ⭐ 金額 (`amount`) を足しています。数量だけだと「電極パッド 1,000 個」と
--    「計測ユニット 1 台」が同じ重みに見えてしまい、業務判断に使いにくいためです。
CREATE OR REFRESH MATERIALIZED VIEW fct_shipments
COMMENT 'Gold: 月次出荷実績。品目 × チャネル × 月で一意。需要予測の入力になる中心テーブル。'
CLUSTER BY (ym, item_code)
AS SELECT
  s.item_code,
  s.channel,
  s.ym,
  s.qty,
  CAST(s.qty * i.unit_price AS BIGINT) AS amount
FROM silver_shipments s
LEFT JOIN silver_items i USING (item_code);

-- -----------------------------------------------------------------------------
-- 品目マスタ（ディメンション）
-- -----------------------------------------------------------------------------
CREATE OR REFRESH MATERIALIZED VIEW dim_item
COMMENT 'Gold: 品目マスタ。カテゴリ・本体/消耗品・需要分類・国内専用フラグを持つ。集計の軸になる。'
AS SELECT
  item_code,
  item_name,
  item_category,
  item_type,
  unit_price,
  demand_class,
  adi,
  cv2,
  is_domestic_only,
  launch_ym
FROM silver_items;

-- -----------------------------------------------------------------------------
-- チャネル定義（ディメンション）
-- -----------------------------------------------------------------------------
CREATE OR REFRESH MATERIALIZED VIEW dim_channel
COMMENT 'Gold: チャネル定義。DOM = 国内、EXP = 海外。'
AS SELECT channel_code, channel_name, description
FROM silver_channels;

-- -----------------------------------------------------------------------------
-- 標準リードタイム（ディメンション）
-- -----------------------------------------------------------------------------
CREATE OR REFRESH MATERIALIZED VIEW dim_lead_time
COMMENT 'Gold: 品目 × 拠点の標準リードタイム日数。「いつ発注すれば間に合うか」の判断に使う。'
AS SELECT item_code, site_code, standard_lead_time_days
FROM silver_lead_time;

-- -----------------------------------------------------------------------------
-- 拠点別の月末在庫（ファクト）
-- -----------------------------------------------------------------------------
CREATE OR REFRESH MATERIALIZED VIEW fct_inventory
COMMENT 'Gold: 拠点別の月末在庫・安全在庫・欠品フラグ。「欠品」「余剰在庫」を見るためのテーブル。'
CLUSTER BY (ym, item_code)
AS SELECT
  item_code,
  site_code,
  ym,
  closing_qty,
  safety_stock_qty,
  stockout_flag,
  -- 安全在庫に対してどれだけ余っている / 足りないか
  closing_qty - safety_stock_qty AS surplus_qty
FROM silver_inventory;

-- -----------------------------------------------------------------------------
-- ベースライン予測（ファクト）
-- -----------------------------------------------------------------------------
-- ⭐ 前年同月ナイーブ = 「去年の同じ月と同じ数量が出る」と予測するだけの手法。
--    機械学習モデルを作ったら、**まずこれに勝てているかを確認**します。
CREATE OR REFRESH MATERIALIZED VIEW fct_forecast_baseline
COMMENT 'Gold: 前年同月ナイーブによるベースライン予測。自作モデルの比較対象になる。'
CLUSTER BY (target_ym, item_code)
AS SELECT
  item_code,
  channel,
  target_ym,
  forecast_run_ym,
  model_name,
  p50,
  lower_bound,
  upper_bound
FROM silver_forecast_baseline;

-- -----------------------------------------------------------------------------
-- ⭐ 予実比較（ファクト）
-- -----------------------------------------------------------------------------
-- 予測と実績を突き合わせた、**精度を語るためのテーブル**です。
--
-- ⚠️ 「予測がどれくらい当たっているか」は、指標の選び方で結論が変わります。
--
--   `ape` (絶対パーセント誤差) は分かりやすい反面、**数量が少ない品目に不利**です。
--   月に 1 個しか出ない品目で 1 個ずれると誤差 100%、月に 1,000 個の品目で
--   10 個ずれても誤差 1% にしかなりません。
--   → ⭐ だから `abs_error`（個数のずれ）も一緒に持っています。
--     「率で見るか、個数で見るか」で優先順位は変わります。
CREATE OR REFRESH MATERIALIZED VIEW fct_forecast_accuracy
COMMENT 'Gold: 予測と実績を突き合わせた予実比較。誤差を率(ape)と個数(abs_error)の両方で持つ。'
CLUSTER BY (target_ym, item_code)
AS SELECT
  f.item_code,
  f.channel,
  f.target_ym,
  f.forecast_run_ym,
  f.model_name,
  f.p50 AS forecast_qty,
  a.qty AS actual_qty,
  abs(a.qty - f.p50) AS abs_error,
  -- 実績が 0 の月は率が定義できないので NULL にする（0 除算を避ける）
  CASE WHEN a.qty > 0 THEN abs(a.qty - f.p50) / a.qty END AS ape,
  -- 予測区間の中に実績が収まっていたか
  CASE WHEN a.qty BETWEEN f.lower_bound AND f.upper_bound THEN 1 ELSE 0 END AS within_interval
FROM fct_forecast_baseline f
INNER JOIN fct_shipments a
  ON f.item_code = a.item_code
 AND f.channel   = a.channel
 AND f.target_ym = a.ym;
