#!/usr/bin/env python3
"""Ablation study for the Convergencia Pai/Filho/Trindade strategy.

Read-only with respect to source market data and strategy modules. Writes only
new timestamped summary reports under <root>/reports.

Each ablation removes one entry confirmation while keeping the macro context
(Pai), exit rules, execution model, candles, and cost assumptions fixed. The
Fractal ablation removes the child's bullish-direction entry confirmation;
parent context remains a common architecture gate.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
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


def sha256_bytes(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def replay_events(buy_condition: pd.Series, exit_condition: pd.Series) -> np.ndarray:
    """Turn causal entry/exit conditions into position-aware events."""
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
    values = equity.to_numpy(dtype=float)
    if not len(values):
        return 0.0
    with_initial = np.concatenate(([1.0], values))
    peaks = np.maximum.accumulate(with_initial)
    # Use equity values after each interval, compared to all prior peaks incl. initial capital.
    dd = values / peaks[1:] - 1.0
    return float(np.min(dd)) if len(dd) else 0.0


def trade_diagnostics(bt: pd.DataFrame) -> dict[str, float | int]:
    pos = (bt["position"].to_numpy(dtype=float) > 0.5)
    prior = np.concatenate(([False], pos[:-1]))
    following = np.concatenate((pos[1:], [False]))
    starts = np.flatnonzero(pos & ~prior)
    ends = np.flatnonzero(pos & ~following)
    if len(starts) != len(ends):
        raise RuntimeError("Position series has unmatched trade starts/ends")

    gross_trades: list[float] = []
    net_trade_windows: list[float] = []
    durations: list[int] = []
    gross = bt["gross_return"].to_numpy(dtype=float)
    net = bt["net_return"].to_numpy(dtype=float)
    for start, end in zip(starts, ends):
        gross_trades.append(float(np.prod(1.0 + gross[start:end + 1]) - 1.0))
        # Entry cost is recorded on the preceding interval; exit cost on the final held interval.
        window_start = max(int(start) - 1, 0)
        net_trade_windows.append(float(np.prod(1.0 + net[window_start:end + 1]) - 1.0))
        durations.append(int(end - start + 1))

    gross_arr = np.asarray(gross_trades, dtype=float)
    net_arr = np.asarray(net_trade_windows, dtype=float)
    positives = float(gross_arr[gross_arr > 0].sum()) if len(gross_arr) else 0.0
    negatives = float(-gross_arr[gross_arr < 0].sum()) if len(gross_arr) else 0.0
    pf = positives / negatives if negatives > 0 else (float("inf") if positives > 0 else float("nan"))

    return {
        "trades": int(len(starts)),
        "avg_holding_bars": float(np.mean(durations)) if durations else 0.0,
        "median_holding_bars": float(np.median(durations)) if durations else 0.0,
        "gross_trade_win_rate": float(np.mean(gross_arr > 0)) if len(gross_arr) else 0.0,
        "net_trade_window_win_rate": float(np.mean(net_arr > 0)) if len(net_arr) else 0.0,
        "mean_gross_trade_return": float(np.mean(gross_arr)) if len(gross_arr) else 0.0,
        "median_gross_trade_return": float(np.median(gross_arr)) if len(gross_arr) else 0.0,
        "gross_profit_factor_per_trade": float(pf),
    }


def run_variant(
    candles: pd.DataFrame,
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

    # Keep the baseline exit policy fixed across variants to isolate entry filters.
    exit_condition = (
        features["parent_direction"].ne(1)
        | features["child_direction"].eq(-1)
        | features["normalized_slope"].lt(0)
    ).fillna(False)
    events = replay_events(entry, exit_condition)

    if variant == "FULL":
        expected = pd.to_numeric(features["signal"], errors="raise").to_numpy(dtype=np.int8)
        if not np.array_equal(events, expected):
            mismatch = int(np.flatnonzero(events != expected)[0])
            raise RuntimeError(
                "A regra FULL reconstruida nao corresponde ao signal original; "
                f"primeira divergencia na linha {mismatch}. Abortando comparacao."
            )

    bt = run_backtest(features, events, fee_bps=fee_bps, slippage_bps=slippage_bps)
    if bt.empty:
        raise RuntimeError(f"Backtest vazio para variante {variant}")

    gross_equity = (1.0 + bt["gross_return"]).cumprod()
    gross_return = float(gross_equity.iloc[-1] - 1.0)
    net_return = float(bt["equity"].iloc[-1] - 1.0)
    diag = trade_diagnostics(bt)
    diag.update({
        "variant": variant,
        "removed_entry_confirmation": removed or "none",
        "fee_bps_per_side": float(fee_bps),
        "slippage_bps_per_side": float(slippage_bps),
        "buy_events": int(np.sum(events == 1)),
        "exit_events": int(np.sum(events == -1)),
        "candidate_entry_bars": int(entry.sum()),
        "exposure_fraction": float(bt["position"].mean()),
        "gross_total_return": gross_return,
        "net_total_return": net_return,
        "max_drawdown_net": max_drawdown(bt["equity"]),
        "sum_cost_returns": float(bt["costs"].sum()),
        "rows_backtested": int(len(bt)),
    })
    return diag


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Raiz da pasta 3 Pro")
    parser.add_argument("--input", default="data/raw/BTCUSDT_1m.csv", help="CSV OHLCV de 1 minuto")
    parser.add_argument("--fee-bps", type=float, default=10.0, help="Taxa por lado em bps para o cenario de custo-base")
    parser.add_argument("--slippage-bps", type=float, default=5.0, help="Slippage por lado em bps para o cenario de custo-base")
    parser.add_argument("--allow-different-input", action="store_true", help="Permite deliberadamente um CSV diferente do historico auditado")
    args = parser.parse_args()

    root = args.root.resolve()
    source = Path(args.input)
    if not source.is_absolute():
        source = root / source
    source = source.resolve()
    if not source.is_file():
        raise FileNotFoundError(f"CSV de entrada nao encontrado: {source}")
    if not np.isfinite([args.fee_bps, args.slippage_bps]).all() or min(args.fee_bps, args.slippage_bps) < 0:
        raise ValueError("Fee e slippage devem ser finitos e nao negativos")

    csv_sha_before = sha256_bytes(source)
    if not args.allow_different_input and csv_sha_before != EXPECTED_CSV_SHA256:
        raise RuntimeError(
            "SHA256 do CSV nao corresponde ao historico auditado. "
            "Por seguranca, estudo cancelado. Use --allow-different-input somente se escolheu outro dataset de proposito."
        )
    original_path = root / "Matematica trindade.txt"
    original_sha_before = sha256_bytes(original_path) if original_path.is_file() else None
    if original_sha_before is not None and original_sha_before != EXPECTED_SOURCE_SHA256 and not args.allow_different_input:
        raise RuntimeError("SHA256 do arquivo de referencia mudou. Estudo cancelado.")

    src = root / "src"
    if not src.is_dir():
        raise FileNotFoundError(f"Diretorio src nao encontrado: {src}")
    sys.path.insert(0, str(src))
    from convergencia.backtest import run_backtest
    from convergencia.strategy import StrategyConfig, generate_strategy_signals

    print("Carregando candles e calculando features uma unica vez...")
    candles = pd.read_csv(source)
    config = StrategyConfig()
    features = generate_strategy_signals(candles, config)
    print(f"CSV SHA256: {csv_sha_before}")
    print(f"Candles: {len(candles):,}; features geradas: {len(features):,}")
    print(f"Custos-base por lado: taxa={args.fee_bps:g} bps; slippage={args.slippage_bps:g} bps")
    print("As ablações alteram somente os filtros de entrada; Pai e regras de saída ficam fixos.")

    rows: list[dict] = []
    cost_cases = (("ZERO", 0.0, 0.0), ("BASE", args.fee_bps, args.slippage_bps))
    for label, fee, slip in cost_cases:
        print(f"\n--- CENARIO DE CUSTO {label}: fee={fee:g} bps/lado, slippage={slip:g} bps/lado ---")
        for variant, removed in VARIANTS:
            result = run_variant(candles, features, variant, removed, fee, slip, run_backtest)
            result["cost_case"] = label
            rows.append(result)
            print(
                f"{variant:30s} trades={result['trades']:4d} "
                f"exposure={result['exposure_fraction'] * 100:7.3f}% "
                f"gross={result['gross_total_return'] * 100:8.3f}% "
                f"net={result['net_total_return'] * 100:8.3f}% "
                f"maxDD={result['max_drawdown_net'] * 100:8.3f}%"
            )

    # Ensure both inputs remained unchanged during the experiment.
    csv_sha_after = sha256_bytes(source)
    if csv_sha_after != csv_sha_before:
        raise RuntimeError("CSV de candles mudou durante o estudo")
    if original_sha_before is not None and sha256_bytes(original_path) != original_sha_before:
        raise RuntimeError("Arquivo matematico original mudou durante o estudo")

    reports = root / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    csv_out = reports / f"ablation_BTCUSDT_1m_{stamp}.csv"
    json_out = reports / f"ablation_BTCUSDT_1m_{stamp}.json"

    result_frame = pd.DataFrame(rows)
    result_frame.to_csv(csv_out, index=False, encoding="utf-8")
    def json_safe(value):
        if isinstance(value, dict):
            return {str(k): json_safe(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [json_safe(v) for v in value]
        if isinstance(value, (np.integer,)):
            return int(value)
        if isinstance(value, (np.floating, float)):
            return float(value) if np.isfinite(value) else None
        if pd.isna(value):
            return None
        return value

    payload = {
        "status": "EXPLORATORY_ABLATION_NOT_VALIDATED",
        "input_file": str(source),
        "input_sha256": csv_sha_before,
        "rows_input": int(len(candles)),
        "strategy_config": asdict(config),
        "policy": "Each variant removes one entry confirmation; parent context and exit rules remain fixed.",
        "cost_cases": [{"label": label, "fee_bps_per_side": fee, "slippage_bps_per_side": slip} for label, fee, slip in cost_cases],
        "variants": json_safe(result_frame.to_dict(orient="records")),
        "limitations": [
            "In-sample exploratory comparison only; not a parameter optimization or proof of profitability.",
            "Ablations remove one entry confirmation while keeping common exit rules fixed.",
            "The fractal ablation removes the child's bullish-direction entry confirmation but retains parent context and bearish-child exit rule.",
            "No stop-loss, take-profit, sizing, or market-impact model is introduced.",
            "Use chronological validation and a held-out period before drawing performance conclusions.",
        ],
    }
    json_out.write_text(json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")

    print("\n========== SAIDAS ==========")
    print("CSV:", csv_out)
    print("JSON:", json_out)
    print("CSV historico inalterado:", csv_sha_after)
    if original_sha_before is not None:
        print("Arquivo matematico original inalterado:", original_sha_before)
    print("Concluido: nenhum sinal/ordem real enviado; apenas relatorios novos foram criados.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERRO NO ESTUDO DE ABLACAO: {exc}", file=sys.stderr)
        raise SystemExit(1)
