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
SIGNAL_INTERVAL_MS = 4 * 60 * 60 * 1000
MIN_COMPLETED_TRADES = 10
EXECUTION_POLICY = (
    "Sinal no fecho da barra N executa na abertura da barra N+1 "
    "(atraso de 1 barra; nunca no fecho de N)."
)
BENCHMARK_POLICY = (
    "Benchmark buy-and-hold líquido no mesmo período de avaliação da segmentação, "
    "com os mesmos 30 bps ida e volta."
)
VALIDATION_POLICY = (
    "O período final de validação (30%) só serve para checagem final; "
    "usá-lo para escolher parâmetros ou regras contamina o resultado."
)
RAW_METRICS_NOTE = (
    "raw_metrics existe apenas para diagnóstico quando status=inconclusive; "
    "não é resultado utilizável."
)


def _price(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number <= 0:
        return None
    return number


def _temporal_quality(candles: list[dict[str, Any]]) -> dict[str, int]:
    gap_transitions = missing_bars_estimate = nonmonotonic_diffs = irregular_diffs = 0
    for previous, current in zip(candles, candles[1:]):
        diff = current["open_time_ms"] - previous["open_time_ms"]
        if diff <= 0:
            nonmonotonic_diffs += 1
        elif diff % SIGNAL_INTERVAL_MS:
            irregular_diffs += 1
        elif diff > SIGNAL_INTERVAL_MS:
            gap_transitions += 1
            missing_bars_estimate += diff // SIGNAL_INTERVAL_MS - 1
    return {
        "expected_interval_ms": SIGNAL_INTERVAL_MS,
        "gap_transitions": gap_transitions,
        "missing_bars_estimate": missing_bars_estimate,
        "nonmonotonic_diffs": nonmonotonic_diffs,
        "irregular_diffs": irregular_diffs,
    }


def evaluate_segment(candles: list[dict[str, Any]]) -> dict[str, Any]:
    quality = _temporal_quality(candles)
    base: dict[str, Any] = {
        "status": "insufficient_data", "reason": None, "candles": len(candles),
        "net_return": None, "buy_hold_net_return": None, "max_drawdown": None,
        "completed_trades": 0, "exposure_bars": 0, "raw_metrics": None,
    }
    base.update(quality)
    if len(candles) < LOOKBACK_BARS + 2:
        base["reason"] = (
            f"série com {len(candles)} candles; mínimo de {LOOKBACK_BARS + 2} "
            "para avaliar a SMA-20 sem fabricar métricas."
        )
        return base
    for row in candles:
        if _price(row.get("open")) is None or _price(row.get("close")) is None:
            base["status"] = "inconclusive"
            base["reason"] = "há candle com preço não positivo ou não finito; métricas suprimidas."
            return base
    equity, peak, max_drawdown = 1.0, 1.0, 0.0
    position = False
    completed_trades = exposure_bars = 0
    for index in range(LOOKBACK_BARS, len(candles)):
        prior_closes = [row["close"] for row in candles[index - LOOKBACK_BARS:index]]
        desired = candles[index - 1]["close"] > sum(prior_closes) / LOOKBACK_BARS
        entering = desired and not position
        if desired != position:
            equity *= 1.0 - COST_PER_SIDE
            if position and not desired:
                completed_trades += 1
            position = desired
        if position:
            open_price, close_price = candles[index]["open"], candles[index]["close"]
            if not entering:
                equity *= open_price / candles[index - 1]["close"]
            equity *= close_price / open_price
            exposure_bars += 1
        peak = max(peak, equity)
        if peak > 0:
            max_drawdown = min(max_drawdown, equity / peak - 1.0)
    if position:
        equity *= 1.0 - COST_PER_SIDE
        completed_trades += 1
    first_open, last_close = candles[LOOKBACK_BARS]["open"], candles[-1]["close"]
    raw = {
        "net_return": equity - 1.0,
        "buy_hold_net_return": (last_close / first_open) * (1.0 - COST_PER_SIDE) ** 2 - 1.0,
        "max_drawdown": max_drawdown,
    }
    reasons: list[str] = []
    if quality["gap_transitions"] or quality["missing_bars_estimate"]:
        reasons.append(
            f"{quality['gap_transitions']} lacuna(s) de tempo cobrindo "
            f"{quality['missing_bars_estimate']} barra(s) ausente(s) de 4h."
        )
    if quality["nonmonotonic_diffs"]:
        reasons.append(f"{quality['nonmonotonic_diffs']} timestamp(s) não monotônico(s) (duplicado/ordenado).")
    if quality["irregular_diffs"]:
        reasons.append(f"{quality['irregular_diffs']} intervalo(s) fora de 4h.")
    if completed_trades < MIN_COMPLETED_TRADES:
        reasons.append(
            f"menos de {MIN_COMPLETED_TRADES} operações completas "
            f"({completed_trades}); amostra inconclusiva."
        )
    if reasons:
        base.update({
            "status": "inconclusive", "reason": " ".join(reasons),
            "completed_trades": completed_trades, "exposure_bars": exposure_bars,
            "raw_metrics": raw,
        })
        return base
    base.update({
        "status": "ok", "completed_trades": completed_trades, "exposure_bars": exposure_bars,
        "net_return": raw["net_return"], "buy_hold_net_return": raw["buy_hold_net_return"],
        "max_drawdown": raw["max_drawdown"],
    })
    return base


def run_experiment(candles: list[dict[str, Any]]) -> dict[str, Any]:
    ordered: list[dict[str, Any]] = []
    dropped_duplicates = 0
    for row in sorted(candles, key=lambda item: int(item["open_time_ms"])):
        if ordered and row["open_time_ms"] == ordered[-1]["open_time_ms"]:
            dropped_duplicates += 1
            continue
        ordered.append(row)
    split_at = int(len(ordered) * 0.70)
    train, validation = ordered[:split_at], ordered[split_at:]
    train_metrics, validation_metrics = evaluate_segment(train), evaluate_segment(validation)
    warnings = [
        LABEL,
        "Baseline pedagógico SMA-20 fixo; seleção repetida de regras/parâmetros aumenta risco de sobreajuste.",
        VALIDATION_POLICY,
        "Retorno de uma posição aberta é contínuo: fecho da barra N vira abertura da barra N+1, "
        "inclusive em lacunas de tempo.",
        RAW_METRICS_NOTE,
    ]
    if dropped_duplicates:
        warnings.append(f"{dropped_duplicates} candle(s) com timestamp duplicado foram descartados.")
    for name, metrics in (("treino", train_metrics), ("validação", validation_metrics)):
        if metrics["status"] == "inconclusive":
            warnings.append(f"Amostra de {name} inconclusiva: {metrics['reason']}")
        if metrics["completed_trades"] < MIN_COMPLETED_TRADES:
            warnings.append(
                f"Amostra de {name} pequena: menos de {MIN_COMPLETED_TRADES} operações completas; "
                "resultado inconclusivo."
            )
    return {
        "label": LABEL,
        "created_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "symbol": "BTCUSDT", "signal_interval": "4h",
        "method": (
            "Baseline long-only SMA-20 não otimizado; sinal usa apenas candles anteriores; "
            "execução na abertura da barra seguinte; custos por lado."
        ),
        "round_trip_cost_bps": ROUND_TRIP_COST_BPS, "train_fraction": 0.70,
        "execution_policy": EXECUTION_POLICY,
        "benchmark_policy": BENCHMARK_POLICY,
        "validation_policy": VALIDATION_POLICY,
        "data_quality": {"duplicate_timestamps_dropped": dropped_duplicates},
        "train": train_metrics, "validation": validation_metrics, "warnings": warnings,
        "interpretation": (
            "Não valida a Trilha B, não altera parâmetros congelados e não prova rentabilidade; "
            "métricas suprimidas em status inconclusive ficam apenas em raw_metrics."
        ),
    }


def load_candles(root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted((root / "data" / "BTCUSDT_4h").glob("*.csv")):
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            for row in csv.DictReader(stream):
                try:
                    open_time_ms = int(row["open_time_ms"])
                    open_price = _price(row["open"])
                    close_price = _price(row["close"])
                except (KeyError, TypeError, ValueError):
                    continue
                if open_price is None or close_price is None:
                    continue
                rows.append({
                    "open_time_ms": open_time_ms, "open": open_price, "close": close_price,
                })
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
        f"- Execução: {result['execution_policy']}",
        f"- Benchmark: {result['benchmark_policy']}",
        f"- Validação: {result['validation_policy']}",
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
    print(
        f"{LABEL}: candles={len(candles)}; "
        f"train trades={result['train']['completed_trades']} ({result['train']['status']}); "
        f"validation trades={result['validation']['completed_trades']} "
        f"({result['validation']['status']}); cost={ROUND_TRIP_COST_BPS}bps RT"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
