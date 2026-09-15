"""サンプルデータ生成 — 架空の産業用機器メーカー「アクアテック工業」

`item_master_spec.yaml` の目標値 (需要分類 / ADI / CV2 / 月次平均数量) を再現する
月次時系列データを生成し、`data/` 配下に CSV として書き出す。

## 再現性について

このスクリプトは **誰がどの環境で実行しても同じ CSV を出力する**ように作られている:

1. 乱数は `numpy.random.default_rng(seed)` のみを使う (グローバル seed に依存しない)
2. seed は品目ごとに `base_seed + index * 1000 + attempt` で決まる
3. 目標値を満たすまで `attempt` を 0 から順に試し、**最初に通ったものを採用**する
   (ランダムな再試行ではないので、何度実行しても同じ attempt が選ばれる)
4. 生成後に ADI / CV2 / 平均数量を実測し、目標との相対誤差を検証する

そのため `git diff data/` に差分が出ないことが、再現性の検証そのものになる。

## 使い方

    uv run src/setup/generate_sample_data.py

生成物 (すべて `data/` 配下):

| ファイル | 内容 |
|---|---|
| `shipments_2020_2026_07.csv`  | 月次出荷実績 (CSV セット A — 事前に投入する分) |
| `shipments_2026_08.csv`       | 月次出荷実績 (CSV セット B — ハンズオン当日に投入する分) |
| `dim_item.csv`                | 品目マスタ |
| `dim_channel.csv`             | チャネル定義 |
| `fct_inventory.csv`           | 拠点別の月末在庫・安全在庫・欠品フラグ |
| `dim_lead_time.csv`           | 品目 × 拠点の標準リードタイム |
| `fct_forecast_baseline.csv`   | 前年同月ナイーブによるベースライン予測 |
| `_generation_report.csv`      | 目標値と実測値の対比 (透明性のため) |
"""

from __future__ import annotations

import csv
import math
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SPEC_PATH = Path(__file__).resolve().parent / "item_master_spec.yaml"
DATA_DIR = REPO_ROOT / "data"

# 目標値を満たす乱数系列を探す最大試行回数。attempt は 0 から順に試すので決定的。
MAX_ATTEMPTS = 200

# EXP チャネルで需要が発生する月の割合 (国内より間欠的)
EXP_OCCURRENCE_RATE = 0.55
# EXP チャネルで大口スパイクが立つ月の割合とその倍率レンジ
EXP_SPIKE_RATE = 0.08
EXP_SPIKE_RANGE = (2.0, 4.0)
# EXP シェアの上限 (1 ヶ月の出荷が全部海外になることは避ける)
EXP_SHARE_CAP = 0.85


# =============================================================================
# 月次カレンダー
# =============================================================================


def month_end(year: int, month: int) -> str:
    """その月の月末日を YYYY-MM-DD で返す。

    MMF の `freq="M"` は月末日でのアライメントを要求するため、
    本データの `ym` はすべて月末日で持つ。
    """
    if month == 12:
        next_year, next_month = year + 1, 1
    else:
        next_year, next_month = year, month + 1
    # 翌月 1 日の 1 日前 = 当月末
    import datetime as _dt

    return (_dt.date(next_year, next_month, 1) - _dt.timedelta(days=1)).isoformat()


def parse_ym(ym: str) -> tuple[int, int]:
    year, month = ym.split("-")[:2]
    return int(year), int(month)


def month_range(start_ym: str, end_ym: str) -> list[tuple[int, int]]:
    """(year, month) のリストを両端含みで返す。"""
    sy, sm = parse_ym(start_ym)
    ey, em = parse_ym(end_ym)
    out: list[tuple[int, int]] = []
    y, m = sy, sm
    while (y, m) <= (ey, em):
        out.append((y, m))
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return out


def shift_months(year: int, month: int, delta: int) -> tuple[int, int]:
    idx = year * 12 + (month - 1) + delta
    return idx // 12, idx % 12 + 1


# =============================================================================
# 需要系列の生成
# =============================================================================


@dataclass
class SeriesResult:
    """1 品目分の生成結果。"""

    total: np.ndarray  # 品目合計の月次数量 (active 期間のみ)
    dom: np.ndarray
    exp: np.ndarray
    attempt: int
    adi: float
    cv2: float
    mean_qty: float


def _lognormal_params(mean: float, cv2: float) -> tuple[float, float]:
    """平均 `mean` / 変動係数の2乗 `cv2` を持つ対数正規分布の (mu, sigma)。"""
    sigma = math.sqrt(math.log(1.0 + cv2))
    mu = math.log(mean) - sigma * sigma / 2.0
    return mu, sigma


def _measure(total: np.ndarray, last_n: int = 12) -> tuple[float, float, float]:
    """生成された系列から ADI / CV2 / 直近平均数量を実測する。"""
    n = len(total)
    nonzero = total[total > 0]
    adi = n / len(nonzero) if len(nonzero) else float("inf")
    if len(nonzero) >= 2 and nonzero.mean() > 0:
        cv2 = float((nonzero.std(ddof=0) / nonzero.mean()) ** 2)
    else:
        cv2 = 0.0
    mean_qty = float(total[-last_n:].mean()) if n >= last_n else float(total.mean())
    return adi, cv2, mean_qty


def _generate_once(item: dict, months: list[tuple[int, int]], seed: int) -> SeriesResult:
    """1 回の試行で品目の DOM / EXP 系列を作る。"""
    rng = np.random.default_rng(seed)
    n = len(months)

    target_adi = float(item["adi"])
    target_cv2 = float(item["cv2"])
    target_mean = float(item["mean_qty"])

    p_occur = min(1.0, 1.0 / target_adi)

    # --- 水準のパス (緩やかなトレンド) ---
    # 直近 12 ヶ月の平均が target_mean になるよう、系列末尾の水準を target_mean に合わせる
    trend = float(rng.uniform(-0.15, 0.30))
    t = np.arange(n) / max(n - 1, 1)
    level = target_mean * (1.0 + trend * (t - 1.0))
    level = np.clip(level, target_mean * 0.25, None)

    # --- 季節性 (指定された品目のみ) ---
    if item.get("seasonal"):
        phase = float(rng.uniform(0, 2 * math.pi))
        amp = float(rng.uniform(0.18, 0.28))
        season = 1.0 + amp * np.sin(2 * math.pi * (np.array([m for _, m in months]) - 1) / 12.0 + phase)
        level = level * season

    # --- 需要発生の有無 ---
    occur = np.ones(n, dtype=bool) if p_occur >= 1.0 else (rng.random(n) < p_occur)

    # --- 非ゼロ需要の数量 (対数正規) ---
    # 全期間平均 = p_occur * E[非ゼロ] = level  →  E[非ゼロ] = level / p_occur
    mean_nz = level / p_occur
    _, sigma = _lognormal_params(1.0, target_cv2)
    noise = rng.lognormal(mean=0.0, sigma=sigma, size=n)
    # lognormal(0, sigma) の平均は exp(sigma^2/2) なので割って平均 1 に正規化
    noise = noise / math.exp(sigma * sigma / 2.0)
    raw = mean_nz * noise * occur

    total = np.floor(raw + 0.5).astype(np.int64)
    total = np.clip(total, 0, None)

    # --- DOM / EXP への分割 ---
    # 合計を先に決めてから比率で割ることで、DOM + EXP == total を厳密に保つ
    if item.get("domestic_only"):
        exp = np.zeros(n, dtype=np.int64)
    else:
        exp_share = float(item["exp_share"])
        exp_occur = rng.random(n) < EXP_OCCURRENCE_RATE
        # 間欠化した分だけ 1 回あたりのシェアを上げて、期間全体のシェアを保つ
        w = np.where(exp_occur, exp_share / EXP_OCCURRENCE_RATE, 0.0)
        spike = rng.random(n) < EXP_SPIKE_RATE
        w = w * np.where(spike, rng.uniform(*EXP_SPIKE_RANGE, size=n), 1.0)
        w = np.clip(w, 0.0, EXP_SHARE_CAP)
        exp = np.floor(total * w + 0.5).astype(np.int64)
        exp = np.minimum(exp, total)

    dom = total - exp

    adi, cv2, mean_qty = _measure(total)
    return SeriesResult(total=total, dom=dom, exp=exp, attempt=-1, adi=adi, cv2=cv2, mean_qty=mean_qty)


def generate_series(item: dict, index: int, months: list[tuple[int, int]], spec: dict) -> SeriesResult:
    """目標値を満たす系列が得られるまで attempt を 0 から順に試す (決定的)。"""
    base_seed = int(spec["meta"]["base_seed"])
    tol = spec["meta"]["tolerance"]

    def within(actual: float, target: float, rel: float) -> bool:
        if target == 0:
            return actual == 0
        return abs(actual - target) / abs(target) <= rel

    best: SeriesResult | None = None
    best_score = float("inf")

    for attempt in range(MAX_ATTEMPTS):
        seed = base_seed + index * 1000 + attempt
        res = _generate_once(item, months, seed)
        ok = (
            within(res.adi, float(item["adi"]), tol["adi"])
            and within(res.cv2, float(item["cv2"]), tol["cv2"])
            and within(res.mean_qty, float(item["mean_qty"]), tol["mean_qty"])
        )
        if ok:
            res.attempt = attempt
            return res
        # 通らなかった場合の最良候補も覚えておく (エラーメッセージ用)
        score = (
            abs(res.adi - float(item["adi"])) / max(float(item["adi"]), 1e-9)
            + abs(res.cv2 - float(item["cv2"])) / max(float(item["cv2"]), 1e-9)
            + abs(res.mean_qty - float(item["mean_qty"])) / max(float(item["mean_qty"]), 1e-9)
        )
        if score < best_score:
            best_score, best = score, res

    assert best is not None
    raise RuntimeError(
        f"品目 {item['code']}: {MAX_ATTEMPTS} 回試しても目標値を満たせませんでした。\n"
        f"  目標 ADI={item['adi']} CV2={item['cv2']} mean={item['mean_qty']}\n"
        f"  最良 ADI={best.adi:.2f} CV2={best.cv2:.2f} mean={best.mean_qty:.1f}\n"
        f"  → item_master_spec.yaml の目標値または tolerance を見直してください。"
    )


# =============================================================================
# 各テーブルの組み立て
# =============================================================================


def build_shipments(spec: dict) -> tuple[list[dict], dict[str, SeriesResult], list[dict]]:
    """出荷実績・生成レポート・品目ごとの系列を作る。"""
    meta = spec["meta"]
    all_months = month_range(meta["start_ym"], meta["end_ym"])

    rows: list[dict] = []
    report: list[dict] = []
    series: dict[str, SeriesResult] = {}

    for index, item in enumerate(spec["items"]):
        code = item["code"]
        active_months = month_range(item["launch_ym"], meta["end_ym"])
        res = generate_series(item, index, active_months, spec)
        series[code] = res

        # 立ち上がり前の月はゼロ行として明示的に持たせる
        # (パイプラインで「データが無い」と「需要が無い」を区別できるようにする)
        active_start = active_months[0]
        for y, m in all_months:
            ym = month_end(y, m)
            if (y, m) < active_start:
                dom_qty = exp_qty = 0
            else:
                i = active_months.index((y, m))
                dom_qty, exp_qty = int(res.dom[i]), int(res.exp[i])
            rows.append({"item_code": code, "channel": "DOM", "ym": ym, "qty": dom_qty})
            if not item.get("domestic_only"):
                rows.append({"item_code": code, "channel": "EXP", "ym": ym, "qty": exp_qty})

        report.append(
            {
                "item_code": code,
                "demand_class": item["demand_class"],
                "target_adi": item["adi"],
                "actual_adi": round(res.adi, 3),
                "target_cv2": item["cv2"],
                "actual_cv2": round(res.cv2, 3),
                "target_mean_qty": item["mean_qty"],
                "actual_mean_qty": round(res.mean_qty, 2),
                "seed_attempt": res.attempt,
            }
        )

    return rows, series, report


def build_dim_item(spec: dict) -> list[dict]:
    return [
        {
            "item_code": it["code"],
            "item_name": it["name"],
            "item_category": it["category"],
            "item_type": it["item_type"],
            "unit_price": it["unit_price"],
            "demand_class": it["demand_class"],
            "adi": it["adi"],
            "cv2": it["cv2"],
            "is_domestic_only": "true" if it.get("domestic_only") else "false",
            "launch_ym": month_end(*parse_ym(it["launch_ym"])),
        }
        for it in spec["items"]
    ]


def build_dim_channel(spec: dict) -> list[dict]:
    return [
        {"channel_code": c["code"], "channel_name": c["name"], "description": c["description"]}
        for c in spec["channels"]
    ]


def _sites_for(item: dict, spec: dict) -> list[dict]:
    sites = spec["meta"]["sites"]
    if item.get("domestic_only"):
        return [s for s in sites if s["domestic"]]
    return sites


def build_lead_time(spec: dict) -> list[dict]:
    rng = np.random.default_rng(int(spec["meta"]["base_seed"]) + 777_000)
    ranges = spec["lead_time"]
    rows: list[dict] = []
    for it in spec["items"]:
        for site in _sites_for(it, spec):
            lo, hi = ranges[site["code"]]
            rows.append(
                {
                    "item_code": it["code"],
                    "site_code": site["code"],
                    "standard_lead_time_days": int(rng.integers(lo, hi + 1)),
                }
            )
    return rows


def build_inventory(spec: dict, series: dict[str, SeriesResult]) -> list[dict]:
    """拠点別の月末在庫・安全在庫・欠品フラグ。

    国内拠点は DOM 需要を 60:40 (東京:大阪) で分担、海外中継倉庫は EXP 需要を担当する。
    """
    meta = spec["meta"]
    all_months = month_range(meta["start_ym"], meta["end_ym"])
    inv_cfg = spec["inventory"]
    site_share = {"TOKYO_DC": 0.6, "OSAKA_DC": 0.4, "OVERSEAS_HUB": 1.0}

    rows: list[dict] = []
    for index, it in enumerate(spec["items"]):
        code = it["code"]
        res = series[code]
        active_months = month_range(it["launch_ym"], meta["end_ym"])
        rng = np.random.default_rng(int(meta["base_seed"]) + 555_000 + index)

        for site in _sites_for(it, spec):
            source = res.exp if site["code"] == "OVERSEAS_HUB" else res.dom
            share = site_share[site["code"]]
            for y, m in all_months:
                ym = month_end(y, m)
                if (y, m) < active_months[0]:
                    rows.append(
                        {
                            "item_code": code,
                            "site_code": site["code"],
                            "ym": ym,
                            "closing_qty": 0,
                            "safety_stock_qty": 0,
                            "stockout_flag": 0,
                        }
                    )
                    continue
                i = active_months.index((y, m))
                # 直近 12 ヶ月 (無ければ利用可能な範囲) の平均需要を基準にする
                window = source[max(0, i - 11) : i + 1]
                base = float(window.mean()) * share
                safety = int(np.floor(base * float(inv_cfg["safety_stock_months"]) + 0.5))
                noise = float(rng.normal(0.0, float(inv_cfg["closing_qty_noise_sd"])))
                closing = int(np.floor(max(0.0, safety * (1.0 + noise)) + 0.5))
                if rng.random() < float(inv_cfg["stockout_rate"]):
                    closing = 0
                rows.append(
                    {
                        "item_code": code,
                        "site_code": site["code"],
                        "ym": ym,
                        "closing_qty": closing,
                        "safety_stock_qty": safety,
                        "stockout_flag": 1 if closing == 0 and safety > 0 else 0,
                    }
                )
    return rows


def build_forecast_baseline(spec: dict, shipments: list[dict]) -> list[dict]:
    """前年同月ナイーブによるベースライン予測。

    ハンズオンでは Genie / ダッシュボードのパートが機械学習のパートより先に来るため、
    予測誤差を見られる状態を最初から用意しておく。
    さらに「自作モデルはナイーブに勝てているか」という比較軸にもなる。

    - 履歴ブロック : 2021-01 〜 2026-08 を対象に「先月末時点で作った予測」として持つ
                     → 実績と突き合わせて予測誤差率を計算できる
    - 将来ブロック : 2026-09 〜 2028-02 (18 ヶ月) を 2026-08 末時点の予測として持つ
    """
    meta = spec["meta"]
    actual = {(r["item_code"], r["channel"], r["ym"]): r["qty"] for r in shipments}
    pairs = sorted({(r["item_code"], r["channel"]) for r in shipments})

    start_y, start_m = parse_ym(meta["start_ym"])
    end_y, end_m = parse_ym(meta["end_ym"])

    def lookup(item_code: str, channel: str, y: int, m: int) -> int | None:
        return actual.get((item_code, channel, month_end(y, m)))

    def naive(item_code: str, channel: str, y: int, m: int) -> int | None:
        """前年同月 → 無ければ 2 年前同月。"""
        for back in (12, 24):
            py, pm = shift_months(y, m, -back)
            v = lookup(item_code, channel, py, pm)
            if v is not None:
                return v
        return None

    rows: list[dict] = []

    # --- 履歴ブロック (予実比較用) ---
    hist_start = shift_months(start_y, start_m, 12)  # 前年同月が使える最初の月
    for y, m in month_range(f"{hist_start[0]:04d}-{hist_start[1]:02d}", meta["end_ym"]):
        run_y, run_m = shift_months(y, m, -1)
        for item_code, channel in pairs:
            p50 = naive(item_code, channel, y, m)
            if p50 is None:
                continue
            rows.append(
                {
                    "item_code": item_code,
                    "channel": channel,
                    "target_ym": month_end(y, m),
                    "forecast_run_ym": month_end(run_y, run_m),
                    "model_name": "baseline_seasonal_naive",
                    "p50": p50,
                    "lower_bound": int(np.floor(p50 * 0.6 + 0.5)),
                    "upper_bound": int(np.floor(p50 * 1.5 + 0.5)),
                }
            )

    # --- 将来ブロック (18 ヶ月先予測) ---
    fut_start = shift_months(end_y, end_m, 1)
    fut_end = shift_months(end_y, end_m, 18)
    run_ym = month_end(end_y, end_m)
    for y, m in month_range(f"{fut_start[0]:04d}-{fut_start[1]:02d}", f"{fut_end[0]:04d}-{fut_end[1]:02d}"):
        for item_code, channel in pairs:
            p50 = naive(item_code, channel, y, m)
            if p50 is None:
                continue
            rows.append(
                {
                    "item_code": item_code,
                    "channel": channel,
                    "target_ym": month_end(y, m),
                    "forecast_run_ym": run_ym,
                    "model_name": "baseline_seasonal_naive",
                    "p50": p50,
                    "lower_bound": int(np.floor(p50 * 0.6 + 0.5)),
                    "upper_bound": int(np.floor(p50 * 1.5 + 0.5)),
                }
            )

    return rows


# =============================================================================
# 書き出し
# =============================================================================


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        raise ValueError(f"{path.name}: 書き出す行がありません")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(f"  {path.relative_to(REPO_ROOT)}: {len(rows):,} 行")



def build_own_data_sample(spec: dict) -> list[dict]:
    """⭐ 自由時間 (`99_your_own_data`) の練習用 CSV。

    ⭐ **データを持ってきていない参加者**でも自由時間を体験できるようにするためのもの。
    ⚠️ 見本データとは別物で、パイプラインには一切取り込みません。

    ⭐ わざと「実データっぽい形」にしてあります（`99` の説明どおりに詰まるように）:

    | 特徴 | 狙い |
    |---|---|
    | 列名が日本語 (`商品コード` / `年月` / `数量`) | ⭐ バッククォートが必要になる |
    | `年月` が `2024年1月` 形式 | ⭐ 日付として素直に解釈できない |
    | `数量` が桁区切りつき (`1,234`) | ⭐ 数値なのに文字列として読まれる |
    | 出ない月がある品目つき | ⭐ 間欠需要の扱いが問われる |
    | 30 か月 × 4 品目 | ⭐ 予測モデルが作れる長さ (24 か月以上) |

    ⭐ Genie Code がこれをどう捌くかを見るのが `99` の狙いです。
    """
    rng = np.random.default_rng(spec["meta"]["base_seed"] + 777)
    rows: list[dict] = []
    # 性質を作り分ける: 安定 / 成長 / 振れる / 出ない月がある
    # (品目, 基準数量, 変動係数, 月次成長率, 出荷が起きる確率)
    items = [
        # ⭐ 4 桁にして「1,234」形式の桁区切りを発生させる（カンマ除去処理を通すため）
        ("A-100", 2400, 0.10, 0.00, 1.0),   # 安定・大口
        ("A-200", 900, 0.15, 0.02, 1.0),    # 成長トレンドあり
        ("B-310", 60, 0.55, 0.00, 1.0),     # 数量が振れる
        ("C-900", 25, 0.40, 0.00, 0.6),     # ⭐ 出ない月がある（間欠需要）
    ]
    for item, base, cv, growth, occur in items:
        for i in range(30):
            year = 2024 + (i // 12)
            month = (i % 12) + 1
            if rng.random() > occur:
                qty = 0
            else:
                level = base * (1 + growth) ** i
                # 12 か月周期の季節性を少し入れる
                season = 1 + 0.18 * np.sin(2 * np.pi * (month - 1) / 12)
                qty = max(0, int(round(rng.normal(level * season, level * cv))))
            rows.append({
                "商品コード": item,
                "年月": f"{year}年{month}月",
                # ⚠️ わざと桁区切りの文字列にする
                "数量": f"{qty:,}",
            })
    return rows

def main() -> int:
    spec = yaml.safe_load(SPEC_PATH.read_text(encoding="utf-8"))
    meta = spec["meta"]
    holdout_ym = month_end(*parse_ym(meta["holdout_ym"]))

    print("=" * 70)
    print(f"  サンプルデータ生成 — {meta['company']}")
    print(f"  期間 {meta['start_ym']} 〜 {meta['end_ym']} / 品目 {len(spec['items'])} 件")
    print("=" * 70)

    shipments, series, report = build_shipments(spec)

    # CSV セット A (事前投入分) と セット B (当日投入分) に分ける
    set_a = [r for r in shipments if r["ym"] < holdout_ym]
    set_b = [r for r in shipments if r["ym"] == holdout_ym]

    print("\n[出荷実績]")
    write_csv(DATA_DIR / "shipments_2020_2026_07.csv", set_a)
    write_csv(DATA_DIR / "shipments_2026_08.csv", set_b)

    print("\n[自由時間の練習用]")
    write_csv(DATA_DIR / "sample_own_data.csv", build_own_data_sample(spec))

    print("\n[マスタ]")
    write_csv(DATA_DIR / "dim_item.csv", build_dim_item(spec))
    write_csv(DATA_DIR / "dim_channel.csv", build_dim_channel(spec))
    write_csv(DATA_DIR / "dim_lead_time.csv", build_lead_time(spec))

    print("\n[在庫]")
    write_csv(DATA_DIR / "fct_inventory.csv", build_inventory(spec, series))

    print("\n[ベースライン予測]")
    write_csv(DATA_DIR / "fct_forecast_baseline.csv", build_forecast_baseline(spec, shipments))

    print("\n[生成レポート — 目標値 vs 実測値]")
    write_csv(DATA_DIR / "_generation_report.csv", report)
    print()
    header = f"  {'品目':<8} {'分類':<14} {'ADI':>12} {'CV2':>14} {'平均数量':>16} {'試行':>5}"
    print(header)
    print("  " + "-" * (len(header) - 2))
    for r in report:
        print(
            f"  {r['item_code']:<8} {r['demand_class']:<14}"
            f" {r['target_adi']:>5.2f}→{r['actual_adi']:>5.2f}"
            f" {r['target_cv2']:>6.2f}→{r['actual_cv2']:>6.2f}"
            f" {r['target_mean_qty']:>7.1f}→{r['actual_mean_qty']:>7.1f}"
            f" {r['seed_attempt']:>5}"
        )

    print("\n✅ すべての品目が目標値の許容範囲内で生成されました")
    print("   (許容誤差: "
          f"ADI ±{meta['tolerance']['adi']:.0%} / "
          f"CV2 ±{meta['tolerance']['cv2']:.0%} / "
          f"平均数量 ±{meta['tolerance']['mean_qty']:.0%})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
