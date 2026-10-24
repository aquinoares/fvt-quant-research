from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(sys.argv[1]).resolve()
CSV = ROOT / "data" / "raw" / "BTCUSDT_1m.csv"
OUT_ROOT = ROOT / "reports"
EXPECTED_CSV_SHA256 = "604835C55D98319CF6F26516040F6F285E02152B6EE984238C0D3359C2DBDE41"
FEE_BPS_PER_SIDE = 10.0
SLIPPAGE_BPS_PER_SIDE = 5.0
ADAPT_VOL_RATIO = 1.20

sys.path.insert(0, str(ROOT / "src"))
import convergencia.strategy as strategy_module
from convergencia.backtest import run_backtest
from convergencia.strategy import StrategyConfig, generate_strategy_signals


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def parent_bars(frame: pd.DataFrame, config: StrategyConfig, timeframe: int) -> pd.DataFrame:
    indexed = frame.set_index("timestamp")
    rule = f"{timeframe}min"
    aggregation = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    if "quote_volume" in frame.columns:
        aggregation["quote_volume"] = "sum"
    parent = indexed.resample(rule, label="left", closed="left").agg(aggregation)
    parent["bar_count"] = indexed["close"].resample(rule, label="left", closed="left").count()
    parent = parent.loc[parent["bar_count"] == timeframe].copy()
    if parent.empty:
        raise ValueError(f"Dados insuficientes para contexto de {timeframe}m.")

    close = pd.to_numeric(parent["close"], errors="coerce")
    fast = close.ewm(span=config.parent_fast, adjust=False, min_periods=config.parent_fast).mean()
    slow = close.ewm(span=config.parent_slow, adjust=False, min_periods=config.parent_slow).mean()
    bullish = (close > fast) & (fast > slow) & (fast > fast.shift(2))
    bearish = (close < fast) & (fast < slow) & (fast < fast.shift(2))
    direction = pd.Series(0, index=parent.index, dtype="int8")
    direction.loc[bullish] = 1
    direction.loc[bearish] = -1

    result = pd.DataFrame({
        "available_at": parent.index + pd.Timedelta(minutes=timeframe),
        "parent_direction": direction.to_numpy(),
        "parent_close": close.to_numpy(),
        "selected_parent_timeframe_minutes": timeframe,
    })
    return result.sort_values("available_at").reset_index(drop=True)


def make_parent_builder(mode: str):
    """Constructs only from parent candles already fully closed at decision time."""
    original = strategy_module._parent_direction

    def build(frame: pd.DataFrame, config: StrategyConfig) -> pd.DataFrame:
        if mode == "15m":
            return original(frame, config)
        if mode in ("3m", "5m"):
            return parent_bars(frame, config, int(mode[:-1]))

        p3 = parent_bars(frame, config, 3)
        p5 = parent_bars(frame, config, 5)
        query = pd.DataFrame({"available_at": frame["timestamp"] + pd.Timedelta(minutes=1)})

        p3_right = p3[["available_at", "parent_direction", "parent_close"]].rename(
            columns={"parent_direction": "direction_3m", "parent_close": "close_3m"}
        ).sort_values("available_at")
        p5_right = p5[["available_at", "parent_direction", "parent_close"]].rename(
            columns={"parent_direction": "direction_5m", "parent_close": "close_5m"}
        ).sort_values("available_at")

        m3 = pd.merge_asof(
            query.copy(), p3_right, on="available_at", direction="backward",
            tolerance=pd.Timedelta(minutes=3), allow_exact_matches=True,
        )
        m5 = pd.merge_asof(
            query.copy(), p5_right, on="available_at", direction="backward",
            tolerance=pd.Timedelta(minutes=5), allow_exact_matches=True,
        )

        close = pd.to_numeric(frame["close"], errors="coerce").astype("float64")
        log_returns = np.log(close).diff()
        vol_fast = log_returns.rolling(5, min_periods=5).std(ddof=1)
        vol_slow = log_returns.rolling(20, min_periods=20).std(ddof=1)
        ratio = (vol_fast / vol_slow.replace(0.0, np.nan)).replace([np.inf, -np.inf], np.nan)
        use_fast_context = ratio.ge(ADAPT_VOL_RATIO).fillna(False).to_numpy(dtype=bool)

        d3 = m3["direction_3m"].fillna(0).to_numpy(dtype="int8")
        d5 = m5["direction_5m"].fillna(0).to_numpy(dtype="int8")
        c3 = m3["close_3m"].to_numpy(dtype="float64")
        c5 = m5["close_5m"].to_numpy(dtype="float64")

        return pd.DataFrame({
            "available_at": query["available_at"].to_numpy(),
            "parent_direction": np.where(use_fast_context, d3, d5).astype("int8"),
            "parent_close": np.where(use_fast_context, c3, c5),
            "selected_parent_timeframe_minutes": np.where(use_fast_context, 3, 5).astype("int8"),
        }).sort_values("available_at").reset_index(drop=True)

    return build


def generate_features(candles: pd.DataFrame, mode: str, config: StrategyConfig) -> pd.DataFrame:
    original = strategy_module._parent_direction
    strategy_module._parent_direction = make_parent_builder(mode)
    try:
        return generate_strategy_signals(candles, config)
    finally:
        strategy_module._parent_direction = original


def rules(features: pd.DataFrame, flexible: bool = False):
    parent = features["parent_direction"]
    child = features["child_direction"]
    fib = features["fibonacci_confirmed"].fillna(False).astype(bool)
    regime = features["regime_acceptable"].fillna(False).astype(bool)
    volume = features["volume_confirmed"].fillna(False).astype(bool)
    momentum = features["momentum_confirmed"].fillna(False).astype(bool)
    slope = pd.to_numeric(features["normalized_slope"], errors="coerce")

    if not flexible:
        entry = (parent == 1) & (child == 1) & fib & regime & volume & momentum
        exit_ = (parent != 1) | (child == -1) | (slope < 0)
    else:
        # O contexto pode estar neutro, mas nunca pode estar explicitamente contra a entrada.
        # Exige filho de alta e pelo menos 2 das 4 confirmações independentes.
        optional_score = fib.astype("int8") + regime.astype("int8") + volume.astype("int8") + momentum.astype("int8")
        entry = (parent >= 0) & (child == 1) & (optional_score >= 2)
        # Saída mais responsiva, sem exigir que o contexto deixe de ser exatamente bullish.
        exit_ = (child == -1) | (slope < 0) | ((parent == -1) & (child != 1))
    return entry.fillna(False).to_numpy(dtype=bool), exit_.fillna(False).to_numpy(dtype=bool)


def event_stream(features: pd.DataFrame, flexible: bool = False) -> np.ndarray:
    entry, exit_ = rules(features, flexible=flexible)
    events = np.zeros(len(features), dtype="int8")
    in_position = False
    for i in range(len(features)):
        if not in_position and entry[i]:
            events[i] = 1
            in_position = True
        elif in_position and exit_[i]:
            events[i] = -1
            in_position = False
    return events


def events_to_targets(events: np.ndarray) -> np.ndarray:
    """Translate entry/exit events to target exposure; -1 must never become short."""
    targets = np.zeros(len(events), dtype="int8")
    state = 0
    for i, event in enumerate(events):
        if event == 1:
            if state != 0:
                raise ValueError(f"Entrada duplicada no evento {i}.")
            state = 1
        elif event == -1:
            if state != 1:
                raise ValueError(f"Saída sem posição no evento {i}.")
            state = 0
        targets[i] = state
    return targets


def trade_returns(result: pd.DataFrame) -> list[float]:
    positions = result["position"].to_numpy(dtype="float64")
    net = result["net_return"].to_numpy(dtype="float64")
    completed = []
    active = False
    factor = 1.0
    previous = 0.0
    for i, (position, ret) in enumerate(zip(positions, net)):
        if position > 0 and previous <= 0:
            active = True
            factor = 1.0
        if active:
            factor *= 1.0 + float(ret)
        if active and position <= 0 and previous > 0:
            completed.append(factor - 1.0)
            active = False
        previous = position
    return completed


def run_metrics(segment: pd.DataFrame, events: np.ndarray, wrong_semantics: bool = False) -> dict:
    """Evaluate event signals with explicit next-open execution.

    The generic backtest takes position targets and shifts them once. This lab
    builds the executable position path directly, so event -> target -> position
    cannot be shifted or counted twice. The legacy mismatch is retained only
    for the separately labeled diagnostic row.
    """
    if wrong_semantics:
        bt = run_backtest(
            segment, events,
            fee_bps=FEE_BPS_PER_SIDE,
            slippage_bps=SLIPPAGE_BPS_PER_SIDE,
        )
        equity = bt["equity"].astype("float64")
        position = bt["position"].astype("float64")
        delta = position.diff().fillna(position)
        return {
            "signals_entry_events": int((events == 1).sum()),
            "signals_exit_events": int((events == -1).sum()),
            "executed_entries": int((delta > 0).sum()),
            "executed_exits": int((delta < 0).sum()),
            "short_exposure_bars": int((position < 0).sum()),
            "exposure_fraction": float((position > 0).mean()),
            "ending_equity": float(equity.iloc[-1]),
            "net_return_pct": float((equity.iloc[-1] - 1.0) * 100.0),
            "max_drawdown_pct": float((equity / equity.cummax() - 1.0).min() * 100.0),
            "closed_trades": 0,
            "closed_trade_win_rate_pct": None,
            "mean_closed_trade_return_pct": None,
            "forced_end_liquidations": 0,
        }

    n = len(segment)
    if n < 2 or len(events) != n:
        raise ValueError("Need at least two candles and one event per candle.")

    opens = pd.to_numeric(segment["open"], errors="coerce").to_numpy(dtype="float64")
    closes = pd.to_numeric(segment["close"], errors="coerce").to_numpy(dtype="float64")
    if not np.isfinite(opens).all() or not np.isfinite(closes).all() or (opens <= 0).any() or (closes <= 0).any():
        raise ValueError("Invalid OHLC prices in evaluation segment.")

    # Event at candle i is known only after its close; execution is at open i+1.
    targets = events_to_targets(events)
    position = np.zeros(n, dtype="float64")
    position[1:] = targets[:-1]

    # Open-to-open returns; final interval is marked open-to-final-close.
    interval_returns = np.empty(n, dtype="float64")
    interval_returns[:-1] = opens[1:] / opens[:-1] - 1.0
    interval_returns[-1] = closes[-1] / opens[-1] - 1.0

    prior_position = np.r_[0.0, position[:-1]]
    turnover = np.abs(position - prior_position)
    cost_per_side = (FEE_BPS_PER_SIDE + SLIPPAGE_BPS_PER_SIDE) / 10_000.0
    costs = turnover * cost_per_side

    # Force-liquidate a position still open at the end of this evaluation split.
    # The last candle's close is the final available mark; charge the exit cost.
    forced_end_liquidations = int(position[-1] > 0)
    if forced_end_liquidations:
        costs[-1] += cost_per_side

    gross = position * interval_returns
    net = gross - costs
    if np.any(1.0 + net <= 0):
        raise ValueError("Non-positive equity factor found in simulated returns.")
    equity = pd.Series(np.cumprod(1.0 + net), dtype="float64")
    drawdown = equity / equity.cummax() - 1.0

    # Add a synthetic flat row only for closing the final trade-statistics loop.
    trade_position = np.r_[position, 0.0] if forced_end_liquidations else position
    trade_net = np.r_[net, 0.0] if forced_end_liquidations else net
    trade_frame = pd.DataFrame({"position": trade_position, "net_return": trade_net})
    trades = trade_returns(trade_frame)

    delta = np.diff(np.r_[0.0, position])
    executed_entries = int((delta > 0).sum())
    executed_exits = int((delta < 0).sum()) + forced_end_liquidations
    if executed_entries < executed_exits:
        raise ValueError("More exits than entries; event/position accounting is inconsistent.")

    return {
        "signals_entry_events": int((events == 1).sum()),
        "signals_exit_events": int((events == -1).sum()),
        "executed_entries": executed_entries,
        "executed_exits": executed_exits,
        "short_exposure_bars": int((position < 0).sum()),
        "exposure_fraction": float((position > 0).mean()),
        "ending_equity": float(equity.iloc[-1]),
        "net_return_pct": float((equity.iloc[-1] - 1.0) * 100.0),
        "max_drawdown_pct": float(drawdown.min() * 100.0),
        "closed_trades": len(trades),
        "closed_trade_win_rate_pct": float(100.0 * sum(x > 0 for x in trades) / len(trades)) if trades else None,
        "mean_closed_trade_return_pct": float(100.0 * np.mean(trades)) if trades else None,
        "forced_end_liquidations": forced_end_liquidations,
    }


def main() -> int:
    if not CSV.is_file():
        raise SystemExit(f"CSV ausente: {CSV}")
    actual_hash = sha256_file(CSV)
    if actual_hash != EXPECTED_CSV_SHA256:
        raise SystemExit(f"SHA256 do CSV não confere. Esperado {EXPECTED_CSV_SHA256}; encontrado {actual_hash}")

    candles = pd.read_csv(CSV)
    if len(candles) < 3000:
        raise SystemExit("Amostra de candles insuficiente.")
    split = int(len(candles) * 0.70)

    variants = [
        ("BASELINE_15M", "15m", StrategyConfig(), False),
        ("FIXED_3M_STRICT", "3m", StrategyConfig(parent_fast=4, parent_slow=9), False),
        ("FIXED_5M_STRICT", "5m", StrategyConfig(parent_fast=4, parent_slow=9), False),
        ("ADAPTIVE_3M_5M_STRICT", "adaptive", StrategyConfig(parent_fast=4, parent_slow=9), False),
        ("ADAPTIVE_3M_5M_RESPONSIVE", "adaptive", StrategyConfig(
            parent_fast=4, parent_slow=9,
            child_fast=5, child_slow=13,
            fib_lookback=30, atr_window=10,
            volume_lookback=15, relative_volume_min=1.0,
            momentum_window=5, regime_window=30,
        ), True),
    ]

    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = OUT_ROOT / f"adaptive_timeframe_lab_{stamp}"
    out_dir.mkdir(parents=True, exist_ok=False)
    summary = []
    signal_trace = []
    validation = {
        "input_csv": str(CSV),
        "input_sha256": actual_hash,
        "rows": len(candles),
        "train_rows_70pct": split,
        "test_rows_30pct": len(candles) - split,
        "adaptive_rule": f"Use parent 3m when rolling std(log returns, 5 bars) / rolling std(log returns, 20 bars) >= {ADAPT_VOL_RATIO:.2f}; otherwise parent 5m.",
        "entry_timing": "Signal from completed 1m candle; execution at next candle open; return intervals and costs are aligned to the executable position path.",
        "costs_bps_per_side": {"fee": FEE_BPS_PER_SIDE, "slippage": SLIPPAGE_BPS_PER_SIDE, "round_trip_total": 2 * (FEE_BPS_PER_SIDE + SLIPPAGE_BPS_PER_SIDE)},
        "target_position_conversion": "Event +1 opens long at next candle open; event -1 returns to flat at next candle open. Long-only position path is simulated directly; event -1 is never treated as short.",
        "important_limitations": [
            "Exploratory comparison; many variants are compared, so the final 30% is not a pristine holdout after selecting a winner.",
            "The adaptive threshold is a fixed hypothesis and is not fitted to the final 30%.",
            "No real order book, spread replay, stop/target sizing, or broker execution is simulated.",
            "The original strategy.py and backtest.py are not modified by this lab.",
        ],
    }

    for name, mode, cfg, flexible in variants:
        print(f"Calculando {name} ...", flush=True)
        features = generate_features(candles, mode, cfg)
        if "selected_parent_timeframe_minutes" in features.columns:
            selection = pd.to_numeric(features["selected_parent_timeframe_minutes"], errors="coerce")
            pct3 = float((selection == 3).mean() * 100.0)
            pct5 = float((selection == 5).mean() * 100.0)
        else:
            pct3 = 0.0
            pct5 = 0.0

        for split_name, start, end in (
            ("TREINO_70", 0, split),
            ("TESTE_30", split, len(features)),
            ("FULL_EXPLORATORIO", 0, len(features)),
        ):
            segment = features.iloc[start:end].copy().reset_index(drop=True)
            events = event_stream(segment, flexible=flexible)
            good = run_metrics(segment, events, wrong_semantics=False)
            summary.append({
                "variant": name,
                "parent_mode": mode,
                "rule_mode": "SCORE_2_DE_4" if flexible else "STRICT_ALL_CONFIRMATIONS",
                "split": split_name,
                "selected_parent_3m_pct": pct3,
                "selected_parent_5m_pct": pct5,
                **good,
            })

            if name == "BASELINE_15M":
                wrong = run_metrics(segment, events, wrong_semantics=True)
                summary.append({
                    "variant": "BASELINE_15M_OLD_SEMANTICS_DIAGNOSTIC_ONLY",
                    "parent_mode": mode,
                    "rule_mode": "EVENTS_MISTAKEN_AS_POSITION_TARGETS",
                    "split": split_name,
                    "selected_parent_3m_pct": 0.0,
                    "selected_parent_5m_pct": 0.0,
                    **wrong,
                })

            for i, ev in enumerate(events):
                if ev != 0:
                    signal_trace.append({
                        "variant": name,
                        "split": split_name,
                        "timestamp": str(segment["timestamp"].iloc[i]),
                        "event": int(ev),
                        "parent_direction": int(segment["parent_direction"].iloc[i]),
                        "child_direction": int(segment["child_direction"].iloc[i]),
                        "buy_confirmations": int(segment["buy_confirmations"].iloc[i]),
                        "selected_parent_timeframe_minutes": int(segment["selected_parent_timeframe_minutes"].iloc[i]) if "selected_parent_timeframe_minutes" in segment.columns and pd.notna(segment["selected_parent_timeframe_minutes"].iloc[i]) else None,
                    })

    summary_path = out_dir / "comparacao.csv"
    pd.DataFrame(summary).to_csv(summary_path, index=False, encoding="utf-8-sig")
    trace_path = out_dir / "eventos_sinal.csv"
    pd.DataFrame(signal_trace).to_csv(trace_path, index=False, encoding="utf-8-sig")

    strategy_hash = sha256_file(ROOT / "src" / "convergencia" / "strategy.py")
    backtest_hash = sha256_file(ROOT / "src" / "convergencia" / "backtest.py")
    runner_hash = sha256_file(ROOT / "scripts" / "run_backtest.py")
    validation["strategy_py_sha256_after_runner_fix"] = strategy_hash
    validation["backtest_py_sha256_unchanged"] = backtest_hash
    validation["runner_py_sha256_after_runner_fix"] = runner_hash
    validation["results_csv"] = str(summary_path)
    validation["signal_event_trace_csv"] = str(trace_path)
    (out_dir / "validacao.json").write_text(json.dumps(validation, indent=2, ensure_ascii=False), encoding="utf-8")

    frame = pd.DataFrame(summary)
    shown = frame[frame["split"] == "TESTE_30"].copy()
    shown = shown.sort_values("net_return_pct", ascending=False)
    print("\n=== COMPARAÇÃO NO TESTE CRONOLÓGICO FINAL (EXPLORATÓRIO) ===")
    print(f"{'VARIANTE':42} {'ENT':>5} {'SAI':>5} {'SHORT':>6} {'RET.LIQ%':>10} {'DD%':>9} {'ACERTO_OP%':>11}")
    for _, r in shown.iterrows():
        wr = "-" if pd.isna(r["closed_trade_win_rate_pct"]) else f"{r['closed_trade_win_rate_pct']:.2f}"
        print(f"{str(r['variant'])[:42]:42} {int(r['executed_entries']):5d} {int(r['executed_exits']):5d} {int(r['short_exposure_bars']):6d} {r['net_return_pct']:10.3f} {r['max_drawdown_pct']:9.3f} {wr:>11}")
    print("\nARQUIVOS:")
    print("Comparação:", summary_path)
    print("Eventos:", trace_path)
    print("Validação:", out_dir / "validacao.json")
    print("Motor de sinais e backtest genérico preservados; somente run_backtest.py foi corrigido para converter eventos em posição-alvo.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())