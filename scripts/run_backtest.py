"""Run the initial causal strategy on local historical candle data."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from convergencia.backtest import run_backtest
from convergencia.strategy import StrategyConfig, generate_strategy_signals


def main() -> int:
    parser = argparse.ArgumentParser(description="Convergencia Pai/Filho/Trindade - backtest exploratorio spot long-only")
    parser.add_argument("--input", default="data/raw/BTCUSDT_1m.csv", help="CSV OHLCV local")
    parser.add_argument("--symbol", default="BTCUSDT", help="Nome usado nos relatorios")
    parser.add_argument("--fee-bps", type=float, default=10.0, help="Taxa por transacao em basis points")
    parser.add_argument("--slippage-bps", type=float, default=5.0, help="Slippage estimado por transacao em basis points")
    parser.add_argument("--relative-volume-min", type=float, default=1.2, help="Volume relativo minimo")
    args = parser.parse_args()

    source = Path(args.input)
    if not source.is_absolute():
        source = ROOT / source
    if not source.is_file():
        parser.error(f"Arquivo de entrada nao encontrado: {source}")
    if not np.isfinite([args.fee_bps, args.slippage_bps]).all() or args.fee_bps < 0 or args.slippage_bps < 0:
        parser.error("Custos devem ser finitos e nao negativos")

    raw_bytes = source.read_bytes()
    source_sha256 = hashlib.sha256(raw_bytes).hexdigest()
    candles = pd.read_csv(source)
    cfg = StrategyConfig(relative_volume_min=args.relative_volume_min)

    print("Construindo features e sinais causais...")
    enriched = generate_strategy_signals(candles, cfg)
    print("Simulando execucao spot long-only...")
    # run_backtest recebe os EVENTOS crus (1=BUY, -1=EXIT, 0=HOLD) e converte-os
    # internamente em estado-alvo com atraso de um candle. Pre-converter aqui em
    # estado-alvo (como fazia events_to_position_targets) transformava a saida -1
    # em 0; o motor, lendo 0 como "manter estado", nunca encerrava a posicao — bug
    # de dupla conversao que contaminava o resultado (ver research/RESEARCH_REPORT.md,
    # Secao 6.1). O wrapper redundante foi removido.
    bt = run_backtest(enriched, enriched["signal"].to_numpy(), fee_bps=args.fee_bps, slippage_bps=args.slippage_bps)

    # run_backtest returns all valid opening-to-opening intervals; align via original row index.
    report = enriched.loc[bt.index].copy()
    for column in ("position", "next_open_return", "gross_return", "costs", "net_return", "equity"):
        report[column] = bt[column]

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    reports_dir = ROOT / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{args.symbol.upper()}_1m_{stamp}"
    features_path = reports_dir / f"signals_{stem}.csv"
    results_path = reports_dir / f"backtest_{stem}.csv"
    summary_path = reports_dir / f"backtest_summary_{stem}.json"

    # Keep a raw signal trace and a separate equity/returns trace for auditing.
    signal_columns = [
        "timestamp", "open", "high", "low", "close", "volume",
        "parent_direction", "child_direction", "fib_618", "fibonacci_confirmed",
        "regime_zscore", "regime_acceptable", "relative_volume", "volume_confirmed",
        "normalized_slope", "normalized_acceleration", "momentum_confirmed",
        "buy_confirmations", "signal",
    ]
    if "quote_volume" in report.columns:
        signal_columns.insert(6, "quote_volume")
    enriched[signal_columns].to_csv(features_path, index=False)
    report[["timestamp", "signal", "position", "next_open_return", "gross_return", "costs", "net_return", "equity"]].to_csv(results_path, index=False)

    final_equity = float(report["equity"].iloc[-1]) if len(report) else 1.0
    total_return = final_equity - 1.0
    drawdown = report["equity"] / report["equity"].cummax() - 1.0 if len(report) else pd.Series(dtype="float64")
    max_drawdown = float(drawdown.min()) if len(drawdown) else 0.0
    positions = report["position"].astype("float64")
    starts = int((positions.diff().fillna(positions) > 0).sum())
    exits = int((positions.diff().fillna(0.0) < 0).sum())
    exposure = float(positions.mean()) if len(positions) else 0.0
    opens = pd.to_numeric(enriched["open"], errors="coerce")
    cost_rate = (args.fee_bps + args.slippage_bps) / 10_000.0
    buy_hold_return = float((opens.iloc[-1] / opens.iloc[0]) * (1.0 - cost_rate) ** 2 - 1.0) if len(opens) > 1 else 0.0

    summary = {
        "status": "EXPLORATORY_NOT_VALIDATED",
        "symbol": args.symbol.upper(),
        "timeframe": "1m",
        "parent_timeframe": "15m",
        "input_file": str(source),
        "input_sha256": source_sha256,
        "rows_input": int(len(candles)),
        "rows_backtested": int(len(report)),
        "first_timestamp_utc": pd.to_datetime(enriched["timestamp"].iloc[0], utc=True).isoformat(),
        "last_timestamp_utc": pd.to_datetime(enriched["timestamp"].iloc[-1], utc=True).isoformat(),
        "fee_bps_per_side": float(args.fee_bps),
        "slippage_bps_per_side": float(args.slippage_bps),
        "relative_volume_min": float(args.relative_volume_min),
        "buy_signal_bars": int((enriched["signal"] == 1).sum()),
        "exit_signal_bars": int((enriched["signal"] == -1).sum()),
        "executed_entries": starts,
        "executed_exits_in_return_series": exits,
        "exposure_fraction": exposure,
        "ending_equity_from_1": final_equity,
        "total_return_net": total_return,
        "max_drawdown": max_drawdown,
        "buy_and_hold_return_net_estimate": buy_hold_return,
        "features_csv": str(features_path),
        "backtest_csv": str(results_path),
        "limitations": [
            "Exploratory result; not evidence of live profitability.",
            "No stop-loss, target, portfolio sizing, or market impact model in this first baseline.",
            "Fees and slippage are assumptions and must be stress-tested.",
            "The full history is not a held-out sample; use chronological walk-forward validation before conclusions.",
            "BUY opens a spot long; SELL/EXIT closes it and never shorts.",
        ],
    }
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\n========== BACKTEST SUMMARY ==========")
    print("Status:", summary["status"])
    print("Input SHA256:", source_sha256)
    print("Candles:", summary["rows_input"], "| backtested intervals:", summary["rows_backtested"])
    print("Buy signal bars:", summary["buy_signal_bars"], "| exit signal bars:", summary["exit_signal_bars"])
    print("Executed entries:", starts, "| executed exits:", exits)
    print("Exposure:", f"{exposure:.2%}")
    print("Net total return:", f"{total_return:.2%}")
    print("Max drawdown:", f"{max_drawdown:.2%}")
    print("Buy-and-hold net estimate:", f"{buy_hold_return:.2%}")
    print("Features:", features_path)
    print("Results:", results_path)
    print("Summary:", summary_path)
    if starts == 0:
        print("WARNING: no completed entries; this is not a performance result. Review signal frequency before interpreting returns.")
    print("No real orders were sent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
