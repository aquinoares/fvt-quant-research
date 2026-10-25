#!/usr/bin/env python3
"""Candidatas adaptadas do GitHub (chencore/autoresearch-crypto) ao formato FVT.

Uso: .venv/Scripts/python.exe research/github_strategies_search.py

Referencias estudadas (somente regras; nenhum codigo de trading ao vivo importado):
- dex/strategies/trend_follow.py  -> GITHUB_TREND_PULLBACK
- dex/strategies/hybrid_mm.py     -> GITHUB_RSI_REENTRY (ramo long only)
- descricao da tarefa             -> GITHUB_SQUEEZE_BREAKOUT (Bollinger+ATR+volume)

Adaptacoes obrigatorias ao FVT:
- long-only spot (o motor FVT nao faz short); sinais em barras fechadas;
  entrada na abertura da barra 1m seguinte; custos P4 por lado (0.0015).
- Stops/tempos verificados intrabarra em 1m; se stop e condicao de saida
  ocorrem na mesma barra, o stop tem prioridade; stop atingido com gap
  preenche no open pior (min(stop, open)); alvo (se houvesse) nunca melhora
  por gap. Equidade mark-to-close para maxDD.
- Simulador proprio (contabilidade trade-a-trade, custo aditivo por lado,
  equity = prod(1+net)); MOM_TF240_LB96 recalculado no MESMO simulador para
  comparacao homogenea (motor publicado fica como cross-check).
- Leitura apenas nrows=97200; bloco de teste intocado.
"""
from __future__ import annotations

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
COST_P4 = 0.0015
COST_STRESS = 0.0030

sys.path.insert(0, str(ROOT / "research"))
sys.path.insert(0, str(ROOT / "src"))
from strategy_search import atr_wilder, bars_of, map_to_1m, rsi_wilder  # noqa: E402


def sha256_check(path: Path) -> str:
    import hashlib

    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    digest = h.hexdigest()
    if digest != EXPECTED_SHA256:
        raise RuntimeError(f"SHA256 do CSV diverge: {digest}")
    return digest


def build_signals(frame: pd.DataFrame, cfg: dict) -> dict:
    tf = int(cfg["tf"])
    bars = bars_of(frame, tf)
    close = bars["close"]
    high = bars["high"]
    vol = bars["volume"]
    atr = atr_wilder(bars, 14)
    fam = cfg["family"]

    entry = pd.Series(False, index=bars.index)
    exit_close = pd.Series(False, index=bars.index)

    if fam == "GITHUB_TREND_PULLBACK":
        long_ma = close.ewm(span=cfg["long_ma"], adjust=False, min_periods=cfg["long_ma"]).mean()
        pull = close.ewm(span=cfg["pull_ma"], adjust=False, min_periods=cfg["pull_ma"]).mean()
        mid = close.ewm(span=cfg["pull_ma"] * 2, adjust=False, min_periods=cfg["pull_ma"] * 2).mean()
        up = close > long_ma
        pullback = close <= pull * (1.0 + cfg["entry_zone"])
        entry = up & pullback & pull.notna() & long_ma.notna()
        exit_close = pull < mid
    elif fam == "GITHUB_RSI_REENTRY":
        r = rsi_wilder(close, cfg["rsi_n"])
        ema_f = close.ewm(span=cfg["ma"], adjust=False, min_periods=cfg["ma"]).mean()
        ema_s = close.ewm(span=cfg["ma"] * 2, adjust=False, min_periods=cfg["ma"] * 2).mean()
        cross_up = (r.shift(1) < cfg["rsi_low"]) & (r >= cfg["rsi_low"])
        tb = bars_of(frame, 240)
        cf = tb["close"]
        fast4 = cf.ewm(span=20, adjust=False, min_periods=20).mean()
        slow4 = cf.ewm(span=40, adjust=False, min_periods=40).mean()
        trend4 = (fast4 > slow4).astype(float)
        right = pd.DataFrame({"ts": trend4.index, "v": trend4.to_numpy()})
        m4 = pd.merge_asof(pd.DataFrame({"ts": bars.index}), right, on="ts", direction="backward")
        trend_ok = m4["v"].fillna(0.0).to_numpy() == 1.0
        entry = cross_up & trend_ok
        exit_close = ema_f < ema_s
    elif fam == "GITHUB_SQUEEZE_BREAKOUT":
        n = cfg["bb_n"]
        mid = close.rolling(n).mean()
        sd = close.rolling(n).std()
        upper_prev = (mid + cfg["bb_k"] * sd).shift(1)
        width = (2.0 * cfg["bb_k"] * sd) / close
        width_ref = width.rolling(cfg["width_ma"]).mean()
        squeeze = width <= cfg["squeeze_ratio"] * width_ref
        vol_ref = vol.rolling(cfg["vol_ma"]).mean()
        breakout = (close > upper_prev) & (vol > cfg["vol_mult"] * vol_ref)
        entry = squeeze.shift(1).fillna(False) & breakout & mid.notna()
        exit_close = close < mid
    else:
        raise ValueError(family)

    entry_1m = map_to_1m(frame, entry.astype(float), tf).fillna(0.0) > 0.5
    exit_1m = map_to_1m(frame, exit_close.astype(float), tf).fillna(0.0) > 0.5
    hi_1m = map_to_1m(frame, high, tf)
    atr_1m = map_to_1m(frame, atr, tf)
    sig_ts = bars.index + pd.Timedelta(minutes=tf - 1)
    completed = frame["timestamp"].isin(sig_ts).to_numpy()
    entry_arr = (entry_1m.to_numpy(bool) & completed).astype(np.int8)
    exit_arr = (exit_1m.to_numpy(bool) & completed).astype(np.int8)
    hi_arr = np.where(completed, hi_1m.to_numpy(float), np.nan)
    atr_arr = np.where(completed, atr_1m.to_numpy(float), np.nan)
    return {
        "entry": entry_arr.astype(bool),
        "exit_close": exit_arr.astype(bool),
        "tf_high": hi_arr,
        "tf_atr": atr_arr,
        "use_stop": True,
        "atr_mult": float(cfg.get("atr_mult", 2.0)),
        "max_hold_tf": int(cfg.get("max_hold", 24)),
    }


def simulate(frame: pd.DataFrame, sig: dict, cost: float) -> dict:
    o = frame["open"].to_numpy(float)
    h = frame["high"].to_numpy(float)
    lo = frame["low"].to_numpy(float)
    cl = frame["close"].to_numpy(float)
    n = len(o)
    entry_s, exit_s = sig["entry"], sig["exit_close"]
    hi_tf, atr_tf = sig["tf_high"], sig["tf_atr"]
    use_stop, mult, max_hold = sig["use_stop"], sig["atr_mult"], sig["max_hold_tf"]

    equity = 1.0
    eq_path = np.ones(n)
    trades = []
    holding = False
    pending_entry = False
    pending_exit = False
    entry_fill = 0.0
    eq_at_entry = 1.0
    highest = 0.0
    stop = np.inf
    hold_tf = 0
    entry_row = -1
    exposure = 0

    for i in range(n):
        if pending_exit and holding:
            exit_fill = o[i]
            net = exit_fill / entry_fill - 1.0 - 2.0 * cost
            equity = eq_at_entry * (exit_fill / entry_fill - 2.0 * cost) / (1.0 - cost)
            trades.append({"entry_row": entry_row, "exit_row": i, "exit_kind": "signal", "net": net})
            holding = False
            pending_exit = False
        if pending_entry and not holding:
            entry_fill = o[i]
            eq_at_entry = equity * (1.0 - cost)
            equity = eq_at_entry
            holding = True
            pending_entry = False
            entry_row = i
            highest = float(hi_tf[i]) if np.isfinite(hi_tf[i]) else entry_fill
            stop = entry_fill - mult * atr_tf[i] if np.isfinite(atr_tf[i]) else np.inf
            hold_tf = 0
        if holding:
            exposure += 1
            if np.isfinite(stop) and lo[i] <= stop:
                exit_fill = min(stop, o[i])
                net = exit_fill / entry_fill - 1.0 - 2.0 * cost
                equity = eq_at_entry * (exit_fill / entry_fill - 2.0 * cost) / (1.0 - cost)
                trades.append({"entry_row": entry_row, "exit_row": i, "exit_kind": "stop", "net": net})
                holding = False
            else:
                if np.isfinite(hi_tf[i]):
                    highest = max(highest, float(hi_tf[i]))
                    if use_stop and np.isfinite(atr_tf[i]):
                        stop = highest - mult * float(atr_tf[i])
                    hold_tf += 1
                if exit_s[i] or (use_stop and hold_tf >= max_hold):
                    pending_exit = True
            eq_path[i] = equity * (cl[i] / entry_fill) if holding else equity
        else:
            eq_path[i] = equity
            if entry_s[i]:
                pending_entry = True

    if holding:
        exit_fill = o[-1]
        net = exit_fill / entry_fill - 1.0 - 2.0 * cost
        equity = eq_at_entry * (exit_fill / entry_fill - 2.0 * cost) / (1.0 - cost)
        trades.append({"entry_row": entry_row, "exit_row": n - 1, "exit_kind": "eod", "net": net})
        eq_path[-1] = equity

    nets = np.array([t["net"] for t in trades], dtype=float)
    gp = float(nets[nets > 0].sum()) if len(nets) else 0.0
    gn = float(-nets[nets < 0].sum()) if len(nets) else 0.0
    pf = gp / gn if gn > 0 else (float("inf") if gp > 0 else float("nan"))
    peaks = np.maximum.accumulate(eq_path)
    maxdd = float(np.min(eq_path / peaks - 1.0)) if n else 0.0
    return {
        "net": float(equity - 1.0),
        "pf": float(pf),
        "maxdd": maxdd,
        "trades": len(trades),
        "win": float(np.mean(nets > 0)) if len(nets) else 0.0,
        "costs": len(nets) * 2.0 * cost,
        "exposure": exposure / n if n else 0.0,
        "best": float(nets.max()) if len(nets) else 0.0,
        "worst": float(nets.min()) if len(nets) else 0.0,
        "trade_list": trades,
        "eq_path": eq_path,
    }


def mom_events(frame_dev: pd.DataFrame) -> np.ndarray:
    from strategy_search import desired_and_events

    cfg = {"family": "momentum", "tf": 240, "lookback": 96, "thr": 0.005}
    ev, _ = desired_and_events(frame_dev, cfg)
    return ev


def simulate_from_events(frame: pd.DataFrame, events: np.ndarray, cost: float) -> dict:
    sig = {
        "entry": events == 1,
        "exit_close": events == -1,
        "tf_high": np.full(len(events), np.nan),
        "tf_atr": np.full(len(events), np.nan),
        "use_stop": False,
        "atr_mult": 0.0,
        "max_hold_tf": 10**9,
    }
    return simulate(frame, sig, cost)


def main() -> int:
    import hashlib

    digest = sha256_check(CSV)
    candles = pd.read_csv(CSV, nrows=DEV_ROWS)
    if len(candles) != DEV_ROWS:
        raise RuntimeError(f"Esperado {DEV_ROWS} linhas, obtido {len(candles)}")
    candles["timestamp"] = pd.to_datetime(candles["timestamp"], format="ISO8601", utc=True)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    outdir = ROOT / "research" / "out" / f"github_strategies_{stamp}"
    outdir.mkdir(parents=True, exist_ok=False)

    configs = [
        {"name": "GITHUB_TREND_PULLBACK_A", "family": "GITHUB_TREND_PULLBACK", "tf": 60, "long_ma": 100, "pull_ma": 20, "entry_zone": 0.002, "atr_mult": 2.0, "max_hold": 24},
        {"name": "GITHUB_TREND_PULLBACK_B", "family": "GITHUB_TREND_PULLBACK", "tf": 60, "long_ma": 100, "pull_ma": 20, "entry_zone": 0.002, "atr_mult": 3.0, "max_hold": 24},
        {"name": "GITHUB_TREND_PULLBACK_C", "family": "GITHUB_TREND_PULLBACK", "tf": 240, "long_ma": 100, "pull_ma": 20, "entry_zone": 0.002, "atr_mult": 2.0, "max_hold": 24},
        {"name": "GITHUB_TREND_PULLBACK_D", "family": "GITHUB_TREND_PULLBACK", "tf": 15, "long_ma": 100, "pull_ma": 20, "entry_zone": 0.002, "atr_mult": 2.0, "max_hold": 24},
        {"name": "GITHUB_RSI_REENTRY_A", "family": "GITHUB_RSI_REENTRY", "tf": 15, "rsi_n": 14, "rsi_low": 25, "ma": 20, "atr_mult": 2.0, "max_hold": 24},
        {"name": "GITHUB_RSI_REENTRY_B", "family": "GITHUB_RSI_REENTRY", "tf": 15, "rsi_n": 14, "rsi_low": 30, "ma": 20, "atr_mult": 2.0, "max_hold": 24},
        {"name": "GITHUB_RSI_REENTRY_C", "family": "GITHUB_RSI_REENTRY", "tf": 60, "rsi_n": 14, "rsi_low": 25, "ma": 20, "atr_mult": 2.0, "max_hold": 24},
        {"name": "GITHUB_RSI_REENTRY_D", "family": "GITHUB_RSI_REENTRY", "tf": 60, "rsi_n": 14, "rsi_low": 30, "ma": 20, "atr_mult": 2.0, "max_hold": 24},
        {"name": "GITHUB_SQUEEZE_BREAKOUT_A", "family": "GITHUB_SQUEEZE_BREAKOUT", "tf": 15, "bb_n": 20, "bb_k": 2.0, "width_ma": 50, "squeeze_ratio": 0.6, "vol_ma": 20, "vol_mult": 1.5, "atr_mult": 2.0, "max_hold": 24},
        {"name": "GITHUB_SQUEEZE_BREAKOUT_B", "family": "GITHUB_SQUEEZE_BREAKOUT", "tf": 60, "bb_n": 20, "bb_k": 2.0, "width_ma": 50, "squeeze_ratio": 0.6, "vol_ma": 20, "vol_mult": 1.5, "atr_mult": 2.0, "max_hold": 24},
        {"name": "GITHUB_SQUEEZE_BREAKOUT_C", "family": "GITHUB_SQUEEZE_BREAKOUT", "tf": 60, "bb_n": 20, "bb_k": 2.0, "width_ma": 50, "squeeze_ratio": 0.6, "vol_ma": 20, "vol_mult": 2.0, "atr_mult": 2.5, "max_hold": 24},
    ]

    rows = []
    detail = {}
    for cfg in configs:
        sig = build_signals(candles, cfg)
        for period, (a, b) in (("train", (0, TRAIN_END)), ("val", (TRAIN_END, DEV_ROWS))):
            sl = candles.iloc[a:b].reset_index(drop=True)
            sub = {k: (v[a:b] if isinstance(v, np.ndarray) else v) for k, v in sig.items()}
            res = simulate(sl, sub, COST_P4)
            res_stress = simulate(sl, sub, COST_STRESS)
            detail[(cfg["name"], period)] = res
            rows.append(
                {
                    "name": cfg["name"],
                    "family": cfg["family"],
                    "tf": cfg["tf"],
                    "params": json.dumps({k: v for k, v in cfg.items() if k not in ("name", "family", "tf")}, sort_keys=True),
                    "period": period,
                    "net": res["net"],
                    "pf": res["pf"],
                    "maxdd": res["maxdd"],
                    "trades": res["trades"],
                    "win": res["win"],
                    "costs": res["costs"],
                    "exposure": res["exposure"],
                    "best": res["best"],
                    "worst": res["worst"],
                    "net_60bps": res_stress["net"],
                }
            )
    df = pd.DataFrame(rows)

    def verdict(name: str) -> dict:
        tr = df[(df["name"] == name) & (df["period"] == "train")].iloc[0]
        va = df[(df["name"] == name) & (df["period"] == "val")].iloc[0]
        base_ok = tr["net"] > 0 and va["net"] > 0 and tr["pf"] >= 1.0 and va["pf"] >= 1.0 and va["maxdd"] >= -0.10
        enough = tr["trades"] >= 10 and va["trades"] >= 10
        stress_ok = va["net_60bps"] > 0
        return {
            "base_ok": bool(base_ok),
            "enough_trades": bool(enough),
            "stress_val_positive": bool(stress_ok),
            "evidence": "util" if (base_ok and enough and stress_ok) else ("inconclusivo_poucos_trades" if base_ok else "nao_passou"),
            "score": min(tr["net"], va["net"]),
        }

    verdicts = {name: verdict(name) for name in df["name"].unique()}

    ev_mom_tr = mom_events(candles)
    mom_rows = []
    for period, (a, b) in (("train", (0, TRAIN_END)), ("val", (TRAIN_END, DEV_ROWS))):
        sl = candles.iloc[a:b].reset_index(drop=True)
        res = simulate_from_events(sl, ev_mom_tr[a:b], COST_P4)
        res_s = simulate_from_events(sl, ev_mom_tr[a:b], COST_STRESS)
        mom_rows.append({"name": "MOM_TF240_LB96 (simulador)", "period": period, "net": res["net"], "pf": res["pf"], "maxdd": res["maxdd"], "trades": res["trades"], "win": res["win"], "costs": res["costs"], "net_60bps": res_s["net"]})
    df_mom = pd.DataFrame(mom_rows)

    bh = {}
    for period, (a, b) in (("train", (0, TRAIN_END)), ("val", (TRAIN_END, DEV_ROWS))):
        opens = candles["open"].iloc[a:b]
        bh[period] = float((opens.iloc[-1] / opens.iloc[0]) * (1.0 - COST_P4) ** 2 - 1.0)

    passing = [n for n, v in verdicts.items() if v["evidence"] == "util"]
    enough = [n for n, v in verdicts.items() if v["enough_trades"]]
    others = [n for n in verdicts if n not in passing and n not in enough]
    grp_pass = sorted(passing, key=lambda n: verdicts[n]["score"], reverse=True)
    grp_enough = sorted(enough, key=lambda n: verdicts[n]["score"], reverse=True)
    grp_other = sorted(others, key=lambda n: verdicts[n]["score"], reverse=True)
    ranked = [(n, verdicts[n]) for n in (grp_pass + grp_enough + grp_other)]
    best_name = grp_pass[0] if grp_pass else (grp_enough[0] if grp_enough else ranked[0][0])

    best_cfg = next(c for c in configs if c["name"] == best_name)
    best_sig = build_signals(candles, best_cfg)
    tr_sl = candles.iloc[:TRAIN_END].reset_index(drop=True)
    tr_sub = {k: (v[:TRAIN_END] if isinstance(v, np.ndarray) else v) for k, v in best_sig.items()}
    best_tr = simulate(tr_sl, tr_sub, COST_P4)
    val_sl = candles.iloc[TRAIN_END:].reset_index(drop=True)
    val_sub = {k: (v[TRAIN_END:] if isinstance(v, np.ndarray) else v) for k, v in best_sig.items()}
    best_va = simulate(val_sl, val_sub, COST_P4)
    dev_sl = candles.reset_index(drop=True)
    best_dev = simulate(dev_sl, best_sig, COST_P4)

    ts_dev = candles["timestamp"].reset_index(drop=True)
    eq_df = pd.DataFrame({"timestamp": ts_dev[: len(best_dev["eq_path"])], "equity_best": best_dev["eq_path"]})
    eq_df.to_csv(outdir / "equity_best_dev.csv", index=False)

    trade_rows = []
    for tag, res, off in (("train", best_tr, 0), ("val", best_va, TRAIN_END)):
        for t in res["trade_list"]:
            trade_rows.append(
                {
                    "period": tag,
                    "entry_ts": str(ts_dev.iloc[t["entry_row"] + off]),
                    "exit_ts": str(ts_dev.iloc[t["exit_row"] + off]),
                    "exit_kind": t["exit_kind"],
                    "net": t["net"],
                }
            )
    pd.DataFrame(trade_rows).to_csv(outdir / "best_trades.csv", index=False)

    qbounds = [("train_q1", 0, 16200), ("train_q2", 16200, 32400), ("train_q3", 32400, 48600), ("train_q4", 48600, 64800), ("val_q1", 64800, 81000), ("val_q2", 81000, 97200)]
    sub_rows = []
    for name in df["name"].unique():
        cfg = next(c for c in configs if c["name"] == name)
        sig = build_signals(candles, cfg)
        for qname, a, b in qbounds:
            sl = candles.iloc[a:b].reset_index(drop=True)
            sub = {k: (v[a:b] if isinstance(v, np.ndarray) else v) for k, v in sig.items()}
            r = simulate(sl, sub, COST_P4)
            sub_rows.append({"name": name, "subperiod": qname, "net": r["net"], "pf": r["pf"], "trades": r["trades"]})
    df_sub = pd.DataFrame(sub_rows)

    df.to_csv(outdir / "candidates.csv", index=False)
    df_mom.to_csv(outdir / "mom_baseline.csv", index=False)
    df_sub.to_csv(outdir / "subperiods.csv", index=False)

    meta = {
        "generated_utc": stamp,
        "csv_sha256": digest,
        "cost_p4_per_side": COST_P4,
        "cost_stress_per_side": COST_STRESS,
        "test_block_untouched": True,
        "reference_repo": "https://github.com/chencore/autoresearch-crypto (trend_follow.py, hybrid_mm.py)",
        "configs": configs,
        "best_name": best_name,
        "best_evidence": verdicts[best_name]["evidence"],
        "best_cfg": best_cfg,
        "verdicts": verdicts,
    }
    (outdir / "best_config.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    md = []
    md.append("# Candidatas GitHub adaptadas — FVT (dev: linhas 0..97199)")
    md.append("")
    md.append(f"- Gerado (UTC): {stamp} | CSV SHA-256 `{digest}` | bloco de teste intocado")
    md.append("- Referência: chencore/autoresearch-crypto (trend_follow.py, hybrid_mm.py) — só regras adaptadas; long-only; execução open t+1; stops intrabarra 1m conservadores (stop antes de saída por sinal; gap de stop preenche no open pior)")
    md.append("- Custos P4 = 0,0015/lado (30 bps RT) + stress 60 bps RT; contabilidade: custo aditivo por lado, equity = prod(1+net_trade); maxDD mark-to-close")
    md.append(f"- Configs: {len(configs)} (conjunto pequeno e documentado; sem grade massiva)")
    md.append("")
    md.append("## Critérios de classificação (declarados)")
    md.append("")
    md.append("- `util`: líquido>0 e PF>=1 em treino E validação, validação maxDD >= -10%, >=10 trades completos por período, validação positiva sob 60 bps")
    md.append("- `inconclusivo_poucos_trades`: critérios econômicos ok mas <10 trades em algum período")
    md.append("- `nao_passou`: demais casos")
    md.append("")
    md.append("## Ranking (grupos: util -> >=10 trades/periodo -> demais; dentro do grupo por min(treino,val) @P4)")
    md.append("")
    md.append("| # | nome | tf | treino net | PF | tr | val net | PF | tr | val DD | val 60bps | veredito |")
    md.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for i, (name, v) in enumerate(ranked, 1):
        tr = df[(df["name"] == name) & (df["period"] == "train")].iloc[0]
        va = df[(df["name"] == name) & (df["period"] == "val")].iloc[0]
        pf_tr = "inf" if np.isinf(tr["pf"]) else f"{tr['pf']:.2f}"
        pf_va = "inf" if np.isinf(va["pf"]) else f"{va['pf']:.2f}"
        md.append(
            f"| {i} | {name} | {int(tr['tf'])} | {tr['net']*100:.2f}% | {pf_tr} | {int(tr['trades'])} "
            f"| {va['net']*100:.2f}% | {pf_va} | {int(va['trades'])} | {va['maxdd']*100:.2f}% "
            f"| {va['net_60bps']*100:.2f}% | {v['evidence']} |"
        )
    md.append("")
    md.append("## Melhor candidata medida")
    md.append("")
    btr = df[(df["name"] == best_name) & (df["period"] == "train")].iloc[0]
    bva = df[(df["name"] == best_name) & (df["period"] == "val")].iloc[0]
    md.append(f"- **{best_name}** | veredito: **{verdicts[best_name]['evidence']}**")
    md.append(f"- config: `{json.dumps(best_cfg, sort_keys=True)}`")
    md.append("")
    md.append("| metrica | treino | val | dev |")
    md.append("|---|---|---|---|")
    md.append(f"| net @P4 | {best_tr['net']*100:.3f}% | {best_va['net']*100:.3f}% | {best_dev['net']*100:.3f}% |")
    md.append(f"| PF | {best_tr['pf']:.3f} | {best_va['pf']:.3f} | {best_dev['pf']:.3f} |")
    md.append(f"| maxDD | {best_tr['maxdd']*100:.3f}% | {best_va['maxdd']*100:.3f}% | {best_dev['maxdd']*100:.3f}% |")
    md.append(f"| trades | {best_tr['trades']} | {best_va['trades']} | {best_dev['trades']} |")
    md.append(f"| acerto | {best_tr['win']*100:.1f}% | {best_va['win']*100:.1f}% | {best_dev['win']*100:.1f}% |")
    md.append(f"| custos | {best_tr['costs']*100:.3f}% | {best_va['costs']*100:.3f}% | {best_dev['costs']*100:.3f}% |")
    md.append(f"| exposicao | {best_tr['exposure']*100:.1f}% | {best_va['exposure']*100:.1f}% | {best_dev['exposure']*100:.1f}% |")
    md.append("")
    md.append("### Sub-períodos da melhor (posicao zerada por fronteira)")
    md.append("")
    md.append("| sub | net | PF | trades |")
    md.append("|---|---|---|---|")
    for _, r in df_sub[df_sub["name"] == best_name].iterrows():
        pf_s = "inf" if np.isinf(r["pf"]) else f"{r['pf']:.2f}"
        md.append(f"| {r['subperiod']} | {r['net']*100:.3f}% | {pf_s} | {int(r['trades'])} |")
    md.append("")
    md.append("## Comparação homogênea (mesmo simulador / mesmas premissas)")
    md.append("")
    md.append("| estratégia | treino net | PF | tr | val net | PF | tr | val 60bps |")
    md.append("|---|---|---|---|---|---|---|---|")
    mtr = df_mom[df_mom["period"] == "train"].iloc[0]
    mva = df_mom[df_mom["period"] == "val"].iloc[0]
    md.append(
        f"| MOM_TF240_LB96 (simulador) | {mtr['net']*100:.2f}% | {mtr['pf']:.2f} | {int(mtr['trades'])} "
        f"| {mva['net']*100:.2f}% | {mva['pf']:.2f} | {int(mva['trades'])} | {mva['net_60bps']*100:.2f}% |"
    )
    md.append(f"| {best_name} | {btr['net']*100:.2f}% | {btr['pf']:.2f} | {int(btr['trades'])} | {bva['net']*100:.2f}% | {bva['pf']:.2f} | {int(bva['trades'])} | {bva['net_60bps']*100:.2f}% |")
    md.append(f"| BTC buy-and-hold P4 | {bh['train']*100:.2f}% | — | 1 | {bh['val']*100:.2f}% | — | 1 | — |")
    md.append("| M15_original @30bps (artefato motor, nao simulador) | -13.12% | 0.15 | 53 | -5.12% | 0.18 | 21 | — |")
    md.append("")
    md.append("## Arquivos")
    md.append("")
    md.append("- `candidates.csv` (todas as configs × período, P4 + stress), `subperiods.csv`, `mom_baseline.csv`, `best_trades.csv`, `equity_best_dev.csv`, `best_config.json`")
    md.append("")
    md.append("## Limitações")
    md.append("")
    md.append("- Adaptação documentada GITHUB_RSI_REENTRY: o filtro original (price > EMA20 da própria barra) dispara 0/74 cruzas nesta janela (no cruzamento do RSI o preço está sempre abaixo da EMA20, -0,1% a -0,5%); substituído pelo próprio `is_uptrend` (EMA20>EMA40) do referenciado, avaliado no timeframe superior 240m (36/74 cruzas passam) — mudança de semântica única para corrigir disparo estruturalmente nulo, não busca de limiar favorável.")
    md.append("")
    md.append("- Resultados EXPLORATÓRIOS: validação histórica já foi usada em seleções anteriores (busca strategy_search) e nesta (escolha entre 11 configs); não constituem prova independente de rentabilidade.")
    md.append("- Janela única de mercado (alta acentuada); sem short (motor FVT long-only); ATR/trailing calculados no fechamento das barras tf e checados em 1m; maxDD mark-to-close (extremos intrabarra não cobertos).")
    md.append("- MOM_TF240 recalculado no simulador difere levemente do motor publicado (colocação do custo na composição); motor publicado: treino +21,95% / val +6,47%.")
    md.append("- Bloco de teste [97200,129600) permanece intocado; P5 não iniciada; nenhuma ordem real.")
    (outdir / "report.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    print(f"OUTDIR={outdir}")
    print(df.pivot(index="name", columns="period", values=["net", "pf", "trades"]).to_string())
    print("VERDICTS:", json.dumps(verdicts, indent=1))
    print(f"BEST={best_name} evidence={verdicts[best_name]['evidence']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
