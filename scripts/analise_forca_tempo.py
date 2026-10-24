#!/usr/bin/env python3
"""3 Pro: exploratory second-level buyer-pressure response study.

Downloads public Binance Spot 1-second klines for a short research window,
then measures aggressor-volume imbalance, response horizons and within-minute
high/low timing. This is research only: it emits no trading orders.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd

EXPECTED_1M_SHA256 = "604835C55D98319CF6F26516040F6F285E02152B6EE984238C0D3359C2DBDE41"
BASE_URLS = [
    "https://data-api.binance.vision/api/v3/klines",
    "https://api.binance.com/api/v3/klines",
]
KLINE_COLUMNS = [
    "open_time_ms", "open", "high", "low", "close", "volume",
    "close_time_ms", "quote_volume", "trades",
    "taker_buy_base_volume", "taker_buy_quote_volume", "ignore",
]
HORIZONS_SECONDS = [1, 2, 3, 5, 10, 15, 30, 45, 60]
IMBALANCE_THRESHOLDS = [0.20, 0.35, 0.50]
VOLUME_RATIO_MIN = 1.5
EVENT_COOLDOWN_SECONDS = 60
ROUND_TRIP_COST_BPS_DEFAULT = 30.0  # 2 * (10 bps fee + 5 bps slippage)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def utc_now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def fetch_page(params: dict[str, Any], timeout: int = 20) -> list[list[Any]]:
    last_error: Exception | None = None
    for base_url in BASE_URLS:
        url = base_url + "?" + urlencode(params)
        for attempt in range(5):
            try:
                request = Request(url, headers={"User-Agent": "3Pro-Research/1.0"})
                with urlopen(request, timeout=timeout) as response:
                    payload = response.read().decode("utf-8")
                parsed = json.loads(payload)
                if not isinstance(parsed, list):
                    raise RuntimeError(f"Resposta inesperada da API: {str(parsed)[:300]}")
                return parsed
            except HTTPError as exc:
                last_error = exc
                # Try a different public base URL immediately for endpoint/interval errors.
                if exc.code in (400, 404):
                    break
                if exc.code in (418, 429):
                    delay = min(30.0, float(exc.headers.get("Retry-After", 2 ** attempt)))
                else:
                    delay = min(8.0, 0.5 * (2 ** attempt))
                time.sleep(delay)
            except (URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
                last_error = exc
                time.sleep(min(8.0, 0.5 * (2 ** attempt)))
            except RuntimeError as exc:
                last_error = exc
                break
    raise RuntimeError(f"Falha ao consultar candles 1s em endpoints publicos: {last_error}")


def download_1s_klines(symbol: str, days: int) -> tuple[pd.DataFrame, dict[str, Any]]:
    now_ms = int(time.time() * 1000)
    # Most recent candle whose full one-second interval has ended.
    end_ms = (now_ms // 1000) * 1000 - 1000
    start_ms = end_ms - days * 86_400_000 + 1000
    cursor = start_ms
    rows: list[list[Any]] = []
    page = 0
    first_error: str | None = None

    while cursor <= end_ms:
        params = {
            "symbol": symbol.upper(),
            "interval": "1s",
            "startTime": cursor,
            "endTime": end_ms,
            "limit": 1000,
        }
        try:
            batch = fetch_page(params)
        except Exception as exc:
            first_error = str(exc)
            raise RuntimeError(
                f"Download interrompido em {cursor}; nenhum relatorio final foi declarado completo. {exc}"
            ) from exc
        if not batch:
            break
        clean_batch = [r for r in batch if isinstance(r, list) and len(r) >= 12]
        if not clean_batch:
            raise RuntimeError("A API devolveu linhas kline com formato inesperado.")
        rows.extend(clean_batch)
        last_open = int(clean_batch[-1][0])
        if last_open < cursor:
            raise RuntimeError("A pagina da API nao avancou no tempo; download interrompido.")
        cursor = last_open + 1000
        page += 1
        if page == 1 or page % 25 == 0:
            print(f"Paginas 1s: {page} | linhas recebidas: {len(rows):,}")
        time.sleep(0.04)
        if last_open >= end_ms:
            break
        # Even a short page is not assumed to mean end-of-data: seconds without
        # reported trades may be omitted by the endpoint.

    if not rows:
        raise RuntimeError("A API nao retornou candles 1s para o periodo solicitado.")

    frame = pd.DataFrame(rows, columns=KLINE_COLUMNS)
    frame["open_time_ms"] = pd.to_numeric(frame["open_time_ms"], errors="raise").astype("int64")
    duplicated = frame[frame.duplicated(subset=["open_time_ms"], keep=False)]
    duplicate_count = 0
    if not duplicated.empty:
        compare_cols = [c for c in KLINE_COLUMNS if c != "ignore"]
        for open_time, group in duplicated.groupby("open_time_ms", sort=False):
            if len(group[compare_cols].drop_duplicates()) > 1:
                raise RuntimeError(f"Candles duplicados conflitantes no open_time_ms={open_time}; download rejeitado.")
        duplicate_count = int(frame.duplicated(subset=["open_time_ms"], keep="first").sum())
        frame = frame.drop_duplicates(subset=["open_time_ms"], keep="first")
    frame = frame.sort_values("open_time_ms")
    numeric = [
        "open", "high", "low", "close", "volume", "quote_volume", "trades",
        "taker_buy_base_volume", "taker_buy_quote_volume", "close_time_ms",
    ]
    for col in numeric:
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    if frame[numeric].isna().any().any():
        raise RuntimeError("Dados 1s possuem campos numericos ausentes ou invalidos.")
    if not np.isfinite(frame[numeric].to_numpy(dtype=float)).all():
        raise RuntimeError("Dados 1s possuem valores nao finitos.")
    if (frame[["open", "high", "low", "close"]] <= 0).any().any():
        raise RuntimeError("Dados 1s possuem precos nao positivos.")
    if (frame["quote_volume"] < 0).any() or (frame["taker_buy_quote_volume"] < 0).any():
        raise RuntimeError("Dados 1s possuem volume negativo.")
    if (frame["taker_buy_quote_volume"] - frame["quote_volume"] > 1e-6).any():
        raise RuntimeError("Volume comprador agressor excede o volume financeiro total.")
    if (frame["high"] < frame[["open", "close", "low"]].max(axis=1)).any():
        raise RuntimeError("Candles 1s possuem maximas inconsistentes.")
    if (frame["low"] > frame[["open", "close", "high"]].min(axis=1)).any():
        raise RuntimeError("Candles 1s possuem minimas inconsistentes.")

    frame = frame.reset_index(drop=True)
    actual_first = int(frame["open_time_ms"].iloc[0])
    actual_last = int(frame["open_time_ms"].iloc[-1])
    expected_grid = np.arange(actual_first, actual_last + 1000, 1000, dtype=np.int64)
    observed_count = len(frame)
    indexed = frame.set_index("open_time_ms").reindex(expected_grid)
    observed = indexed["close"].notna()
    synthetic_count = int((~observed).sum())
    indexed["observed_kline"] = observed.to_numpy()

    # Explicit placeholder for a second with no returned kline: carry the last
    # observed close forward and set all activity to zero. Count/report these
    # placeholders; they are NOT actual traded candles.
    previous_close = indexed["close"].ffill()
    for col in ["open", "high", "low", "close"]:
        indexed[col] = indexed[col].fillna(previous_close)
    for col in ["volume", "quote_volume", "trades", "taker_buy_base_volume", "taker_buy_quote_volume"]:
        indexed[col] = indexed[col].fillna(0.0)
    indexed["close_time_ms"] = indexed.index + 999
    indexed["ignore"] = "0"
    indexed.index.name = "open_time_ms"
    indexed = indexed.reset_index()
    indexed["timestamp"] = pd.to_datetime(indexed["open_time_ms"], unit="ms", utc=True)
    indexed["close_time"] = pd.to_datetime(indexed["close_time_ms"], unit="ms", utc=True)

    delta = np.diff(indexed["open_time_ms"].to_numpy(dtype=np.int64))
    audit = {
        "symbol": symbol.upper(),
        "interval": "1s",
        "days_requested": days,
        "requested_start_utc": datetime.fromtimestamp(start_ms / 1000, timezone.utc).isoformat(),
        "requested_last_closed_open_utc": datetime.fromtimestamp(end_ms / 1000, timezone.utc).isoformat(),
        "first_observed_open_utc": indexed["timestamp"].iloc[0].isoformat(),
        "last_grid_open_utc": indexed["timestamp"].iloc[-1].isoformat(),
        "observed_kline_rows": observed_count,
        "grid_seconds": len(indexed),
        "seconds_without_returned_kline_filled_as_zero_activity": synthetic_count,
        "identical_duplicate_rows_removed": duplicate_count,
        "irregular_grid_steps_after_reindex": int(np.sum(delta != 1000)),
        "first_error": first_error,
    }
    return indexed, audit


def _imbalance(buy_quote: float, total_quote: float) -> float:
    if not np.isfinite(total_quote) or total_quote <= 0:
        return float("nan")
    return float((2.0 * buy_quote - total_quote) / total_quote)


def prepare_features(frame: pd.DataFrame) -> pd.DataFrame:
    df = frame.copy()
    total = df["quote_volume"].to_numpy(dtype=float)
    buy = df["taker_buy_quote_volume"].to_numpy(dtype=float)
    for window in (5, 10, 30):
        total_roll = pd.Series(total).rolling(window, min_periods=window).sum()
        buy_roll = pd.Series(buy).rolling(window, min_periods=window).sum()
        denominator = total_roll.replace(0.0, np.nan)
        df[f"imbalance_{window}s"] = (2.0 * buy_roll - total_roll) / denominator
        df[f"quote_volume_{window}s"] = total_roll

    # Compare last 5-second notional with a trailing median based only on older seconds.
    baseline_per_second = pd.Series(total).shift(5).rolling(300, min_periods=180).median()
    denom = (baseline_per_second * 5.0).replace(0.0, np.nan)
    df["relative_activity_5s"] = df["quote_volume_5s"] / denom
    return df


def select_events(df: pd.DataFrame, threshold: float, cooldown: int = EVENT_COOLDOWN_SECONDS) -> list[int]:
    imbalance = df["imbalance_5s"].to_numpy(dtype=float)
    rel_activity = df["relative_activity_5s"].to_numpy(dtype=float)
    candidate = np.where(
        np.isfinite(imbalance) & np.isfinite(rel_activity) &
        (rel_activity >= VOLUME_RATIO_MIN) & (np.abs(imbalance) >= threshold)
    )[0]
    chosen: list[int] = []
    last_index = -cooldown - 1
    for idx in candidate:
        if idx - last_index < cooldown:
            continue
        chosen.append(int(idx))
        last_index = int(idx)
    return chosen


def hourly_bootstrap_ci(values: np.ndarray, hours: np.ndarray, seed: int = 20261021, reps: int = 1000) -> tuple[float, float]:
    valid = np.isfinite(values)
    values = values[valid]
    hours = hours[valid]
    if len(values) < 5:
        return float("nan"), float("nan")
    unique_hours = np.unique(hours)
    if len(unique_hours) < 3:
        return float("nan"), float("nan")
    sums = np.array([values[hours == h].sum() for h in unique_hours], dtype=float)
    counts = np.array([(hours == h).sum() for h in unique_hours], dtype=float)
    rng = np.random.default_rng(seed)
    means = np.empty(reps, dtype=float)
    for r in range(reps):
        sampled = rng.integers(0, len(unique_hours), size=len(unique_hours))
        denominator = counts[sampled].sum()
        means[r] = sums[sampled].sum() / denominator if denominator else np.nan
    means = means[np.isfinite(means)]
    if not len(means):
        return float("nan"), float("nan")
    low, high = np.quantile(means, [0.025, 0.975])
    return float(low), float(high)


def analyze_events(df: pd.DataFrame, fee_bps: float, slippage_bps: float) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    all_event_rows: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []
    total_round_trip_cost = 2.0 * (fee_bps + slippage_bps)
    close = df["close"].to_numpy(dtype=float)
    open_ = df["open"].to_numpy(dtype=float)
    ts = df["timestamp"]
    observed = df["observed_kline"].to_numpy(dtype=bool)
    base_stats: dict[str, Any] = {}

    for threshold in IMBALANCE_THRESHOLDS:
        idxs = select_events(df, threshold)
        events_for_threshold: list[dict[str, Any]] = []
        for idx in idxs:
            side_value = float(df.at[idx, "imbalance_5s"])
            side = 1 if side_value > 0 else -1
            event: dict[str, Any] = {
                "threshold": threshold,
                "timestamp_utc": ts.iloc[idx].isoformat(),
                "side": "BUY_PRESSURE" if side > 0 else "SELL_PRESSURE",
                "side_numeric": side,
                "imbalance_5s": side_value,
                "imbalance_10s": float(df.at[idx, "imbalance_10s"]) if np.isfinite(df.at[idx, "imbalance_10s"]) else np.nan,
                "imbalance_30s": float(df.at[idx, "imbalance_30s"]) if np.isfinite(df.at[idx, "imbalance_30s"]) else np.nan,
                "relative_activity_5s": float(df.at[idx, "relative_activity_5s"]),
                "net_aggressive_quote_flow_5s": float(2 * df.at[idx, "taker_buy_quote_volume"] - df.at[idx, "quote_volume"]),
                "kline_observed_at_signal": bool(observed[idx]),
            }
            # Exit outcomes start at the next second's open; no fill at signal candle close.
            for horizon in HORIZONS_SECONDS:
                exit_idx = idx + horizon
                entry_idx = idx + 1
                if exit_idx >= len(df) or entry_idx >= len(df):
                    event[f"gross_bps_{horizon}s"] = np.nan
                    event[f"net_bps_{horizon}s"] = np.nan
                    event[f"directional_response_bps_{horizon}s"] = np.nan
                    continue
                if not (open_[entry_idx] > 0 and close[exit_idx] > 0 and close[idx] > 0):
                    event[f"gross_bps_{horizon}s"] = np.nan
                    event[f"net_bps_{horizon}s"] = np.nan
                    event[f"directional_response_bps_{horizon}s"] = np.nan
                    continue
                gross = side * 10_000.0 * math.log(close[exit_idx] / open_[entry_idx])
                response = side * 10_000.0 * math.log(close[exit_idx] / close[idx])
                event[f"gross_bps_{horizon}s"] = gross
                event[f"net_bps_{horizon}s"] = gross - total_round_trip_cost
                event[f"directional_response_bps_{horizon}s"] = response
            events_for_threshold.append(event)
            all_event_rows.append(event)

        base_stats[f"threshold_{threshold:.2f}"] = {"events": len(events_for_threshold)}
        for horizon in HORIZONS_SECONDS:
            col = f"gross_bps_{horizon}s"
            values = np.asarray([e[col] for e in events_for_threshold], dtype=float)
            values = values[np.isfinite(values)]
            net_values = values - total_round_trip_cost
            if len(values):
                event_hours = np.asarray([
                    pd.Timestamp(e["timestamp_utc"]).floor("h").isoformat()
                    for e in events_for_threshold if np.isfinite(e[col])
                ], dtype=object)
                ci_low, ci_high = hourly_bootstrap_ci(values, event_hours)
                summary_rows.append({
                    "threshold_abs_imbalance_5s": threshold,
                    "min_relative_activity_5s": VOLUME_RATIO_MIN,
                    "cooldown_seconds": EVENT_COOLDOWN_SECONDS,
                    "horizon_seconds": horizon,
                    "events": int(len(values)),
                    "mean_gross_bps": float(np.mean(values)),
                    "median_gross_bps": float(np.median(values)),
                    "pct_gross_directionally_positive": float(100.0 * np.mean(values > 0)),
                    "mean_net_bps_after_assumed_round_trip_cost": float(np.mean(net_values)),
                    "pct_net_positive_after_assumed_cost": float(100.0 * np.mean(net_values > 0)),
                    "hour_cluster_bootstrap_95ci_mean_gross_low_bps": ci_low,
                    "hour_cluster_bootstrap_95ci_mean_gross_high_bps": ci_high,
                    "round_trip_cost_bps_assumed": total_round_trip_cost,
                })
            else:
                summary_rows.append({
                    "threshold_abs_imbalance_5s": threshold,
                    "min_relative_activity_5s": VOLUME_RATIO_MIN,
                    "cooldown_seconds": EVENT_COOLDOWN_SECONDS,
                    "horizon_seconds": horizon,
                    "events": 0,
                    "mean_gross_bps": np.nan,
                    "median_gross_bps": np.nan,
                    "pct_gross_directionally_positive": np.nan,
                    "mean_net_bps_after_assumed_round_trip_cost": np.nan,
                    "pct_net_positive_after_assumed_cost": np.nan,
                    "hour_cluster_bootstrap_95ci_mean_gross_low_bps": np.nan,
                    "hour_cluster_bootstrap_95ci_mean_gross_high_bps": np.nan,
                    "round_trip_cost_bps_assumed": total_round_trip_cost,
                })

    return pd.DataFrame(all_event_rows), pd.DataFrame(summary_rows), base_stats


def _phase(second: int) -> str:
    if second < 20:
        return "EARLY_00_19S"
    if second < 40:
        return "MID_20_39S"
    return "LATE_40_59S"


def analyze_minute_extrema(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    data = df.copy()
    data["minute"] = data["timestamp"].dt.floor("min")
    minute_rows: list[dict[str, Any]] = []
    for minute, g in data.groupby("minute", sort=True):
        if len(g) != 60:
            continue
        g = g.reset_index(drop=True)
        high_pos = int(g["high"].to_numpy().argmax())
        low_pos = int(g["low"].to_numpy().argmin())
        high_price = float(g["high"].max())
        low_price = float(g["low"].min())
        close_price = float(g["close"].iloc[-1])
        open_price = float(g["open"].iloc[0])
        quote = g["quote_volume"].to_numpy(dtype=float)
        buy_quote = g["taker_buy_quote_volume"].to_numpy(dtype=float)

        def imbalance_slice(mask: np.ndarray) -> float:
            total = float(quote[mask].sum())
            buy = float(buy_quote[mask].sum())
            return _imbalance(buy, total)

        low_after_mask = np.arange(60) > low_pos
        high_after_mask = np.arange(60) > high_pos
        post_low_buy = imbalance_slice(low_after_mask)
        post_high_sell = -imbalance_slice(high_after_mask)
        candle_range = high_price - low_price
        close_location = (close_price - low_price) / candle_range if candle_range > 0 else np.nan
        minute_rows.append({
            "minute_utc": pd.Timestamp(minute).isoformat(),
            "open": open_price,
            "high": high_price,
            "low": low_price,
            "close": close_price,
            "high_second": high_pos,
            "low_second": low_pos,
            "high_phase": _phase(high_pos),
            "low_phase": _phase(low_pos),
            "range_bps": 10_000.0 * math.log(high_price / low_price) if low_price > 0 else np.nan,
            "close_location_0_bottom_1_top": close_location,
            "buy_imbalance_after_low_to_close": post_low_buy,
            "sell_imbalance_after_high_to_close": post_high_sell,
            "return_low_to_close_bps": 10_000.0 * math.log(close_price / low_price) if low_price > 0 else np.nan,
            "return_high_to_close_bps": 10_000.0 * math.log(close_price / high_price) if high_price > 0 else np.nan,
            "next_minute_close_return_bps": np.nan,
        })
    minute_df = pd.DataFrame(minute_rows)
    if minute_df.empty:
        return minute_df, pd.DataFrame()
    next_returns = 10_000.0 * np.log(minute_df["close"].shift(-1) / minute_df["close"])
    minute_df["next_minute_close_return_bps"] = next_returns

    summary: list[dict[str, Any]] = []
    for extremum, phase_col, flow_col, retreat_col in [
        ("BOTTOM", "low_phase", "buy_imbalance_after_low_to_close", "return_low_to_close_bps"),
        ("TOP", "high_phase", "sell_imbalance_after_high_to_close", "return_high_to_close_bps"),
    ]:
        for phase in ("EARLY_00_19S", "MID_20_39S", "LATE_40_59S"):
            g = minute_df[minute_df[phase_col] == phase]
            f = g[flow_col].dropna()
            r = g["next_minute_close_return_bps"].dropna()
            summary.append({
                "extremum": extremum,
                "phase": phase,
                "minutes": int(len(g)),
                "mean_directional_flow_after_extremum": float(f.mean()) if len(f) else np.nan,
                "pct_flow_aligned_after_extremum": float(100.0 * (f > 0).mean()) if len(f) else np.nan,
                "mean_extremum_to_close_bps": float(g[retreat_col].mean()) if len(g) else np.nan,
                "mean_close_location_0_bottom_1_top": float(g["close_location_0_bottom_1_top"].mean()) if len(g) else np.nan,
                "mean_next_minute_close_return_bps": float(r.mean()) if len(r) else np.nan,
                "pct_next_minute_positive": float(100.0 * (r > 0).mean()) if len(r) else np.nan,
            })
    return minute_df, pd.DataFrame(summary)


def run_self_test() -> None:
    # Deterministic synthetic 1-second data with alternating buy/sell aggression.
    n = 1200
    t0 = 1_800_000_000_000
    close = 100.0 * np.exp(np.cumsum(np.full(n, 0.00001)))
    open_ = np.r_[close[0], close[:-1]]
    total_quote = np.full(n, 1000.0)
    buy_quote = np.full(n, 500.0)
    buy_quote[300:340] = 900.0
    buy_quote[700:740] = 100.0
    synthetic = pd.DataFrame({
        "open_time_ms": t0 + np.arange(n, dtype=np.int64) * 1000,
        "timestamp": pd.to_datetime(t0 + np.arange(n, dtype=np.int64) * 1000, unit="ms", utc=True),
        "open": open_, "high": np.maximum(open_, close) * 1.00001,
        "low": np.minimum(open_, close) * 0.99999, "close": close,
        "volume": total_quote / close, "quote_volume": total_quote,
        "trades": np.full(n, 10), "taker_buy_base_volume": buy_quote / close,
        "taker_buy_quote_volume": buy_quote, "close_time_ms": t0 + np.arange(n, dtype=np.int64) * 1000 + 999,
        "close_time": pd.to_datetime(t0 + np.arange(n, dtype=np.int64) * 1000 + 999, unit="ms", utc=True),
        "observed_kline": np.ones(n, dtype=bool),
    })
    f = prepare_features(synthetic)
    assert f["imbalance_5s"].iloc[320] > 0.7
    assert f["imbalance_5s"].iloc[720] < -0.7
    events, response, stats = analyze_events(f, 10.0, 5.0)
    assert not response.empty and set(response["horizon_seconds"]).issubset(set(HORIZONS_SECONDS))
    minute, pattern = analyze_minute_extrema(f)
    assert isinstance(minute, pd.DataFrame) and isinstance(pattern, pd.DataFrame)
    print("SELF-TEST PASSED: 1s aggressor imbalance, horizons, costs and top/bottom study; no network, no file writes.")


def main() -> int:
    parser = argparse.ArgumentParser(description="3 Pro Forca x Tempo: research on BTCUSDT 1-second bars")
    parser.add_argument("--root", type=Path, help="Root da pasta 3 Pro")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--days", type=int, default=7, help="Janela de candles 1s (1 a 14 dias; padrao 7)")
    parser.add_argument("--fee-bps", type=float, default=10.0, help="Taxa assumida por lado em bps")
    parser.add_argument("--slippage-bps", type=float, default=5.0, help="Slippage assumido por lado em bps")
    parser.add_argument("--self-test", action="store_true", help="Testes sinteticos locais sem rede nem escrita")
    args = parser.parse_args()

    if args.self_test:
        run_self_test()
        return 0
    if args.root is None:
        parser.error("informe --root com a pasta 3 Pro")
    if not 1 <= args.days <= 14:
        parser.error("--days precisa estar entre 1 e 14 para limitar tamanho e chamadas")
    if not np.isfinite([args.fee_bps, args.slippage_bps]).all() or args.fee_bps < 0 or args.slippage_bps < 0:
        parser.error("taxas e slippage precisam ser finitos e nao negativos")

    root = args.root.resolve()
    one_min_csv = root / "data" / "raw" / f"{args.symbol.upper()}_1m.csv"
    if not one_min_csv.is_file():
        raise SystemExit(f"CSV 1m nao encontrado: {one_min_csv}")
    if args.symbol.upper() == "BTCUSDT":
        current_hash = sha256_file(one_min_csv)
        if current_hash != EXPECTED_1M_SHA256:
            raise SystemExit(f"Hash do historico 1m nao corresponde ao baseline auditado: {current_hash}. Nada escrito.")
        print(f"Historico 1m original validado: SHA256 {current_hash}")

    print("FORCA x TEMPO — pesquisa exploratoria de microestrutura")
    print("Fonte: candles Spot publicos de 1 segundo; nenhuma chave API ou corretora.")
    print(f"Par={args.symbol.upper()} | janela={args.days} dias | horizonte=1 a 60 segundos")
    print("Nao usa dinheiro real. O CSV original de 1m nao sera modificado.")
    seconds, audit = download_1s_klines(args.symbol, args.days)
    seconds = prepare_features(seconds)
    events, responses, event_stats = analyze_events(seconds, args.fee_bps, args.slippage_bps)
    minute_detail, minute_summary = analyze_minute_extrema(seconds)

    out_root = root / "data" / "force_time"
    out_root.mkdir(parents=True, exist_ok=True)
    run_dir = out_root / f"run_{args.symbol.upper()}_{utc_now_stamp()}"
    run_dir.mkdir(parents=False, exist_ok=False)

    raw_path = run_dir / f"{args.symbol.upper()}_1s.csv"
    event_path = run_dir / "force_events.csv"
    response_path = run_dir / "force_response_by_horizon.csv"
    minute_path = run_dir / "minute_top_bottom_detail.csv"
    pattern_path = run_dir / "minute_top_bottom_summary.csv"
    summary_path = run_dir / "summary.json"

    save_cols = [
        "open_time_ms", "timestamp", "open", "high", "low", "close", "volume",
        "close_time_ms", "close_time", "quote_volume", "trades", "taker_buy_base_volume",
        "taker_buy_quote_volume", "observed_kline", "imbalance_5s", "imbalance_10s",
        "imbalance_30s", "quote_volume_5s", "quote_volume_10s", "quote_volume_30s",
        "relative_activity_5s",
    ]
    seconds[save_cols].to_csv(raw_path, index=False, encoding="utf-8")
    events.to_csv(event_path, index=False, encoding="utf-8")
    responses.to_csv(response_path, index=False, encoding="utf-8")
    minute_detail.to_csv(minute_path, index=False, encoding="utf-8")
    minute_summary.to_csv(pattern_path, index=False, encoding="utf-8")

    observed = seconds["observed_kline"].astype(bool)
    summary: dict[str, Any] = {
        "status": "EXPLORATORY_NOT_VALIDATED",
        "symbol": args.symbol.upper(),
        "interval": "1s",
        "method": {
            "buyer_pressure": "I_w = (2 * taker_buy_quote_volume_w - quote_volume_w) / quote_volume_w; range [-1,+1]",
            "relative_activity": "5-second quote volume divided by five times the trailing 300-second median per-second quote volume; baseline shifted five seconds to avoid including the signal window",
            "event_rule": "absolute 5s imbalance >= threshold AND 5s relative activity >= 1.5; one event per 60-second cooldown",
            "entry_exit_diagnostic": "signal confirmed at close t; hypothetical entry at open t+1; hypothetical exit at close t+h",
            "costs": {"fee_bps_per_side": args.fee_bps, "slippage_bps_per_side": args.slippage_bps, "round_trip_bps": 2 * (args.fee_bps + args.slippage_bps)},
            "high_low_timing": "1-second kline containing the minute high/low; not exact millisecond order inside that second",
        },
        "data_audit": audit,
        "actual_kline_pct": float(100 * observed.mean()),
        "synthetic_zero_activity_seconds": int((~observed).sum()),
        "event_counts_by_threshold": event_stats,
        "limitations": [
            "This is an exploratory event study, not a validated trading strategy.",
            "One-second klines reveal aggregate aggressor volume per second, not the exact ordering of every trade within that second.",
            "Missing reported klines are filled as flat zero-activity seconds for time alignment and are counted explicitly; they may represent no-trade seconds or data omissions and must be inspected.",
            "Thresholds 0.20/0.35/0.50 and activity ratio 1.5 are predeclared exploratory cuts, not optimized recommendations.",
            "The hourly-cluster bootstrap interval is preliminary; it does not correct all regime shifts or multiple comparisons.",
            "Net calculations assume fee and slippage values supplied on command line; actual execution costs may differ.",
            "Do not choose a response horizon from these same data and claim out-of-sample profitability; freeze rules and validate chronologically on future data.",
        ],
        "files": {
            "one_second_data": str(raw_path),
            "pressure_events": str(event_path),
            "response_by_horizon": str(response_path),
            "minute_high_low_detail": str(minute_path),
            "minute_high_low_summary": str(pattern_path),
        },
        "created_utc": datetime.now(timezone.utc).isoformat(),
    }
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False, allow_nan=False, default=str), encoding="utf-8")

    print("\n========== RESUMO DA COLETA ==========")
    print(f"Candles/segundos no grid: {len(seconds):,}")
    print(f"Candles reportados pela API: {int(observed.sum()):,}")
    print(f"Segundos sem kline reportado, preenchidos como atividade zero: {int((~observed).sum()):,}")
    print(f"Janela observada UTC: {seconds['timestamp'].iloc[0].isoformat()} ate {seconds['timestamp'].iloc[-1].isoformat()}")
    print(f"Eventos de pressao registrados: {len(events):,}")
    print("\n========== RESPOSTA POR HORIZONTE ==========")
    if responses.empty:
        print("Nenhum evento passou os criterios fixos; nao ha estatisticas a reportar.")
    else:
        display_cols = ["threshold_abs_imbalance_5s", "horizon_seconds", "events", "mean_gross_bps", "pct_gross_directionally_positive", "mean_net_bps_after_assumed_round_trip_cost", "hour_cluster_bootstrap_95ci_mean_gross_low_bps", "hour_cluster_bootstrap_95ci_mean_gross_high_bps"]
        print(responses[display_cols].to_string(index=False, formatters={
            "mean_gross_bps": lambda x: f"{x:.3f}",
            "pct_gross_directionally_positive": lambda x: f"{x:.1f}%",
            "mean_net_bps_after_assumed_round_trip_cost": lambda x: f"{x:.3f}",
            "hour_cluster_bootstrap_95ci_mean_gross_low_bps": lambda x: f"{x:.3f}",
            "hour_cluster_bootstrap_95ci_mean_gross_high_bps": lambda x: f"{x:.3f}",
        }))
    print("\n========== TOPO VS FUNDO DA VELA DE 1 MIN ==========")
    if not minute_summary.empty:
        print(minute_summary.to_string(index=False, formatters={
            "mean_directional_flow_after_extremum": lambda x: f"{x:.3f}",
            "pct_flow_aligned_after_extremum": lambda x: f"{x:.1f}%",
            "mean_extremum_to_close_bps": lambda x: f"{x:.3f}",
            "mean_close_location_0_bottom_1_top": lambda x: f"{x:.3f}",
            "mean_next_minute_close_return_bps": lambda x: f"{x:.3f}",
            "pct_next_minute_positive": lambda x: f"{x:.1f}%",
        }))
    print("\n========== ARQUIVOS NOVOS ==========")
    print(f"Pasta: {run_dir}")
    print(f"Resumo: {summary_path}")
    print("Os arquivos existentes do projeto e o CSV 1m nao foram sobrescritos.")
    print("RESULTADO EXPLORATORIO — nenhuma ordem foi enviada.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nInterrompido pelo usuario; sem ordens reais.", file=sys.stderr)
        raise SystemExit(130)
    except Exception as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        raise SystemExit(1)
