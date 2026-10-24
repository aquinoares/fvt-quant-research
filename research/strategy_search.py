#!/usr/bin/env python3
"""Busca de estrategias com retorno liquido positivo no BTCUSDT 1m (dev apenas).

Uso: .venv/Scripts/python.exe research/strategy_search.py

Regras fixas deste script:
- Lê apenas as primeiras 97.200 linhas do CSV (nrows); o bloco de teste
  [97200, 129600) nunca é lido nem calculado.
- Motor real: convergencia.backtest.run_backtest (eventos 1/-1/0, execução em
  open t+1, custo por lado = (fee+slip)/1e4). Cenário principal P4 = 10+5
  bps/lado (30 bps RT); stress posterior 20+10 bps/lado (60 bps RT).
- Métricas: mesmas funções de research/run_research.py (trade_diagnostics,
  max_drawdown, metrics_block) para garantir comparabilidade com o relatório.
- Protocolo de seleção (declarado antes de rodar): onda 1 gera a grade; o
  shortlist é ordenado APENAS por métricas de treino (retorno líquido com
  filtro de nº mínimo de trades); validação é avaliada somente para os
  candidatos do shortlist; vencedor = melhor min(treino, validação) entre os
  aprovados nos critérios (líquido > 0, PF >= 1 nos dois períodos, trades
  mínimos, DD de validação controlado).
- Sinais causais: indicadores usam apenas dados até o fechamento da barra;
  execução sempre na abertura seguinte (motor). Check de prefixo re-confirma
  a causalidade do vencedor.
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CSV = ROOT / "data" / "raw" / "BTCUSDT_1m.csv"
EXPECTED_SHA256 = "604835c55d98319cf6f26516040f6f285e02152b6ee984238c0d3359c2dbde41"
DEV_ROWS = 97_200
TRAIN_END = 64_800

sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "research"))
from convergencia.backtest import run_backtest  # noqa: E402
import run_research as rr  # noqa: E402

FEE_P4, SLIP_P4 = 10.0, 5.0
COST_RATE_P4 = (FEE_P4 + SLIP_P4) / 10_000.0


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def bars_of(frame: pd.DataFrame, tf: int) -> pd.DataFrame:
    indexed = frame.set_index("timestamp")
    if tf == 1:
        out = indexed[["open", "high", "low", "close", "volume"]].copy()
        return out
    rule = f"{tf}min"
    agg = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    b = indexed.resample(rule, label="left", closed="left").agg(agg)
    cnt = indexed["close"].resample(rule, label="left", closed="left").count()
    return b.loc[cnt == tf].copy()


def map_to_1m(frame: pd.DataFrame, series: pd.Series, tf: int) -> pd.Series:
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


def rsi_wilder(close: pd.Series, n: int) -> pd.Series:
    delta = close.diff()
    up = delta.clip(lower=0.0)
    dn = (-delta).clip(lower=0.0)
    au = up.ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean()
    ad = dn.ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean()
    with np.errstate(divide="ignore", invalid="ignore"):
        r = 100.0 - 100.0 / (1.0 + au / ad)
    return r.replace([np.inf, -np.inf], 100.0)


def atr_wilder(bars: pd.DataFrame, n: int = 14) -> pd.Series:
    pc = bars["close"].shift(1)
    tr = pd.concat(
        [
            bars["high"] - bars["low"],
            (bars["high"] - pc).abs(),
            (bars["low"] - pc).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean()


def state_machine(entry: np.ndarray, exit_: np.ndarray) -> np.ndarray:
    n = len(entry)
    out = np.zeros(n, dtype=np.int8)
    s = 0
    for i in range(n):
        if s == 0:
            if entry[i]:
                s = 1
        elif exit_[i]:
            s = 0
        out[i] = s
    return out


def desired_and_events(frame: pd.DataFrame, cfg: dict) -> tuple[np.ndarray, dict]:
    tf = int(cfg["tf"])
    bars = bars_of(frame, tf)
    close, high, low, opn, vol = (bars[c] for c in ("close", "high", "low", "open", "volume"))
    fam = cfg["family"]
    info: dict = {}

    if fam == "ema_cross":
        ef = close.ewm(span=cfg["fast"], adjust=False, min_periods=cfg["fast"]).mean()
        es = close.ewm(span=cfg["slow"], adjust=False, min_periods=cfg["slow"]).mean()
        desired_bars = (ef > es).astype(np.int8)
    elif fam == "momentum":
        roc = close.pct_change(cfg["lookback"])
        desired_bars = (roc > cfg["thr"]).astype(np.int8)
    elif fam == "donchian":
        entry = close > high.shift(1).rolling(cfg["n"]).max()
        exit_ = close < low.shift(1).rolling(cfg["m"]).min()
        desired_bars = state_machine(entry.fillna(False).to_numpy(bool), exit_.fillna(False).to_numpy(bool))
    elif fam == "zscore":
        sma = close.rolling(cfg["n"]).mean()
        sd = close.rolling(cfg["n"]).std()
        z = (close - sma) / sd
        entry = z < -cfg["k"]
        exit_ = z > cfg["kexit"]
        desired_bars = state_machine(entry.fillna(False).to_numpy(bool), exit_.fillna(False).to_numpy(bool))
    elif fam == "rsi_fade":
        r = rsi_wilder(close, cfg["n"])
        entry = r < cfg["kbuy"]
        exit_ = r > cfg["ksell"]
        desired_bars = state_machine(entry.fillna(False).to_numpy(bool), exit_.fillna(False).to_numpy(bool))
    elif fam == "boll":
        sma = close.rolling(cfg["n"]).mean()
        sd = close.rolling(cfg["n"]).std()
        entry = close < sma - cfg["k"] * sd
        exit_ = close > sma
        desired_bars = state_machine(entry.fillna(False).to_numpy(bool), exit_.fillna(False).to_numpy(bool))
    elif fam == "atr_trend":
        sma = close.rolling(cfg["n"]).mean()
        atr = atr_wilder(bars, 14)
        entry = close > sma + cfg["k"] * atr
        exit_ = close < sma
        desired_bars = state_machine(entry.fillna(False).to_numpy(bool), exit_.fillna(False).to_numpy(bool))
    elif fam == "volume":
        rvol = vol / vol.rolling(cfg["n"]).mean()
        entry = (rvol > cfg["thr"]) & (close > opn)
        if cfg["mode"] == "revbar":
            exit_ = close < opn
        else:
            exit_ = rvol < 1.0
        desired_bars = state_machine(entry.fillna(False).to_numpy(bool), exit_.fillna(False).to_numpy(bool))
    elif fam == "dip":
        sma = close.rolling(cfg["sma_n"]).mean()
        r = rsi_wilder(close, cfg["rsi_n"])
        trend = close > sma
        entry = trend & (r < cfg["kbuy"])
        exit_ = (~trend) | (r > cfg["ksell"])
        desired_bars = state_machine(entry.fillna(False).to_numpy(bool), exit_.fillna(False).to_numpy(bool))
    else:
        raise ValueError(f"familia desconhecida: {fam}")

    desired_1m = map_to_1m(frame, pd.Series(desired_bars, index=bars.index), tf).fillna(0.0)
    desired = (desired_1m.to_numpy() > 0.5).astype(np.int8)
    prev = np.concatenate(([0], desired[:-1].astype(int)))
    events = np.zeros(len(desired), dtype=np.int8)
    events[(desired == 1) & (prev == 0)] = 1
    events[(desired == 0) & (prev == 1)] = -1
    info["bars"] = len(bars)
    return events, info


def period_metrics(candles: pd.DataFrame, events: np.ndarray, a: int, b: int) -> tuple[dict, pd.DataFrame]:
    sl = candles.iloc[a:b].reset_index(drop=True)
    ev = events[a:b]
    bt = run_backtest(sl, ev, fee_bps=FEE_P4, slippage_bps=SLIP_P4)
    ts = candles["timestamp"].iloc[a:b].reset_index(drop=True)
    opens = sl["open"]
    m = rr.metrics_block(bt, opens, ts, COST_RATE_P4)
    return m, bt


def shortlist_row(cfg: dict, m: dict) -> dict:
    return {
        "family": cfg["family"],
        "tf": cfg["tf"],
        "params": json.dumps({k: v for k, v in cfg.items() if k not in ("family", "tf")}, sort_keys=True),
        "net": m["net_total_return"],
        "pf": m["profit_factor_net"],
        "maxdd": m["max_drawdown_net"],
        "trades": m["trades"],
        "win": m["net_win_rate"],
        "costs": m["sum_cost_returns"],
        "exposure": m["exposure_fraction"],
        "best_trade": m["best_net_trade"],
        "worst_trade": m["worst_net_trade"],
    }


def main() -> int:
    digest = sha256_file(CSV)
    if digest != EXPECTED_SHA256:
        raise RuntimeError(f"SHA256 do CSV diverge: {digest}")
    candles = pd.read_csv(CSV, nrows=DEV_ROWS)
    if len(candles) != DEV_ROWS:
        raise RuntimeError(f"Esperado {DEV_ROWS} linhas, obtido {len(candles)}")
    candles["timestamp"] = pd.to_datetime(candles["timestamp"], format="ISO8601", utc=True)
    if not candles["timestamp"].is_monotonic_increasing:
        raise RuntimeError("Timestamps fora de ordem no recorte dev")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    outdir = ROOT / "research" / "out" / f"strategy_search_{stamp}"
    outdir.mkdir(parents=True, exist_ok=False)

    wave1: list[dict] = []
    for tf in (1, 5, 15, 60, 240):
        for fast, slow in ((5, 20), (8, 34), (10, 50), (12, 48), (20, 80), (20, 100), (50, 200)):
            wave1.append({"family": "ema_cross", "tf": tf, "fast": fast, "slow": slow})
    for tf in (15, 60, 240):
        for lb, thr in ((12, 0.0), (24, 0.0), (48, 0.003), (96, 0.005)):
            wave1.append({"family": "momentum", "tf": tf, "lookback": lb, "thr": thr})
    for tf in (15, 60, 240):
        for n in (20, 55):
            for m_ in (10, 20):
                wave1.append({"family": "donchian", "tf": tf, "n": n, "m": m_})
    for tf in (5, 15, 60):
        for n in (60, 120):
            for k in (1.5, 2.0, 2.5):
                wave1.append({"family": "zscore", "tf": tf, "n": n, "k": k, "kexit": -0.25})
    for tf in (5, 15, 60):
        for kb, ks in ((20, 50), (30, 50), (30, 60)):
            wave1.append({"family": "rsi_fade", "tf": tf, "n": 14, "kbuy": kb, "ksell": ks})
    for tf in (5, 15, 60):
        for n in (20, 55):
            for k in (2.0, 2.5):
                wave1.append({"family": "boll", "tf": tf, "n": n, "k": k})
    for tf in (15, 60):
        for n in (50, 100):
            for k in (1.5, 2.0, 2.5):
                wave1.append({"family": "atr_trend", "tf": tf, "n": n, "k": k})
    for tf in (1, 5, 15):
        for thr in (2.0, 3.0):
            for mode in ("revbar", "rvol"):
                wave1.append({"family": "volume", "tf": tf, "n": 30, "thr": thr, "mode": mode})
    for tf in (15, 60):
        for sma_n in (100, 200):
            for kb, ks in ((25, 55), (30, 60)):
                wave1.append({"family": "dip", "tf": tf, "sma_n": sma_n, "rsi_n": 14, "kbuy": kb, "ksell": ks})

    def cfg_id(cfg: dict) -> str:
        return hashlib.sha1(json.dumps(cfg, sort_keys=True).encode()).hexdigest()[:10]

    results: dict[str, dict] = {}
    train_cache: dict[str, tuple[dict, np.ndarray]] = {}

    def eval_train(cfg: dict) -> tuple[dict, np.ndarray]:
        cid = cfg_id(cfg)
        if cid not in train_cache:
            events, _ = desired_and_events(candles, cfg)
            m_tr, _ = period_metrics(candles, events, 0, TRAIN_END)
            train_cache[cid] = (m_tr, events)
        return train_cache[cid]

    for cfg in wave1:
        cid = cfg_id(cfg)
        m_tr, events = eval_train(cfg)
        results[cid] = {"cfg": cfg, "train": m_tr, "val": None, "events": events}

    rows = []
    for cid, r in results.items():
        m = r["train"]
        rows.append({"id": cid, "wave": 1, **shortlist_row(r["cfg"], m)})
    df_tr = pd.DataFrame(rows).sort_values("net", ascending=False)

    MIN_TRADES_TRAIN = 3
    elig = df_tr[df_tr["trades"] >= MIN_TRADES_TRAIN]
    shortlist_ids = list(elig.head(15)["id"]) + list(df_tr.head(5)["id"])
    shortlist_ids = list(dict.fromkeys(shortlist_ids))

    families = {results[cid]["cfg"]["family"] for cid in shortlist_ids}
    wave2: list[dict] = []
    if "ema_cross" in families:
        for tf in (60, 240):
            for fast, slow in ((3, 15), (10, 30), (15, 60), (25, 100), (16, 64), (40, 160)):
                wave2.append({"family": "ema_cross", "tf": tf, "fast": fast, "slow": slow})
    if "donchian" in families:
        for tf in (15, 60, 240):
            for n in (34, 89):
                for m_ in (21, 55):
                    wave2.append({"family": "donchian", "tf": tf, "n": n, "m": m_})
    if "zscore" in families:
        for tf in (5, 15, 60):
            for n in (90, 180):
                for k in (2.0, 2.5):
                    wave2.append({"family": "zscore", "tf": tf, "n": n, "k": k, "kexit": 0.0})
    if "rsi_fade" in families:
        for tf in (5, 15, 60):
            for kb, ks in ((15, 50), (25, 55)):
                wave2.append({"family": "rsi_fade", "tf": tf, "n": 14, "kbuy": kb, "ksell": ks})
    if "boll" in families:
        for tf in (5, 15, 60):
            for n in (34,):
                for k in (2.2, 2.5, 3.0):
                    wave2.append({"family": "boll", "tf": tf, "n": n, "k": k})
    if "atr_trend" in families:
        for tf in (15, 60):
            for n in (75, 150):
                for k in (2.0, 2.5):
                    wave2.append({"family": "atr_trend", "tf": tf, "n": n, "k": k})
    if "volume" in families:
        for tf in (1, 5, 15):
            for thr in (2.5, 4.0):
                for mode in ("revbar", "rvol"):
                    wave2.append({"family": "volume", "tf": tf, "n": 30, "thr": thr, "mode": mode})
    if "dip" in families:
        for tf in (15, 60):
            for sma_n in (150, 300):
                for kb, ks in ((20, 50), (28, 58)):
                    wave2.append({"family": "dip", "tf": tf, "sma_n": sma_n, "rsi_n": 14, "kbuy": kb, "ksell": ks})
    if "momentum" in families:
        for tf in (60, 240):
            for lb, thr in ((192, 0.01), (48, 0.0)):
                wave2.append({"family": "momentum", "tf": tf, "lookback": lb, "thr": thr})

    for cfg in wave2:
        cid = cfg_id(cfg)
        if cid in results:
            continue
        m_tr, events = eval_train(cfg)
        results[cid] = {"cfg": cfg, "train": m_tr, "val": None, "events": events}

    rows2 = []
    for cid, r in results.items():
        m = r["train"]
        rows2.append({"id": cid, **shortlist_row(r["cfg"], m)})
    df_all = pd.DataFrame(rows2).sort_values("net", ascending=False)
    elig2 = df_all[df_all["trades"] >= MIN_TRADES_TRAIN]
    short2 = list(elig2.head(15)["id"]) + list(df_all.head(5)["id"])
    shortlist_ids = list(dict.fromkeys(shortlist_ids + short2))

    for cid in shortlist_ids:
        r = results[cid]
        if r["val"] is None:
            m_val, _ = period_metrics(candles, r["events"], TRAIN_END, DEV_ROWS)
            r["val"] = m_val

    rec_rows = []
    for cid, r in results.items():
        m_tr, m_va = r["train"], r["val"]
        base = {"id": cid, "wave": 2 if cid not in {cfg_id(c) for c in wave1} else 1, **shortlist_row(r["cfg"], m_tr)}
        if m_va is not None:
            base.update(
                {
                    "val_net": m_va["net_total_return"],
                    "val_pf": m_va["profit_factor_net"],
                    "val_maxdd": m_va["max_drawdown_net"],
                    "val_trades": m_va["trades"],
                    "val_win": m_va["net_win_rate"],
                    "val_costs": m_va["sum_cost_returns"],
                }
            )
        else:
            base.update({k: np.nan for k in ("val_net", "val_pf", "val_maxdd", "val_trades", "val_win", "val_costs")})
        rec_rows.append(base)
    df = pd.DataFrame(rec_rows)

    def passes(row) -> bool:
        if pd.isna(row["val_net"]):
            return False
        return bool(
            row["net"] > 0
            and row["val_net"] > 0
            and row["pf"] >= 1.0
            and row["val_pf"] >= 1.0
            and row["trades"] >= MIN_TRADES_TRAIN
            and row["val_trades"] >= 2
            and row["val_maxdd"] >= -0.12
        )

    df["pass"] = df.apply(passes, axis=1)
    df["score"] = np.minimum(df["net"].fillna(-9e9), df["val_net"].fillna(-9e9))

    quarters = []
    qbounds = [(0, 16200), (16200, 32400), (32400, 48600), (48600, 64800)]
    passers = df[df["pass"]].sort_values("score", ascending=False)
    fallback = df[~df["pass"] & df["val_net"].notna()].sort_values("score", ascending=False)
    chosen_pool = pd.concat([passers, fallback]).drop_duplicates(subset="id")

    top_rows = []
    for _, row in chosen_pool.head(8).iterrows():
        r = results[row["id"]]
        for qa, qb in qbounds:
            mq, _ = period_metrics(candles, r["events"], qa, qb)
            quarters.append({"id": row["id"], "quarter": f"train_q{qa // 16200 + 1}", "net": mq["net_total_return"], "pf": mq["profit_factor_net"], "trades": mq["trades"]})
        m_dev, bt_dev = period_metrics(candles, r["events"], 0, DEV_ROWS)
        top_rows.append((row, r, m_dev, bt_dev))
        for qa, qb in ((64800, 81000), (81000, 97200)):
            mq, _ = period_metrics(candles, r["events"], qa, qb)
            quarters.append({"id": row["id"], "quarter": f"val_q{(qa - 64800) // 16200 + 1}", "net": mq["net_total_return"], "pf": mq["profit_factor_net"], "trades": mq["trades"]})
    df_quarters = pd.DataFrame(quarters)

    stress = []
    for _, row in chosen_pool.head(8).iterrows():
        r = results[row["id"]]
        for a, b, tag in ((0, TRAIN_END, "train"), (TRAIN_END, DEV_ROWS, "val")):
            sl = candles.iloc[a:b].reset_index(drop=True)
            bt = run_backtest(sl, r["events"][a:b], fee_bps=20.0, slippage_bps=10.0)
            stress.append({"id": row["id"], "period": tag, "net_60bps": float(bt["equity"].iloc[-1] - 1.0)})
    df_stress = pd.DataFrame(stress)

    winner = None
    if len(passers):
        winner = passers.iloc[0]
    elif len(fallback):
        winner = fallback.iloc[0]

    eq_cols = {}
    if winner is not None:
        wcfg = results[winner["id"]]["cfg"]
        wev = results[winner["id"]]["events"]
        for k in range(4):
            cid = chosen_pool.iloc[k]["id"] if k < len(chosen_pool) else None
            if cid is None:
                continue
            _, btd = period_metrics(candles, results[cid]["events"], 0, DEV_ROWS)
            eq_cols[f"equity_{cid}"] = btd["equity"].to_numpy()
        dev_eq = pd.DataFrame(eq_cols)
        dev_eq.insert(0, "row", dev_eq.index)
        ts_dev = candles["timestamp"].iloc[: len(dev_eq)].reset_index(drop=True)
        dev_eq.insert(0, "timestamp", ts_dev)
        dev_eq.to_csv(outdir / "equity_dev_top.csv", index=False)

        w_events = wev
        w_prefix = []
        for cut in (24300, 48600, 72900):
            ev_cut, _ = desired_and_events(candles.iloc[:cut].reset_index(drop=True), wcfg)
            w_prefix.append({"cut": cut, "events_equal": bool(np.array_equal(ev_cut, w_events[:cut]))})
        df_prefix = pd.DataFrame(w_prefix)
        df_prefix.to_csv(outdir / "winner_prefix_check.csv", index=False)

        w_m_tr, w_bt_tr = period_metrics(candles, w_events, 0, TRAIN_END)
        w_m_va, w_bt_va = period_metrics(candles, w_events, TRAIN_END, DEV_ROWS)
        (outdir / "winner_events.csv").write_text(
            "row,timestamp,event\n"
            + "\n".join(
                f"{i},{candles['timestamp'].iloc[i].isoformat()},{int(w_events[i])}"
                for i in np.flatnonzero(w_events)
            ),
            encoding="utf-8",
        )
    else:
        w_m_tr = w_m_va = None

    df.to_csv(outdir / "candidates.csv", index=False)
    df_quarters.to_csv(outdir / "top_quarters.csv", index=False)
    df_stress.to_csv(outdir / "top_stress_60bps.csv", index=False)

    bh = {}
    for tag, (a, b) in (("train", (0, TRAIN_END)), ("val", (TRAIN_END, DEV_ROWS)), ("dev", (0, DEV_ROWS))):
        opens = candles["open"].iloc[a:b]
        bh[tag] = float((opens.iloc[-1] / opens.iloc[0]) * (1.0 - COST_RATE_P4) ** 2 - 1.0)

    meta = {
        "generated_utc": stamp,
        "csv_sha256": digest,
        "dev_rows": DEV_ROWS,
        "train_range": [0, TRAIN_END],
        "val_range": [TRAIN_END, DEV_ROWS],
        "test_block_untouched": True,
        "cost_p4_per_side_bps": FEE_P4 + SLIP_P4,
        "n_configs_total": int(len(df)),
        "n_val_evaluated": int(df["val_net"].notna().sum()),
        "n_pass": int(df["pass"].sum()),
        "buy_and_hold_net": bh,
        "m15_original_reference": {
            "source": "research/out/crossovers_dev_20261023T022656Z/summary.md",
            "train_net": -0.13117,
            "val_net": -0.05118,
            "dev_net": -0.17564,
            "dev_trades": 74,
        },
        "winner_id": None if winner is None else winner["id"],
        "winner_pass": None if winner is None else bool(winner["pass"]),
        "winner_cfg": None if winner is None else results[winner["id"]]["cfg"],
        "winner_train": None if w_m_tr is None else {k: (None if isinstance(w_m_tr[k], float) and np.isinf(w_m_tr[k]) else w_m_tr[k]) for k in ("net_total_return", "profit_factor_net", "max_drawdown_net", "trades", "net_win_rate", "sum_cost_returns", "exposure_fraction", "best_net_trade", "worst_net_trade")},
        "winner_val": None if w_m_va is None else {k: (None if isinstance(w_m_va[k], float) and np.isinf(w_m_va[k]) else w_m_va[k]) for k in ("net_total_return", "profit_factor_net", "max_drawdown_net", "trades", "net_win_rate", "sum_cost_returns", "exposure_fraction", "best_net_trade", "worst_net_trade")},
    }
    (outdir / "best_config.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    top20 = df.sort_values("score", ascending=False).head(20)
    md = []
    md.append("# Busca de estrategias — BTCUSDT 1m, desenvolvimento (linhas 0..97199)")
    md.append("")
    md.append(f"- Gerado (UTC): {stamp}")
    md.append(f"- CSV SHA-256 `{digest}`; apenas nrows=97200 lidos; bloco de teste [97200,129600) intocado")
    md.append("- Motor: `convergencia.backtest.run_backtest` (execucao open t+1, long-only); custos P4 = 10+5 bps/lado (30 bps RT); metricas = funcoes de `research/run_research.py`")
    md.append(f"- Configuracoes testadas: **{len(df)}** (ondas 1+2); validacao avaliada apenas para {int(df['val_net'].notna().sum())} do shortlist (protocolo: selecao por treino)")
    md.append(f"- Aprovados nos criterios (liq>0, PF>=1 treino+val, trades min, DD val >= -12%): **{int(df['pass'].sum())}**")
    md.append("")
    md.append("## Ranking (score = min(treino, validacao) liquido)")
    md.append("")
    md.append("| # | id | familia | tf | params | treino liq | treino PF | val liq | val PF | val DD | trades tr/val | pass |")
    md.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for i, (_, row) in enumerate(top20.iterrows(), 1):
        md.append(
            f"| {i} | {row['id']} | {row['family']} | {row['tf']} | {row['params']} "
            f"| {row['net']*100:.3f}% | {row['pf']:.2f} | {row['val_net']*100:.3f}% | {row['val_pf']:.2f} "
            f"| {row['val_maxdd']*100:.2f}% | {int(row['trades'])}/{int(row['val_trades'])} | {'SIM' if row['pass'] else 'nao'} |"
        )
    md.append("")
    if winner is not None:
        wid = winner["id"]
        wcfg = results[wid]["cfg"]
        md.append("## Melhor candidato")
        md.append("")
        md.append(f"- id `{wid}` | familia `{wcfg['family']}` | config: `{json.dumps(wcfg, sort_keys=True)}`")
        pass_txt = "SIM" if winner["pass"] else "NAO (melhor medido entre os avaliados em val; ver diagnostico)"
        md.append(f"- Aprovado nos criterios: **{pass_txt}**")
        md.append("")
        md.append("| metrica | treino [0,64800) | val [64800,97200) | dev [0,97200) |")
        md.append("|---|---|---|---|")
        m_dev_w = top_rows[0][2] if top_rows and top_rows[0][0]["id"] == wid else period_metrics(candles, results[wid]["events"], 0, DEV_ROWS)[0]
        for key, label in (
            ("net_total_return", "retorno liq"),
            ("profit_factor_net", "PF liq"),
            ("max_drawdown_net", "maxDD liq"),
            ("net_win_rate", "acerto liq"),
            ("trades", "trades"),
            ("sum_cost_returns", "custos (soma)"),
            ("exposure_fraction", "exposicao"),
        ):
            md.append(f"| {label} | {w_m_tr[key]} | {w_m_va[key]} | {m_dev_w[key]} |")
        md.append("")
        md.append("### Consistencia por sub-periodos (posicao zerada em cada fronteira)")
        md.append("")
        md.append("| sub-periodo | net | PF | trades |")
        md.append("|---|---|---|---|")
        qsub = df_quarters[df_quarters["id"] == wid]
        for _, q in qsub.iterrows():
            md.append(f"| {q['quarter']} | {q['net']*100:.3f}% | {q['pf']:.2f} | {int(q['trades'])} |")
        md.append("")
        md.append("### Stress de custos (fee 20 + slip 10 bps/lado = 60 bps RT)")
        md.append("")
        ssub = df_stress[df_stress["id"] == wid]
        for _, s in ssub.iterrows():
            md.append(f"- {s['period']}: {s['net_60bps']*100:.3f}%")
        md.append("")
    md.append("## Comparacao no mesmo intervalo")
    md.append("")
    md.append("| estrategia | treino liq | val liq | dev liq |")
    md.append("|---|---|---|---|")
    md.append(f"| M15_original @30bps (artefato crossovers_dev) | -13.117% | -5.118% | -17.564% |")
    md.append(f"| BTC buy-and-hold P4 | {bh['train']*100:.3f}% | {bh['val']*100:.3f}% | {bh['dev']*100:.3f}% |")
    md.append("| Caixa | 0.000% | 0.000% | 0.000% |")
    if winner is not None:
        md.append(
            f"| Melhor candidato ({wid}) | {w_m_tr['net_total_return']*100:.3f}% | {w_m_va['net_total_return']*100:.3f}% | {m_dev_w['net_total_return']*100:.3f}% |"
        )
    md.append("")
    md.append("## Arquivos")
    md.append("")
    md.append("- `candidates.csv` — todos os candidatos (treino; val so do shortlist)")
    md.append("- `top_quarters.csv` — sub-periodos dos top")
    md.append("- `top_stress_60bps.csv` — stress de custos dos top")
    md.append("- `equity_dev_top.csv` — curvas de equity dev dos top")
    md.append("- `winner_events.csv`, `winner_prefix_check.csv` — eventos e check de causalidade do vencedor")
    md.append("- `best_config.json` — meta + config reproduzivel do vencedor")
    md.append("")
    md.append("## Reproducao do vencedor")
    md.append("")
    if winner is not None:
        md.append("```python")
        md.append(f"cfg = {json.dumps(results[wid]['cfg'], sort_keys=True)}")
        md.append("# events, _ = desired_and_events(candles_dev_97200, cfg); run_backtest(candles_slice, events[a:b], fee_bps=10, slippage_bps=5)")
        md.append("```")
        md.append("")
    md.append("## Limitacoes e bloqueios")
    md.append("")
    md.append("- Janela de mercado unica e fortemente alta (bull): buy-and-hold P4 rendeu "
              f"{bh['dev']*100:.1f}% no dev; vencedores long-only podem estar capturando apenas o viés direcional do período.")
    md.append("- Validacao foi usada para SELECAO do shortlist (nao e holdout limpo); o unico bloco realmente intacto e o de teste [97200,129600), que permanece proibido (P2 queimado para hipoteses novas; avaliacao honesta exige dados futuros/janela P5).")
    md.append("- Multiplos testes: grade grande no treino induz viés de seleção; sem correção estatística aplicada (sem p-vals; DSR bloqueado por P5).")
    md.append("- Motor long-only spot sem alavancagem; sem modelagem de funding/spread dinâmico; slippage fixo P4.")
    md.append("- Nenhum candidato foi testado no bloco de teste; nada aqui autoriza ordens reais nem início da janela P5.")
    (outdir / "report.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    print(f"OUTDIR={outdir}")
    print(f"configs={len(df)} val_avaliadas={int(df['val_net'].notna().sum())} pass={int(df['pass'].sum())}")
    print("TOP10:")
    print(top20.head(10)[["id", "family", "tf", "params", "net", "pf", "val_net", "val_pf", "val_trades", "pass"]].to_string(index=False))
    if winner is not None:
        print(f"WINNER id={winner['id']} pass={bool(winner['pass'])} cfg={json.dumps(results[winner['id']]['cfg'], sort_keys=True)}")
        print(f"  train net={w_m_tr['net_total_return']:.4f} pf={w_m_tr['profit_factor_net']:.3f} trades={w_m_tr['trades']}")
        print(f"  val   net={w_m_va['net_total_return']:.4f} pf={w_m_va['profit_factor_net']:.3f} trades={w_m_va['trades']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
