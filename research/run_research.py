#!/usr/bin/env python3
"""Pesquisa quantitativa FVT — Convergencia Pai/Filho/Trindade.

Somente-leitura em relacao ao motor (src/convergencia), ao painel, ao CSV
original e aos testes. Reimplementa APENAS o aggregate do contexto Pai com
timeframe parametrizavel (para M5 vs M15), reconciliando que a variante 15m
reproduz exatamente os sinais do motor antes de qualquer comparacao.

Metodologia corrigida: os eventos crus (1/-1/0) sao passados diretamente a
run_backtest (contrato real da funcao). O wrapper events_to_position_targets de
scripts/run_backtest.py e evitado porque causa dupla conversao e engole as
saidas (verificado e documentado no relatorio).

Saida: research/out/research_results.json (numerics reproduziveis).
"""
from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CSV = ROOT / "data" / "raw" / "BTCUSDT_1m.csv"
OUT = ROOT / "research" / "out" / "research_results.json"
EXPECTED_SHA256 = "604835c55d98319cf6f26516040f6f285e02152b6ee984238c0d3359c2dbde41"

sys.path.insert(0, str(ROOT / "src"))
import convergencia.strategy as strategy_module
from convergencia.backtest import run_backtest
from convergencia.strategy import StrategyConfig, generate_strategy_signals


# --------------------------------------------------------------------------- #
# Utilidades
# --------------------------------------------------------------------------- #
def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def parent_bars(frame: pd.DataFrame, config: StrategyConfig, timeframe: int) -> pd.DataFrame:
    """Aggrega candles 1m em barras `timeframe`min COMPLETAS e calcula direcao Pai.

    Reproduz exatamente a regra do motor (_parent_direction): EMA span rapida/lenta,
    alta/baixa exigem fast >/< fast.shift(3). Disponivel apenas apos o fecho da barra.
    """
    indexed = frame.set_index("timestamp")
    rule = f"{timeframe}min"
    aggregation = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    if "quote_volume" in frame.columns:
        aggregation["quote_volume"] = "sum"
    parent = indexed.resample(rule, label="left", closed="left").agg(aggregation)
    parent["bar_count"] = indexed["close"].resample(rule, label="left", closed="left").count()
    parent = parent.loc[parent["bar_count"] == timeframe].copy()
    if parent.empty:
        raise ValueError(f"Sem barras completas de {timeframe}min para contexto Pai.")
    close = pd.to_numeric(parent["close"], errors="coerce")
    fast = close.ewm(span=config.parent_fast, adjust=False, min_periods=config.parent_fast).mean()
    slow = close.ewm(span=config.parent_slow, adjust=False, min_periods=config.parent_slow).mean()
    bullish = (close > fast) & (fast > slow) & (fast > fast.shift(3))
    bearish = (close < fast) & (fast < slow) & (fast < fast.shift(3))
    direction = pd.Series(0, index=parent.index, dtype="int8")
    direction.loc[bullish] = 1
    direction.loc[bearish] = -1
    return pd.DataFrame({
        "available_at": parent.index + pd.Timedelta(minutes=timeframe),
        "parent_direction": direction.to_numpy(),
        "parent_close": close.to_numpy(),
    }).sort_values("available_at").reset_index(drop=True)


def make_parent_builder(mode: str):
    """Builder de contexto Pai para o monkeypatch do motor (15m = motor original)."""
    original = strategy_module._parent_direction

    def build(frame: pd.DataFrame, config: StrategyConfig) -> pd.DataFrame:
        if mode == "15m":
            return original(frame, config)
        return parent_bars(frame, config, int(mode[:-1]))

    return build


def generate_features(candles: pd.DataFrame, mode: str, config: StrategyConfig) -> pd.DataFrame:
    original = strategy_module._parent_direction
    strategy_module._parent_direction = make_parent_builder(mode)
    try:
        return generate_strategy_signals(candles, config)
    finally:
        strategy_module._parent_direction = original


# --------------------------------------------------------------------------- #
# Metricas
# --------------------------------------------------------------------------- #
def max_drawdown(equity: pd.Series) -> float:
    values = equity.to_numpy(dtype="float64")
    if not len(values):
        return 0.0
    full = np.concatenate(([1.0], values))
    peaks = np.maximum.accumulate(full)
    return float(np.min(full / peaks - 1.0))


def trade_diagnostics(bt: pd.DataFrame) -> dict:
    """Reconstrue trades a partir da serie de posicao (long-only, posicao unica)."""
    pos = bt["position"].to_numpy(dtype=float) > 0.5
    prior = np.concatenate(([False], pos[:-1]))
    following = np.concatenate((pos[1:], [False]))
    starts = np.flatnonzero(pos & ~prior)
    ends = np.flatnonzero(pos & ~following)
    if len(starts) != len(ends):
        raise RuntimeError("Serie de posicao com trades nao casados")
    gross = bt["gross_return"].to_numpy(dtype=float)
    net = bt["net_return"].to_numpy(dtype=float)
    gross_trades, net_trades, durations = [], [], []
    for s, e in zip(starts, ends):
        gross_trades.append(float(np.prod(1.0 + gross[s:e + 1]) - 1.0))
        # Custo de entrada no intervalo anterior; custo de saida no ultimo intervalo segurado.
        w0 = max(int(s) - 1, 0)
        net_trades.append(float(np.prod(1.0 + net[w0:e + 1]) - 1.0))
        durations.append(int(e - s + 1))
    g = np.asarray(gross_trades, dtype=float)
    n = np.asarray(net_trades, dtype=float)
    gp = float(g[g > 0].sum()) if len(g) else 0.0
    gn = float(-g[g < 0].sum()) if len(g) else 0.0
    pf_gross = gp / gn if gn > 0 else (float("inf") if gp > 0 else float("nan"))
    nn = float(-n[n < 0].sum()) if len(n) else 0.0
    np_ = float(n[n > 0].sum()) if len(n) else 0.0
    pf_net = np_ / nn if nn > 0 else (float("inf") if np_ > 0 else float("nan"))
    return {
        "trades": int(len(starts)),
        "avg_holding_bars": float(np.mean(durations)) if durations else 0.0,
        "median_holding_bars": float(np.median(durations)) if durations else 0.0,
        "gross_win_rate": float(np.mean(g > 0)) if len(g) else 0.0,
        "net_win_rate": float(np.mean(n > 0)) if len(n) else 0.0,
        "mean_gross_trade": float(np.mean(g)) if len(g) else 0.0,
        "median_gross_trade": float(np.median(g)) if len(g) else 0.0,
        "mean_net_trade": float(np.mean(n)) if len(n) else 0.0,
        "median_net_trade": float(np.median(n)) if len(n) else 0.0,
        "profit_factor_gross": pf_gross,
        "profit_factor_net": pf_net,
        "best_net_trade": float(np.max(n)) if len(n) else 0.0,
        "worst_net_trade": float(np.min(n)) if len(n) else 0.0,
    }


DAYS_PER_YEAR = 365.0  # BTC negocia 24/7 (decisao 2, ciclo 2026-10-22)


def daily_returns_with_flat_days(equity: pd.Series, timestamps: pd.Series) -> pd.Series:
    """Retorno diario do equity incluindo dias em caixa (retorno zero).

    O backtest herda o RangeIndex do CSV (o tempo vive na coluna "timestamp"),
    entao os timestamps entram alinhados por rotulo. Dias de calendario sem
    barras herdam o ultimo equity (retorno 0), conforme a decisao 2 do ciclo
    2026-10-22 (memory/journal.md): caixa entra como zero, nunca e excluido.
    """
    if equity.empty:
        return pd.Series(dtype=float)
    ts = timestamps.reindex(equity.index)
    if ts.isna().any():
        raise ValueError(f"timestamps ausentes para {int(ts.isna().sum())} linhas do backtest")
    dias = pd.date_range(ts.iloc[0].normalize(), ts.iloc[-1].normalize(), freq="D")
    diario = equity.groupby(ts.dt.normalize()).last().reindex(dias).ffill()
    return diario.pct_change().dropna()


def metrics_block(
    bt: pd.DataFrame, window_opens: pd.Series, timestamps: pd.Series, cost_rate: float
) -> dict:
    equity = bt["equity"]
    pos = bt["position"]
    gross_equity = (1.0 + bt["gross_return"]).cumprod()
    diag = trade_diagnostics(bt)
    rets_dia = daily_returns_with_flat_days(equity, timestamps)
    media_dia = float(rets_dia.mean()) if len(rets_dia) else 0.0
    std_dia = float(rets_dia.std(ddof=1)) if len(rets_dia) >= 2 else 0.0
    sharpe_anual = (
        media_dia / std_dia * float(np.sqrt(DAYS_PER_YEAR)) if std_dia > 0.0 else 0.0
    )
    bh_gross = float(window_opens.iloc[-1] / window_opens.iloc[0] - 1.0) if len(window_opens) > 1 else 0.0
    bh_net = float((window_opens.iloc[-1] / window_opens.iloc[0]) * (1.0 - cost_rate) ** 2 - 1.0) if len(window_opens) > 1 else 0.0
    out = {
        "intervals": int(len(bt)),
        "entries": int((pos.diff().fillna(pos) > 0).sum()),
        "exits": int((pos.diff().fillna(0.0) < 0).sum()),
        "exposure_fraction": float(pos.mean()) if len(pos) else 0.0,
        "gross_total_return": float(gross_equity.iloc[-1] - 1.0) if len(gross_equity) else 0.0,
        "net_total_return": float(equity.iloc[-1] - 1.0) if len(equity) else 0.0,
        "max_drawdown_net": max_drawdown(equity),
        "max_drawdown_gross": max_drawdown(gross_equity),
        "sum_cost_returns": float(bt["costs"].sum()),
        "buy_and_hold_gross": bh_gross,
        "buy_and_hold_net": bh_net,
        "no_signal_return": 0.0,
        "strategy_minus_buyhold_net": (float(equity.iloc[-1] - 1.0) - bh_net) if len(equity) else 0.0,
        "daily_observations": int(len(rets_dia)),
        "sharpe_ratio_daily_mean": media_dia,
        "sharpe_ratio_daily_std": std_dia,
        "sharpe_ratio_annualized": sharpe_anual,
    }
    out.update(diag)
    return out


# --------------------------------------------------------------------------- #
# Experimentos
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class CostScenario:
    label: str
    fee_bps_per_side: float
    slippage_bps_per_side: float

    @property
    def round_trip_bps(self) -> float:
        return 2.0 * (self.fee_bps_per_side + self.slippage_bps_per_side)


COST_SCENARIOS = (
    CostScenario("ZERO", 0.0, 0.0),
    CostScenario("DEFAULT_30BPS_RT", 10.0, 5.0),   # 30 bps por operacao completa
    CostScenario("HIGH_50BPS_RT", 20.0, 5.0),
    CostScenario("EXTREME_100BPS_RT", 45.0, 5.0),
)

# Config original do motor (nao alterar).
ORIGINAL_CONFIG = StrategyConfig()

# Config "reduzida" declarada A PRIORI (janelas ~metade), sem otimizacao no teste.
REDUCED_CONFIG = StrategyConfig(
    parent_fast=10, parent_slow=25,
    child_fast=5, child_slow=12,
    fib_lookback=30, atr_window=7,
    volume_lookback=10, momentum_window=5, regime_window=30,
    relative_volume_min=1.2,
    min_regime_z=-2.5, max_regime_z=2.0,
)

# Split cronologico por linhas: 50% treino, 25% validacao, 25% teste final.
SPLIT_FRACS = {"train": 0.50, "validation": 0.25, "test": 0.25}


def run_one(features: pd.DataFrame, events: np.ndarray, scenario: CostScenario,
            window: slice | None = None) -> tuple[pd.DataFrame, dict]:
    frame = features if window is None else features.iloc[window]
    ev = events if window is None else events[window]
    bt = run_backtest(frame, ev, fee_bps=scenario.fee_bps_per_side,
                      slippage_bps=scenario.slippage_bps_per_side)
    opens = pd.to_numeric(frame["open"], errors="coerce")
    return bt, metrics_block(
        bt, opens, frame["timestamp"],
        (scenario.fee_bps_per_side + scenario.slippage_bps_per_side) / 10_000.0,
    )


def reconcile_full(features: pd.DataFrame) -> None:
    """Garante que o replay FULL reconstruido bate com signal do motor."""
    entry = (
        features["parent_direction"].eq(1)
        & features["child_direction"].eq(1)
        & features["fibonacci_confirmed"].fillna(False).astype(bool)
        & features["regime_acceptable"].fillna(False).astype(bool)
        & features["volume_confirmed"].fillna(False).astype(bool)
        & features["momentum_confirmed"].fillna(False).astype(bool)
    )
    exit_c = (
        features["parent_direction"].ne(1)
        | features["child_direction"].eq(-1)
        | features["normalized_slope"].lt(0)
    ).fillna(False)
    b = entry.to_numpy(dtype=bool)
    x = exit_c.to_numpy(dtype=bool)
    events = np.zeros(len(b), dtype=np.int8)
    in_pos = False
    for i in range(len(b)):
        if not in_pos and b[i]:
            events[i] = 1
            in_pos = True
        elif in_pos and x[i]:
            events[i] = -1
            in_pos = False
    established = pd.to_numeric(features["signal"], errors="raise").to_numpy(dtype=np.int8)
    if not np.array_equal(events, established):
        idx = int(np.flatnonzero(events != established)[0])
        raise RuntimeError(f"Reconciliacao FULL falhou na linha {idx}")


def main() -> int:
    digest = sha256_file(CSV)
    if digest != EXPECTED_SHA256:
        raise RuntimeError(f"SHA256 do CSV diverge: {digest}")
    candles = pd.read_csv(CSV)
    n = len(candles)
    bounds = {
        "train": (0, int(n * SPLIT_FRACS["train"])),
        "validation": (int(n * SPLIT_FRACS["train"]), int(n * (SPLIT_FRACS["train"] + SPLIT_FRACS["validation"]))),
        "test": (int(n * (SPLIT_FRACS["train"] + SPLIT_FRACS["validation"])), n),
    }
    ts = pd.to_datetime(candles["timestamp"], format="ISO8601", utc=True)
    split_meta = {
        k: {"start": ts.iloc[a].isoformat(), "end": ts.iloc[b - 1].isoformat(), "rows": b - a}
        for k, (a, b) in bounds.items()
    }

    results: dict = {
        "meta": {
            "csv_sha256": digest,
            "rows": n,
            "split_fracs": SPLIT_FRACS,
            "split_meta": split_meta,
            "cost_scenarios": [asdict(s) | {"round_trip_bps": s.round_trip_bps} for s in COST_SCENARIOS],
            "original_config": asdict(ORIGINAL_CONFIG),
            "reduced_config": asdict(REDUCED_CONFIG),
        },
        "bugs": {},
        "lookahead_checks": {},
        "variants": {},
    }

    # ---- Bug demonstration (double conversion) -------------------------------- #
    feats15 = generate_features(candles, "15m", ORIGINAL_CONFIG)
    reconcile_full(feats15)
    ev15 = feats15["signal"].to_numpy()

    def double_convert(events: np.ndarray) -> np.ndarray:
        targets = np.zeros(len(events), dtype="int8")
        state = 0
        for i, e in enumerate(events):
            if e == 1:
                state = 1
            elif e == -1:
                state = 0
            targets[i] = state
        return targets

    sc_default = COST_SCENARIOS[1]
    bt_bug, m_bug = run_one(feats15, double_convert(ev15), sc_default)
    bt_ok, m_ok = run_one(feats15, ev15, sc_default)
    results["bugs"]["double_conversion"] = {
        "description": (
            "scripts/run_backtest.py converte eventos em alvo (events_to_position_targets) e "
            "DEPOIS chama run_backtest, que ja converte eventos internamente. A saida -1 vira 0 "
            "no array e o loop interno interpreta 0 como 'manter estado': as saidas sao engolidas."
        ),
        "bugged": {k: m_bug[k] for k in ("entries", "exits", "exposure_fraction", "net_total_return", "max_drawdown_net")},
        "corrected": {k: m_ok[k] for k in ("entries", "exits", "exposure_fraction", "net_total_return", "max_drawdown_net")},
    }

    # ---- Lookahead / execucao / sobreposicao / liquidacao --------------------- #
    pos = bt_ok["position"].to_numpy(dtype=float)
    sig = feats15["signal"].to_numpy()
    # 1) Execucao no candle seguinte: position[i] deve ser 0 quando signal[i]==1 (entrada apos sinal).
    entry_rows = np.flatnonzero(sig == 1)
    exec_ok = bool((pos[entry_rows] == 0).all()) if len(entry_rows) else True
    # pos no candle apos a entrada deve ser 1
    exec_next_ok = bool((pos[np.minimum(entry_rows + 1, len(pos) - 1)] == 1).all()) if len(entry_rows) else True
    # 2) Sem sobreposicao: posicao nunca negativa; entra so se flat (signal so emite 1 quando flat).
    overlap_ok = bool((pos >= 0).all() and (pos <= 1).all())
    # entradas consecutivas sem saida entre elas?
    events_seq = sig[np.isin(sig, [-1, 1])]
    alt_ok = bool(len(events_seq) == 0 or np.all(np.diff(events_seq.astype(int)) == -2) or np.all(np.abs(np.diff(events_seq.astype(int))) == 2))
    # 3) Liquidacao final: so e relevante se a posicao estiver ABERTA no fim dos dados.
    # O motor força position.iloc[-1]=0; o turnover dessa ultima linha e puxado por
    # turnover.shift(-1) para a penultima linha RETIDA, portanto o custo NAO se perde
    # (ver run_backtest cobra entrada+liquidacao = 2 lados quando ha posicao aberta ao fim).
    # No dataset real entries==exits (ultimo trade ja fecha) -> posicao termina PLANA,
    # logo nao ha liquidacao a cobrar (no-o). O check anterior confundia esse no-op com
    # um "custo gratis" e gerava um falso viés de 15 bps; corrigido separando os casos.
    last_pos_in_bt = float(pos[-1]) if len(pos) else 0.0
    liq_cost = (sc_default.fee_bps_per_side + sc_default.slippage_bps_per_side) / 10_000.0
    # Sinal termina com posicao aberta? (mais compras que saidas no fluxo de eventos)
    signal_open_at_end = int((ev15 == 1).sum()) > int((ev15 == -1).sum())
    # Prova sintetica: com posicao ABERTA no fim, o motor deve cobrar 2 lados (entrada+liq).
    _open_candles = pd.DataFrame({"open": [100.0, 100.0, 110.0, 110.0]})
    _bt_liq = run_backtest(_open_candles, [1, 0, 0, 0],
                           fee_bps=sc_default.fee_bps_per_side,
                           slippage_bps=sc_default.slippage_bps_per_side)
    liq_charged_when_open = bool(np.isclose(float(_bt_liq["costs"].sum()), 2.0 * liq_cost))
    # 4) Perturbacao de lookahead: alterar candle final nao deve mudar sinais anteriores.
    cut = n - 5
    pert = candles.copy()
    pert.loc[cut:, ["open", "high", "low", "close"]] *= 1.5
    pert.loc[cut:, "volume"] *= 3.0
    if "quote_volume" in pert.columns:
        pert.loc[cut:, "quote_volume"] *= 3.0
    feats_pert = generate_features(pert, "15m", ORIGINAL_CONFIG)
    cols = ["parent_direction", "child_direction", "fib_618", "regime_zscore",
            "relative_volume", "normalized_slope", "normalized_acceleration", "signal"]
    la_ok = bool(np.allclose(
        feats15.loc[:cut - 1, cols].select_dtypes(include=[np.number]).to_numpy(dtype=float),
        feats_pert.loc[:cut - 1, cols].select_dtypes(include=[np.number]).to_numpy(dtype=float),
        equal_nan=True,
    ))
    results["lookahead_checks"] = {
        "entry_position_same_bar_is_flat": exec_ok,
        "entry_position_next_bar_is_long": exec_next_ok,
        "position_bounded_0_1_no_short": overlap_ok,
        "events_alternate_no_overlap": alt_ok,
        "final_position_in_result_series": last_pos_in_bt,
        "final_position_signal_open_at_end": signal_open_at_end,
        "final_forced_liquidation_cost_charged_when_open": liq_charged_when_open,
        "final_liquidation_cost_free_bias_bps": 0.0 if liq_charged_when_open else liq_cost * 10_000.0,
        "future_perturbation_does_not_change_past": la_ok,
    }

    # ---- Variantes: M15 vs M5, original vs reduzido --------------------------- #
    variants = {
        "M15_original": (feats15, ev15),
        "M5_original": None,
        "M15_reduced": None,
        "M5_reduced": None,
    }
    feats5 = generate_features(candles, "5m", ORIGINAL_CONFIG)
    reconcile_full(feats5)
    variants["M5_original"] = (feats5, feats5["signal"].to_numpy())
    feats15r = generate_features(candles, "15m", REDUCED_CONFIG)
    reconcile_full(feats15r)
    variants["M15_reduced"] = (feats15r, feats15r["signal"].to_numpy())
    feats5r = generate_features(candles, "5m", REDUCED_CONFIG)
    reconcile_full(feats5r)
    variants["M5_reduced"] = (feats5r, feats5r["signal"].to_numpy())

    for name, (feats, ev) in variants.items():
        per_scenario = {}
        for sc in COST_SCENARIOS:
            _, full = run_one(feats, ev, sc)
            per_split = {}
            for split_name, (a, b) in bounds.items():
                _, m = run_one(feats, ev, sc, window=slice(a, b))
                per_split[split_name] = m
            per_scenario[sc.label] = {"full": full, "by_split": per_split}
        results["variants"][name] = {
            "buy_events": int((ev == 1).sum()),
            "exit_events": int((ev == -1).sum()),
            "cost_scenarios": per_scenario,
        }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(_jsonable(results), indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    _print_summary(results)
    print(f"\nResultados gravados em: {OUT}")
    return 0


def _jsonable(obj):
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        return float(obj) if np.isfinite(obj) else None
    if isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    if pd.isna(obj):
        return None
    return obj


def _pct(x: float) -> str:
    return f"{x * 100:8.3f}%"


def _print_summary(results: dict) -> None:
    print("=" * 78)
    print("BUG DE DUPLA CONVERSAO (scripts/run_backtest.py)")
    b = results["bugs"]["double_conversion"]
    print("  BUGGED  :", b["bugged"])
    print("  CORRECTED:", b["corrected"])
    print("=" * 78)
    print("CHECKS DE CAUSALIDADE/EXECUCAO")
    for k, v in results["lookahead_checks"].items():
        print(f"  {k}: {v}")
    print("=" * 78)
    hdr = f"{'variante':16s} {'cenario':18s} {'split':10s} {'trades':>6s} {'expos%':>8s} {'bruto%':>9s} {'liquido%':>9s} {'maxDD%':>8s} {'PF_liq':>7s} {'win%':>6s}"
    print(hdr)
    for name, data in results["variants"].items():
        for sc_label, sc_data in data["cost_scenarios"].items():
            blocks = [("FULL", sc_data["full"])] + list(sc_data["by_split"].items())
            for split_name, m in blocks:
                pf = m["profit_factor_net"]
                pf_s = f"{pf:7.2f}" if np.isfinite(pf) else "    inf"
                print(
                    f"{name:16s} {sc_label:18s} {split_name:10s} "
                    f"{m['trades']:6d} {m['exposure_fraction']*100:7.3f}% "
                    f"{m['gross_total_return']*100:8.3f}% {m['net_total_return']*100:8.3f}% "
                    f"{m['max_drawdown_net']*100:7.3f}% {pf_s} {m['net_win_rate']*100:5.1f}%"
                )


if __name__ == "__main__":
    raise SystemExit(main())
