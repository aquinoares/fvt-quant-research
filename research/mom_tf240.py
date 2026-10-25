"""Variante congelada MOM_TF240_LB96 para o protocolo prospectivo P6-MOM.

Configuracao vencedora da busca historica (winner id 722a0dd140):
family=momentum, tf=240min, lookback=96 barras, thr=+0.5% de ROC.
Entrada comprada quando ROC(96 barras de 240min) > 0.005; caso contrario,
caixa. Sinal disponivel no fecho da barra de 240min; execucao no proximo
candle conforme o motor convergencia.backtest.run_backtest (open t+1).
Long-only spot, sem alavancagem. Custos P4: 10+5 bps por lado (30 bps por
operacao completa).

A logica de sinais abaixo e copiada de research/strategy_search.py
(bars_of/map_to_1m/familia momentum) e travada por teste de paridade em
tests/test_p6_mom_separation.py contra o codigo da busca.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from convergencia.backtest import run_backtest  # noqa: E402

PROTOCOL = "P6-MOM"
VARIANT = "MOM_TF240_LB96"
CONFIG = {"family": "momentum", "tf": 240, "lookback": 96, "thr": 0.005}
FEE_BPS_P4 = 10.0
SLIP_BPS_P4 = 5.0
FEE_BPS_STRESS = 20.0
SLIP_BPS_STRESS = 10.0
WINDOW_DAYS = 90
RISK_LIMIT_DD = -0.10
MIN_COMPLETE_TRADES = 10
STRESS_ROUND_TRIP_BPS = 60.0


def bars_of(frame: pd.DataFrame, tf: int) -> pd.DataFrame:
    """Agrega 1m em barras `tf`min COMPLETAS (paridade com strategy_search)."""
    indexed = frame.set_index("timestamp")
    if tf == 1:
        return indexed[["open", "high", "low", "close", "volume"]].copy()
    rule = f"{tf}min"
    agg = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    b = indexed.resample(rule, label="left", closed="left").agg(agg)
    cnt = indexed["close"].resample(rule, label="left", closed="left").count()
    return b.loc[cnt == tf].copy()


def map_to_1m(frame: pd.DataFrame, series: pd.Series, tf: int) -> pd.Series:
    """Mapeia sinal de barra tf-min para 1m disponivel no fecho da barra."""
    sig_ts = series.index + pd.Timedelta(minutes=tf - 1)
    right = pd.DataFrame({"sig_ts": sig_ts, "value": series.to_numpy()})
    right = right.dropna().sort_values("sig_ts")
    if right.empty:
        return pd.Series(np.nan, index=frame.index)
    merged = pd.merge_asof(
        frame[["timestamp"]].reset_index(drop=True),
        right,
        left_on="timestamp",
        right_on="sig_ts",
        direction="backward",
    )
    return pd.Series(merged["value"].to_numpy(), index=frame.index)


def build_events(candles: pd.DataFrame, config: dict | None = None) -> np.ndarray:
    """Eventos 1/-1/0 da variante MOM sobre candles 1m (timestamp datetime)."""
    cfg = CONFIG if config is None else config
    tf = int(cfg["tf"])
    frame = candles.copy()
    ts = frame["timestamp"]
    if not pd.api.types.is_datetime64_any_dtype(ts):
        frame["timestamp"] = pd.to_datetime(ts, format="ISO8601", utc=True, errors="raise")
    bars = bars_of(frame, tf)
    close = bars["close"]
    roc = close.pct_change(int(cfg["lookback"]))
    desired_bars = (roc > float(cfg["thr"])).astype(np.int8)
    desired_1m = map_to_1m(
        frame, pd.Series(desired_bars, index=bars.index), tf
    ).fillna(0.0)
    desired = (desired_1m.to_numpy() > 0.5).astype(np.int8)
    prev = np.concatenate(([0], desired[:-1].astype(int)))
    events = np.zeros(len(desired), dtype=np.int8)
    events[(desired == 1) & (prev == 0)] = 1
    events[(desired == 0) & (prev == 1)] = -1
    return events


def events_and_backtest(
    candles: pd.DataFrame,
    fee_bps: float = FEE_BPS_P4,
    slip_bps: float = SLIP_BPS_P4,
    config: dict | None = None,
) -> tuple[np.ndarray, pd.DataFrame]:
    events = build_events(candles, config=config)
    bt = run_backtest(candles, events, fee_bps=fee_bps, slippage_bps=slip_bps)
    return events, bt


def frozen_criteria(metrics_p4: dict, net_stress_60bps: float) -> dict:
    """Aplica os criterios congelados de encerramento de P6-MOM.

    Menos de 10 operacoes completas classifica o resultado como INCONCLUSIVO
    sem flexibilizar nenhum criterio. Nao e calculado durante a janela.
    """
    trades = int(metrics_p4.get("trades", 0))
    net = float(metrics_p4.get("net_total_return", 0.0))
    bh = float(metrics_p4.get("buy_and_hold_net", 0.0))
    dd = float(metrics_p4.get("max_drawdown_net", 0.0))
    raw_pf = metrics_p4.get("profit_factor_net")
    pf = float(raw_pf) if raw_pf is not None else float("nan")
    stress = float(net_stress_60bps)
    checks = {
        "net_positive_after_p4": bool(net > 0.0),
        "net_above_buy_and_hold": bool(net > bh),
        "max_drawdown_not_below_limit": bool(dd >= RISK_LIMIT_DD),
        "profit_factor_above_1": bool(pf > 1.0),
        "min_complete_trades": bool(trades >= MIN_COMPLETE_TRADES),
        "stress_60bps_positive": bool(stress > 0.0),
    }
    if trades < MIN_COMPLETE_TRADES:
        verdict = "INCONCLUSIVO"
    elif all(checks.values()):
        verdict = "APROVADO"
    else:
        verdict = "REPROVADO"
    return {
        "checks": checks,
        "trades": trades,
        "net_total_return": net,
        "buy_and_hold_net": bh,
        "max_drawdown_net": dd,
        "profit_factor_net": None if not np.isfinite(pf) else pf,
        "net_stress_60bps": stress,
        "risk_limit_drawdown_net": RISK_LIMIT_DD,
        "min_complete_trades_required": MIN_COMPLETE_TRADES,
        "verdict": verdict,
    }
