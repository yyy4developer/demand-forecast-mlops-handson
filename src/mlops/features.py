"""需要予測モデルの特徴量づくり。

学習でも推論でも**同じ関数**を使うのが要点です。
学習時と推論時で特徴量の作り方が少しでも違うと、
「学習では良い数字が出たのに本番だけ当たらない」という一番厄介な事故が起きます。
"""

from __future__ import annotations

import pandas as pd

# モデルに渡す特徴量の列（順番も含めて学習・推論で必ず一致させる）
FEATURE_COLS = [
    "month",
    "month_index",
    "lag_1",
    "lag_2",
    "lag_3",
    "lag_12",
    "roll_mean_3",
    "roll_mean_6",
    "roll_mean_12",
    "roll_std_6",
    "nonzero_ratio_12",
]

TARGET_COL = "qty"
SERIES_COLS = ["item_code", "channel"]
TIME_COL = "ym"


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """月次の実績から、時系列の特徴量を作る。

    Parameters
    ----------
    df:
        `item_code` / `channel` / `ym` / `qty` を持つ月次データ。
        系列ごとに月が連続していることを前提にする。

    Returns
    -------
    特徴量列を追加した DataFrame。
    ⚠️ 過去 12 か月を参照する特徴量があるため、各系列の先頭 12 か月は
    値が欠けます（学習時に落とします）。
    """
    out = df.sort_values(SERIES_COLS + [TIME_COL]).copy()
    out[TIME_COL] = pd.to_datetime(out[TIME_COL])

    # 季節性を拾うための「月」と、トレンドを拾うための「通し番号」
    out["month"] = out[TIME_COL].dt.month
    out["month_index"] = (
        out[TIME_COL].dt.year * 12 + out[TIME_COL].dt.month
        - (out[TIME_COL].dt.year.min() * 12)
    )

    g = out.groupby(SERIES_COLS, sort=False)[TARGET_COL]

    # 直近の実績（lag）。1〜3 か月前と、前年同月。
    for lag in (1, 2, 3, 12):
        out[f"lag_{lag}"] = g.shift(lag)

    # 移動平均・移動標準偏差。
    # ⚠️ shift(1) を挟むのが重要。当月の実績を特徴量に含めると
    #    「答えを見ながら予測する」ことになり、本番で通用しません。
    shifted = g.shift(1)
    for window in (3, 6, 12):
        out[f"roll_mean_{window}"] = shifted.groupby(
            [out[c] for c in SERIES_COLS]
        ).transform(lambda s, w=window: s.rolling(w, min_periods=1).mean())
    out["roll_std_6"] = shifted.groupby(
        [out[c] for c in SERIES_COLS]
    ).transform(lambda s: s.rolling(6, min_periods=1).std())

    # 直近 12 か月のうち需要が発生した月の割合（間欠需要の目印）
    out["nonzero_ratio_12"] = shifted.groupby(
        [out[c] for c in SERIES_COLS]
    ).transform(lambda s: s.gt(0).rolling(12, min_periods=1).mean())

    return out


def training_frame(df: pd.DataFrame) -> pd.DataFrame:
    """特徴量が揃っている行だけに絞った学習用データを返す。"""
    feat = build_features(df)
    return feat.dropna(subset=FEATURE_COLS).reset_index(drop=True)
