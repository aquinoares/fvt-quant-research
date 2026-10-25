#!/usr/bin/env python3
"""Chronological stability diagnostic for the Pai/Filho/Trindade baseline.

IMPORTANT: this is a descriptive time-split diagnostic on the already-reviewed
90-day sample, not an untouched out-of-sample test and not evidence of live
profitability. It computes causal features once from the full contiguous history,
then resets the simulated position at each chronological window boundary.
Writes only new timestamped reports under <root>/reports.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

EXPECTED_CSV_SHA256 = "604835C55D98319CF6F26516040F6F285E02152B6EE984238C0D3359C2DBDE41"
EXPECTED_SOURCE_SHA256 = "95A40C752E8BF464220314EB2CA22022B3BA7F80941EC775EE53E639036E5D56"

VARIANTS = (
    ("FULL", None),
    ("NO_FIBONACCI", "fibonacci"),
    ("NO_FRACTAL_CHILD_CONFIRMATION", "fractal_child"),
    ("NO_REGIME_FILTER", "regime"),
    ("NO_VOLUME_CONFIRMATION", "volume"),
    ("NO_MOMENTUM_CONFIRMATION", "momentum"),
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def replay_events(buy_condition: pd.Series, exit_condition: pd.Series) -> np.ndarray:
    buy = buy_condition.fillna(False).to_numpy(dtype=bool)
    exit_ = exit_condition.fillna(False).to_numpy(dtype=bool)
    events = np.zeros(len(buy), dtype=np.int8)
    in_position = False
    for i in range(len(buy)):
        if not in_position and buy[i]:
            events[i] = 1
            in_position = True
        elif in_position and exit_[i]:
            events[i] = -1
            in_position = False
    return events


def max_drawdown(equity: pd.Series) -> float:
    values = equity.to_numpy(dtype="float64")
    if not len(values):
        return 0.0
    full = np.concatenate(([1.0], values))
    peaks = np.maximum.accumulate(full)
    return float(np.min(full / peaks - 1.0))


def run_variant_window(
    features: pd.DataFrame,
    variant: str,
    removed: str | None,
    fee_bps: float,
    slippage_bps: float,
    run_backtest,
) -> dict:
    parent_up = features["parent_direction"].eq(1)
    confirmations = {
        "fibonacci": features["fibonacci_confirmed"].fillna(False).astype(bool),
        "fractal_child": features["child_direction"].eq(1),
        "regime": features["regime_acceptable"].fillna(False).astype(bool),
        "volume": features["volume_confirmed"].fillna(False).astype(bool),
        "momentum": features["momentum_confirmed"].fillna(False).astype(bool),
    }
    entry = parent_up.copy()
    for name, condition in confirmations.items():
        if name != removed:
            entry &= condition
    exit_condition = (
        features["parent_direction"].ne(1)
        | features["child_direction"].eq(-1)
        | features["normalized_slope"].lt(0)
    ).fillna(False)
    events = replay_events(entry, exit_condition)
    bt = run_backtest(features, events, fee_bps=fee_bps, slippage_bps=slippage_bps)
    if bt.empty:
        raise RuntimeError(f"Backtest vazio: {variant}")

    pos = bt["position"].to_numpy(dtype="float64")
    entries = int(np.sum(np.diff(np.r_[0.0, pos]) > 0.5))
    exits = int(np.sum(np.diff(np.r_[0.0, pos]) < -0.5))
    gross_equity = float((1.0 + bt["gross_return"]).prod())
    net_equity = float((1.0 + bt["net_return"]).prod())
    return {
        "variant": variant,
        "removed_entry_confirmation": removed or "none",
        "fee_bps_per_side": float(fee_bps),
        "slippage_bps_per_side": float(slippage_bps),
        "rows_backtested": int(len(bt)),
        "buy_events": int(np.sum(events == 1)),
        "exit_events": int(np.sum(events == -1)),
        "executed_entries": entries,
        "executed_exits": exits,
        "exposure_fraction": float(bt["position"].mean()),
        "gross_total_return": gross_equity - 1.0,
        "net_total_return": net_equity - 1.0,
        "max_drawdown_net": max_drawdown(bt["equity"]),
        "sum_cost_returns": float(bt["costs"].sum()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Raiz da pasta 3 Pro")
    parser.add_argument("--input", default="data/raw/BTCUSDT_1m.csv", help="CSV OHLCV local")
    parser.add_argument("--windows", type=int, default=3, help="Numero de janelas cronologicas")
    parser.add_argument("--fee-bps", type=float, default=10.0, help="Taxa estimada por lado")
    parser.add_argument("--slippage-bps", type=float, default=5.0, help="Slippage estimado por lado")
    parser.add_argument("--allow-different-input", action="store_true", help="Permite dataset diferente para testes deliberados")
    args = parser.parse_args()

    root = args.root.resolve()
    source = Path(args.input)
    if not source.is_absolute():
        source = root / source
    source = source.resolve()
    if not source.is_file():
        raise FileNotFoundError(f"CSV nao encontrado: {source}")
    if args.windows < 2 or args.windows > 12:
        raise ValueError("--windows deve estar entre 2 e 12")
    if not np.isfinite([args.fee_bps, args.slippage_bps]).all() or min(args.fee_bps, args.slippage_bps) < 0:
        raise ValueError("Fee e slippage devem ser finitos e nao negativos")

    csv_sha_before = sha256_file(source)
    if not args.allow_different_input and csv_sha_before != EXPECTED_CSV_SHA256:
        raise RuntimeError("SHA256 do CSV diferente do historico auditado. Validacao cancelada.")
    original_path = root / "Matematica trindade.txt"
    original_sha_before = sha256_file(original_path) if original_path.is_file() else None
    if original_sha_before and not args.allow_different_input and original_sha_before != EXPECTED_SOURCE_SHA256:
        raise RuntimeError("SHA256 do arquivo matematico original mudou. Validacao cancelada.")

    sys.path.insert(0, str(root / "src"))
    from convergencia.backtest import run_backtest
    from convergencia.strategy import StrategyConfig, generate_strategy_signals

    print("Carregando o CSV e calculando features causais uma unica vez...")
    candles = pd.read_csv(source)
    features = generate_strategy_signals(candles, StrategyConfig())
    print(f"CSV SHA256: {csv_sha_before}")
    print(f"Candles: {len(candles):,}; features: {len(features):,}")
    print("Nota: features causais usam apenas o candle atual e o passado; cada janela reinicia a posicao em dinheiro.")
    print("IMPORTANTE: janelas cronologicas exploratorias; o historico completo ja foi inspecionado.")

    # Ensure FULL event generation matches the established strategy across the full dataset.
    full_entry = (
        features["parent_direction"].eq(1)
        & features["child_direction"].eq(1)
        & features["fibonacci_confirmed"].fillna(False).astype(bool)
        & features["regime_acceptable"].fillna(False).astype(bool)
        & features["volume_confirmed"].fillna(False).astype(bool)
        & features["momentum_confirmed"].fillna(False).astype(bool)
    )
    full_exit = (
        features["parent_direction"].ne(1)
        | features["child_direction"].eq(-1)
        | features["normalized_slope"].lt(0)
    ).fillna(False)
    reconstructed = replay_events(full_entry, full_exit)
    established = pd.to_numeric(features["signal"], errors="raise").to_numpy(dtype=np.int8)
    if not np.array_equal(reconstructed, established):
        idx = int(np.flatnonzero(reconstructed != established)[0])
        raise RuntimeError(f"Sinais FULL nao reconciliados na linha {idx}; nenhum relatorio foi criado.")
    print("Sinais FULL reconciliados com strategy.py: OK")

    # Equal-row contiguous slices; for this one-minute series, each 43,200-row
    # window represents 30 days (with the final remainder assigned to the last window).
    slices = np.array_split(np.arange(len(features)), args.windows)
    rows: list[dict] = []
    cost_cases = (("ZERO", 0.0, 0.0), ("BASE", args.fee_bps, args.slippage_bps))
    for wi, indexes in enumerate(slices, start=1):
        if len(indexes) < 3:
            raise RuntimeError(f"Janela {wi} pequena demais para backtest")
        start = int(indexes[0])
        stop = int(indexes[-1]) + 1
        window = features.iloc[start:stop].copy().reset_index(drop=True)
        start_ts = pd.to_datetime(window["timestamp"].iloc[0], utc=True).isoformat()
        end_ts = pd.to_datetime(window["timestamp"].iloc[-1], utc=True).isoformat()
        print(f"\n========== JANELA {wi}/{args.windows}: {start_ts} ate {end_ts} ==========")
        for cost_label, fee, slip in cost_cases:
            print(f"-- Custos {cost_label}: taxa={fee:g} bps/lado, slippage={slip:g} bps/lado")
            for variant, removed in VARIANTS:
                result = run_variant_window(window, variant, removed, fee, slip, run_backtest)
                result.update({
                    "window": wi,
                    "window_start_utc": start_ts,
                    "window_end_utc": end_ts,
                    "cost_case": cost_label,
                    "input_sha256": csv_sha_before,
                })
                rows.append(result)
                print(
                    f"{variant:30s} trades={result['executed_entries']:4d} "
                    f"exposure={result['exposure_fraction']*100:7.3f}% "
                    f"gross={result['gross_total_return']*100:8.3f}% "
                    f"net={result['net_total_return']*100:8.3f}% "
                    f"maxDD={result['max_drawdown_net']*100:8.3f}%"
                )

    if sha256_file(source) != csv_sha_before:
        raise RuntimeError("CSV historico mudou durante o experimento")
    if original_sha_before and sha256_file(original_path) != original_sha_before:
        raise RuntimeError("Arquivo matematico original mudou durante o experimento")

    reports = root / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    csv_out = reports / f"temporal_diagnostic_BTCUSDT_1m_{stamp}.csv"
    json_out = reports / f"temporal_diagnostic_BTCUSDT_1m_{stamp}.json"
    frame = pd.DataFrame(rows)
    frame.to_csv(csv_out, index=False, encoding="utf-8")
    payload = {
        "status": "IN_SAMPLE_TEMPORAL_DIAGNOSTIC_NOT_HELD_OUT",
        "input_file": str(source),
        "input_sha256": csv_sha_before,
        "rows_input": int(len(candles)),
        "windows": int(args.windows),
        "policy": "Causal features from full chronological series; position reset per window; fixed current parameters; no optimization.",
        "cost_cases": [{"label": n, "fee_bps_per_side": fee, "slippage_bps_per_side": slip} for n, fee, slip in cost_cases],
        "results": frame.to_dict(orient="records"),
        "limitations": [
            "This is a temporal stability diagnostic, not a true untouched out-of-sample test: the full dataset and ablation summaries were already reviewed.",
            "Parameters are frozen for this run; do not tune on these window results and still call them independent validation.",
            "The position is reset to flat at each window boundary and any open position is liquidated by the simulator at the boundary.",
            "No stop-loss, take-profit, position sizing or market-impact model is included.",
            "Fees and slippage are assumptions; results remain exploratory and are not evidence of live profitability.",
        ],
    }
    json_out.write_text(json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    print("\n========== SAIDAS ==========")
    print("CSV:", csv_out)
    print("JSON:", json_out)
    print("CSV historico inalterado:", csv_sha_before)
    if original_sha_before:
        print("Arquivo original inalterado:", original_sha_before)
    print("Concluido: nenhum sinal real enviado.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERRO NA VALIDACAO TEMPORAL: {exc}", file=sys.stderr)
        raise SystemExit(1)
