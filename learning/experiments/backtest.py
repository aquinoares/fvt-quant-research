#!/usr/bin/env python3
"""Backtest didático SMA-20 4h. EXPLORATÓRIO — NÃO É PROVA; não é P6-MOM."""
from __future__ import annotations

import argparse
import csv
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LABEL = "EXPLORATÓRIO — NÃO É PROVA"
LOOKBACK_BARS = 20
ROUND_TRIP_COST_BPS = 30
COST_PER_SIDE = (ROUND_TRIP_COST_BPS / 2) / 10_000


def evaluate_segment(candles: list[dict[str, Any]]) -> dict[str, Any]:
    if len(candles) < LOOKBACK_BARS + 2:
        return {
            "status": "insufficient_data", "candles": len(candles),
            "net_return": None, "buy_hold_net_return": None,
            "max_drawdown": None, "completed_trades": 0, "exposure_bars": 0,
        }
    equity, peak, max_drawdown = 1.0, 1.0, 0.0
    position = False
    completed_trades = exposure_bars = 0
    for index in range(LOOKBACK_BARS, len(candles)):
        prior_closes = [float(row["close"]) for row in candles[index - LOOKBACK_BARS:index]]
        desired = float(candles[index - 1]["close"]) > sum(prior_closes) / LOOKBACK_BARS
        if desired != position:
            equity *= 1.0 - COST_PER_SIDE
            if position and not desired:
                completed_trades += 1
            position = desired
        if position:
            open_price, close_price = float(candles[index]["open"]), float(candles[index]["close"])
            if open_price <= 0 or not math.isfinite(open_price + close_price):
                continue
            equity *= close_price / open_price
            exposure_bars += 1
        peak = max(peak, equity)
        if peak > 0:
            max_drawdown = min(max_drawdown, equity / peak - 1.0)
    if position:
        equity *= 1.0 - COST_PER_SIDE
        completed_trades += 1
    first_open, last_close = float(candles[LOOKBACK_BARS]["open"]), float(candles[-1]["close"])
    buy_hold = (last_close / first_open) * (1.0 - COST_PER_SIDE) ** 2 - 1.0 if first_open > 0 else None
    return {
        "status": "ok", "candles": len(candles), "net_return": equity - 1.0,
        "buy_hold_net_return": buy_hold, "max_drawdown": max_drawdown,
        "completed_trades": completed_trades, "exposure_bars": exposure_bars,
    }


def run_experiment(candles: list[dict[str, Any]]) -> dict[str, Any]:
    ordered = sorted(candles, key=lambda row: int(row["open_time_ms"]))
    split_at = int(len(ordered) * 0.70)
    train, validation = ordered[:split_at], ordered[split_at:]
    train_metrics, validation_metrics = evaluate_segment(train), evaluate_segment(validation)
    warnings = [
        LABEL,
        "Baseline pedagógico SMA-20 fixo; seleção repetida de regras/parâmetros aumenta risco de sobreajuste.",
        "Retorno por candle considera open→close quando a posição está aberta; gaps entre candles são simplificados.",
    ]
    if train_metrics["completed_trades"] < 10:
        warnings.append("Amostra de treino pequena: menos de 10 operações completas; resultado inconclusivo.")
    if validation_metrics["completed_trades"] < 10:
        warnings.append("Amostra de validação pequena: menos de 10 operações completas; resultado inconclusivo.")
    if len(train) < LOOKBACK_BARS + 2 or len(validation) < LOOKBACK_BARS + 2:
        warnings.append("Dados insuficientes para comparar treino e validação com confiança.")
    return {
        "label": LABEL,
        "created_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "symbol": "BTCUSDT", "signal_interval": "4h",
        "method": "Baseline long-only SMA-20 não otimizado; sinal usa candles anteriores e custos por lado.",
        "round_trip_cost_bps": ROUND_TRIP_COST_BPS, "train_fraction": 0.70,
        "train": train_metrics, "validation": validation_metrics, "warnings": warnings,
        "interpretation": "Não valida a Trilha B, não altera parâmetros congelados e não prova rentabilidade.",
    }


def load_candles(root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted((root / "data" / "BTCUSDT_4h").glob("*.csv")):
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            for row in csv.DictReader(stream):
                try:
                    rows.append({
                        "open_time_ms": int(row["open_time_ms"]),
                        "open": float(row["open"]), "close": float(row["close"]),
                    })
                except (KeyError, ValueError, TypeError):
                    continue
    return sorted(rows, key=lambda row: row["open_time_ms"])


def write_report(root: Path, result: dict[str, Any]) -> None:
    out = root / "experiments"
    out.mkdir(parents=True, exist_ok=True)
    (out / "latest_backtest.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    lines = [
        "# Backtest didático da Trilha A", "", f"**{LABEL}.**", "",
        f"- Gerado em UTC: {result['created_at_utc']}",
        f"- Método: {result['method']}",
        f"- Custo ida e volta: {result['round_trip_cost_bps']} bps.",
        f"- Treino (primeiros 70%): {json.dumps(result['train'], ensure_ascii=False, sort_keys=True)}",
        f"- Validação (últimos 30%): {json.dumps(result['validation'], ensure_ascii=False, sort_keys=True)}",
        "", "## Avisos obrigatórios", "",
    ]
    lines.extend(f"- {warning}" for warning in result["warnings"])
    lines.extend(["", result["interpretation"], ""])
    (out / "latest_backtest.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("learning"))
    args = parser.parse_args()
    candles = load_candles(args.root)
    result = run_experiment(candles)
    write_report(args.root, result)
    print(f"{LABEL}: candles={len(candles)}; train trades={result['train']['completed_trades']}; validation trades={result['validation']['completed_trades']}; cost={ROUND_TRIP_COST_BPS}bps RT")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
