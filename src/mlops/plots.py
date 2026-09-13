"""ハンズオンで使うグラフ。

⭐ 数字の表だけだと「率と個数で結論が変わる」ような話が伝わりにくいため、
グラフを添えるための小さなヘルパーをまとめています。

⚠️ Databricks のノートブックでは、`plt.show()` の代わりに
そのまま図を返せば表示されます（`display(fig)` でも可）。
"""

from __future__ import annotations

import matplotlib
import matplotlib.pyplot as plt
import pandas as pd

# 日本語ラベルが豆腐（□）になるのを避けるため、ラベルは英数字に寄せる方針。
# ⚠️ サーバーレス環境には日本語フォントが入っていないため、
#    タイトルや凡例は英数字で書き、説明は Markdown セル側に書く。
matplotlib.rcParams["axes.unicode_minus"] = False
matplotlib.rcParams["figure.autolayout"] = True

# 色は使い回す（実績 / 予測 / ベースライン で意味を固定する）
COLOR_ACTUAL = "#1f2a44"
COLOR_FORECAST = "#2f6fdb"
COLOR_BASELINE = "#b8b8b8"
COLOR_INTERVAL = "#2f6fdb"


def plot_series_with_forecast(
    hist: pd.DataFrame,
    forecast: pd.DataFrame,
    title: str,
    *,
    date_col: str = "ym",
    actual_col: str = "qty",
    fc_date_col: str = "target_ym",
    fc_col: str = "p50",
    lower_col: str | None = "lower_bound",
    upper_col: str | None = "upper_bound",
):
    """1 系列の実績と予測を重ねて描く（予測区間つき）。"""
    fig, ax = plt.subplots(figsize=(11, 4))
    h = hist.sort_values(date_col)
    f = forecast.sort_values(fc_date_col)

    ax.plot(h[date_col], h[actual_col], color=COLOR_ACTUAL, lw=1.8, label="actual")
    ax.plot(f[fc_date_col], f[fc_col], color=COLOR_FORECAST, lw=1.8, ls="--", label="forecast")
    if lower_col and upper_col and lower_col in f and upper_col in f:
        ax.fill_between(
            f[fc_date_col], f[lower_col], f[upper_col],
            color=COLOR_INTERVAL, alpha=0.15, label="forecast interval",
        )

    ax.set_title(title)
    ax.set_ylabel("quantity")
    ax.grid(alpha=0.25)
    ax.legend(loc="upper left", frameon=False)
    return fig


def plot_grouped_bars(
    df: pd.DataFrame,
    group_col: str,
    value_cols: list[str],
    title: str,
    *,
    ylabel: str = "",
    colors: list[str] | None = None,
):
    """グループごとに複数の値を横並びの棒で比べる。"""
    fig, ax = plt.subplots(figsize=(10, 4))
    x = range(len(df))
    n = len(value_cols)
    width = 0.8 / n
    palette = colors or [COLOR_FORECAST, COLOR_BASELINE, COLOR_ACTUAL][:n]

    for i, col in enumerate(value_cols):
        ax.bar([xi + i * width for xi in x], df[col], width=width,
               label=col, color=palette[i % len(palette)])

    ax.set_xticks([xi + width * (n - 1) / 2 for xi in x])
    ax.set_xticklabels(df[group_col], rotation=20, ha="right")
    ax.set_title(title)
    ax.set_ylabel(ylabel)
    ax.grid(axis="y", alpha=0.25)
    ax.legend(frameon=False)
    return fig


def plot_pred_vs_actual(
    df: pd.DataFrame,
    actual_col: str = "actual_qty",
    pred_col: str = "forecast_qty",
    title: str = "predicted vs actual",
    *,
    log_scale: bool = True,
):
    """予測と実績の散布図。対角線に乗っていれば当たっている。

    ⭐ 数量の大小が桁で違うため、既定では両軸を対数にしています。
    """
    fig, ax = plt.subplots(figsize=(5.5, 5.5))
    ax.scatter(df[actual_col], df[pred_col], s=10, alpha=0.35, color=COLOR_FORECAST)

    lo = max(1e-1, min(df[actual_col].min(), df[pred_col].min()))
    hi = max(df[actual_col].max(), df[pred_col].max())
    ax.plot([lo, hi], [lo, hi], color=COLOR_ACTUAL, lw=1, ls="--", label="perfect")

    if log_scale:
        ax.set_xscale("log")
        ax.set_yscale("log")
    ax.set_xlabel("actual")
    ax.set_ylabel("predicted")
    ax.set_title(title)
    ax.grid(alpha=0.25)
    ax.legend(frameon=False)
    return fig


def plot_error_over_time(
    df: pd.DataFrame,
    date_col: str,
    series: dict[str, str],
    title: str,
    *,
    ylabel: str = "mean absolute error",
):
    """月ごとの誤差の推移を複数系列で比べる。

    `series` は {凡例に出す名前: 列名}。
    """
    fig, ax = plt.subplots(figsize=(11, 4))
    d = df.sort_values(date_col)
    palette = [COLOR_FORECAST, COLOR_BASELINE, COLOR_ACTUAL]
    for i, (label, col) in enumerate(series.items()):
        ax.plot(d[date_col], d[col], lw=1.8, label=label, color=palette[i % len(palette)])
    ax.set_title(title)
    ax.set_ylabel(ylabel)
    ax.grid(alpha=0.25)
    ax.legend(frameon=False)
    return fig
