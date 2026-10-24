#!/usr/bin/env python3
"""Analise exploratoria dos cruzamentos M15_original no conjunto de DESENVOLVIMENTO.

Conjunto de desenvolvimento = treino (50%) + validacao (25%) definidos em
research/run_research.py; o bloco final de teste (25%) NAO e calculado.

Reproducao fiel do motor: sinais via generate_features("15m", ORIGINAL_CONFIG)
+ reconcile_full (condicoes exatas do codigo) e backtest exclusivamente via
run_one(...) -> run_backtest com custos P4 (10+5 bps/lado). Execucao do sinal
somente na abertura seguinte (sem antecipacao). 100% offline; leitura unica de
data/raw/BTCUSDT_1m.csv (SHA conferido contra o constante do projeto).

Saidas: somente em research/out/crossovers_dev_<UTC>/ (pasta nova).
Graficos PNG gerados por rasterizador proprio embutido (matplotlib/PIL
indisponiveis no ambiente e rede proibida pela regra de offline).
"""
from __future__ import annotations

import hashlib
import json
import struct
import sys
import zlib
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "research"))

import run_research as rr  # noqa: E402

CSV = rr.CSV
EXPECTED_SHA = rr.EXPECTED_SHA256
COST = rr.COST_SCENARIOS[1]
FEE, SLIP = COST.fee_bps_per_side, COST.slippage_bps_per_side
COST_RATE = (FEE + SLIP) / 10_000.0

FONT = {
    " ": [0, 0, 0, 0, 0, 0, 0],
    "0": [0x0E, 0x11, 0x13, 0x15, 0x19, 0x11, 0x0E],
    "1": [0x04, 0x0C, 0x04, 0x04, 0x04, 0x04, 0x0E],
    "2": [0x0E, 0x11, 0x01, 0x02, 0x04, 0x08, 0x1F],
    "3": [0x1F, 0x02, 0x04, 0x02, 0x01, 0x11, 0x0E],
    "4": [0x02, 0x06, 0x0A, 0x12, 0x1F, 0x02, 0x02],
    "5": [0x1F, 0x10, 0x1E, 0x01, 0x01, 0x11, 0x0E],
    "6": [0x06, 0x08, 0x10, 0x1E, 0x11, 0x11, 0x0E],
    "7": [0x1F, 0x01, 0x02, 0x04, 0x08, 0x08, 0x08],
    "8": [0x0E, 0x11, 0x11, 0x0E, 0x11, 0x11, 0x0E],
    "9": [0x0E, 0x11, 0x11, 0x0F, 0x01, 0x02, 0x0C],
    "A": [0x0E, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11],
    "B": [0x1E, 0x11, 0x11, 0x1E, 0x11, 0x11, 0x1E],
    "C": [0x0E, 0x11, 0x10, 0x10, 0x10, 0x11, 0x0E],
    "D": [0x1C, 0x12, 0x11, 0x11, 0x11, 0x12, 0x1C],
    "E": [0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x1F],
    "F": [0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x10],
    "G": [0x0E, 0x11, 0x10, 0x17, 0x11, 0x11, 0x0F],
    "H": [0x11, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11],
    "I": [0x0E, 0x04, 0x04, 0x04, 0x04, 0x04, 0x0E],
    "J": [0x07, 0x02, 0x02, 0x02, 0x02, 0x12, 0x0C],
    "K": [0x11, 0x12, 0x14, 0x18, 0x14, 0x12, 0x11],
    "L": [0x10, 0x10, 0x10, 0x10, 0x10, 0x10, 0x1F],
    "M": [0x11, 0x1B, 0x15, 0x15, 0x11, 0x11, 0x11],
    "N": [0x11, 0x19, 0x19, 0x15, 0x13, 0x13, 0x11],
    "O": [0x0E, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0E],
    "P": [0x1E, 0x11, 0x11, 0x1E, 0x10, 0x10, 0x10],
    "Q": [0x0E, 0x11, 0x11, 0x11, 0x15, 0x12, 0x0D],
    "R": [0x1E, 0x11, 0x11, 0x1E, 0x14, 0x12, 0x11],
    "S": [0x0F, 0x10, 0x10, 0x0E, 0x01, 0x01, 0x1E],
    "T": [0x1F, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04],
    "U": [0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0E],
    "V": [0x11, 0x11, 0x11, 0x11, 0x11, 0x0A, 0x04],
    "W": [0x11, 0x11, 0x11, 0x15, 0x15, 0x15, 0x0A],
    "X": [0x11, 0x11, 0x0A, 0x04, 0x0A, 0x11, 0x11],
    "Y": [0x11, 0x11, 0x0A, 0x04, 0x04, 0x04, 0x04],
    "Z": [0x1F, 0x01, 0x02, 0x04, 0x08, 0x10, 0x1F],
    ".": [0x00, 0x00, 0x00, 0x00, 0x00, 0x0C, 0x0C],
    ",": [0x00, 0x00, 0x00, 0x00, 0x0C, 0x04, 0x08],
    ":": [0x00, 0x0C, 0x0C, 0x00, 0x0C, 0x0C, 0x00],
    "-": [0x00, 0x00, 0x00, 0x1F, 0x00, 0x00, 0x00],
    "_": [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x1F],
    "=": [0x00, 0x00, 0x1F, 0x00, 0x1F, 0x00, 0x00],
    "+": [0x00, 0x04, 0x04, 0x1F, 0x04, 0x04, 0x00],
    "%": [0x19, 0x1A, 0x02, 0x04, 0x08, 0x0B, 0x13],
    "/": [0x01, 0x02, 0x02, 0x04, 0x08, 0x08, 0x10],
    "(": [0x02, 0x04, 0x08, 0x08, 0x08, 0x04, 0x02],
    ")": [0x08, 0x04, 0x02, 0x02, 0x02, 0x04, 0x08],
    "<": [0x02, 0x04, 0x08, 0x10, 0x08, 0x04, 0x02],
    ">": [0x08, 0x04, 0x02, 0x01, 0x02, 0x04, 0x08],
    "*": [0x00, 0x0A, 0x04, 0x1F, 0x04, 0x0A, 0x00],
}
FONT_W, FONT_H = 5, 7


class Raster:
    def __init__(self, width: int, height: int, bg=(255, 255, 255)):
        self.w, self.h = width, height
        self.buf = bytearray(bytes(bg) * (width * height))

    def px(self, x: int, y: int, color) -> None:
        x, y = int(round(x)), int(round(y))
        if 0 <= x < self.w and 0 <= y < self.h:
            i = (y * self.w + x) * 3
            self.buf[i:i + 3] = bytes(color)

    def line(self, x0, y0, x1, y1, color, thick=1) -> None:
        x0, y0, x1, y1 = int(round(x0)), int(round(y0)), int(round(x1)), int(round(y1))
        steps = max(abs(x1 - x0), abs(y1 - y0), 1)
        half = thick // 2
        for k in range(steps + 1):
            x = x0 + (x1 - x0) * k / steps
            y = y0 + (y1 - y0) * k / steps
            for dx in range(-half, half + 1):
                for dy in range(-half, half + 1):
                    self.px(int(round(x)) + dx, int(round(y)) + dy, color)

    def polyline(self, xs, ys, color, thick=1) -> None:
        prev = None
        for x, y in zip(xs, ys):
            cur = (int(round(x)), int(round(y)))
            if prev is not None and cur != prev:
                self.line(prev[0], prev[1], cur[0], cur[1], color, thick)
            prev = cur

    def marker(self, x, y, color, size=4) -> None:
        x, y = int(round(x)), int(round(y))
        for d in range(-size, size + 1):
            self.px(x + d, y, color)
            self.px(x, y + d, color)
        for d in range(-size + 1, size):
            self.px(x + d, y + d, color)
            self.px(x + d, y - d, color)

    def text(self, x, y, s, color=(0, 0, 0), scale=1) -> None:
        cx = int(x)
        for ch in s.upper():
            glyph = FONT.get(ch, FONT[" "])
            for row in range(FONT_H):
                bits = glyph[row]
                for col in range(FONT_W):
                    if bits & (1 << (FONT_W - 1 - col)):
                        for sy in range(scale):
                            for sx in range(scale):
                                self.px(cx + col * scale + sx, y + row * scale + sy, color)
            cx += (FONT_W + 1) * scale

    @staticmethod
    def text_width(s, scale=1) -> int:
        return len(s) * (FONT_W + 1) * scale - scale

    def save(self, path: Path) -> None:
        raw = bytearray()
        stride = self.w * 3
        for y in range(self.h):
            raw.append(0)
            raw.extend(self.buf[y * stride:(y + 1) * stride])
        comp = zlib.compress(bytes(raw), 6)

        def chunk(tag: bytes, data: bytes) -> bytes:
            return (struct.pack(">I", len(data)) + tag + data
                    + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

        ihdr = struct.pack(">IIBBBBB", self.w, self.h, 8, 2, 0, 0, 0)
        png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
               + chunk(b"IDAT", comp) + chunk(b"IEND", b""))
        path.write_bytes(png)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def event_targets(ev: np.ndarray) -> np.ndarray:
    state, out = 0, np.zeros(len(ev), dtype=float)
    for i, e in enumerate(ev):
        if e == 1:
            state = 1
        elif e == -1:
            state = 0
        out[i] = state
    return out


def extended_position(target: np.ndarray, length: int) -> np.ndarray:
    pos = np.zeros(length, dtype=float)
    for k in range(1, length - 1):
        pos[k] = target[k - 1]
    if length >= 2:
        pos[length - 1] = 0.0
    return pos


def flag_motivo_entry(feats_row) -> str:
    return (
        f"PAI={int(feats_row['parent_direction'])};FILHO={int(feats_row['child_direction'])};"
        f"FIB={'OK' if bool(feats_row['fibonacci_confirmed']) else 'NAO'};"
        f"REGIME={'OK' if bool(feats_row['regime_acceptable']) else 'NAO'};"
        f"VOLUME={'OK' if bool(feats_row['volume_confirmed']) else 'NAO'};"
        f"MOMENTUM={'OK' if bool(feats_row['momentum_confirmed']) else 'NAO'}"
    )


def flag_motivo_exit(feats_row) -> str:
    parts = []
    if feats_row["parent_direction"] != 1:
        parts.append("PAI!=1")
    if feats_row["child_direction"] == -1:
        parts.append("FILHO=-1")
    if float(feats_row["normalized_slope"]) < 0:
        parts.append("SLOPE<0")
    return "+".join(parts) if parts else "SEM_CONDICAO"


def build_trades(bt, pos_ext, frame, ev):
    pos = bt["position"].to_numpy(dtype=float) > 0.5
    gross = bt["gross_return"].to_numpy(dtype=float)
    net = bt["net_return"].to_numpy(dtype=float)
    costs = bt["costs"].to_numpy(dtype=float)
    prior = np.concatenate(([False], pos[:-1]))
    following = np.concatenate((pos[1:], [False]))
    starts = np.flatnonzero(pos & ~prior)
    ends = np.flatnonzero(pos & ~following)
    if len(starts) != len(ends):
        raise RuntimeError("posicao com trades nao casados")
    trades = []
    opens = pd.to_numeric(frame["open"]).to_numpy(dtype=float)
    ts = frame["timestamp"]
    for i, (s, e) in enumerate(zip(starts, ends), 1):
        w0 = max(int(s) - 1, 0)
        gross_t = float(np.prod(1.0 + gross[s:e + 1]) - 1.0)
        net_t = float(np.prod(1.0 + net[w0:e + 1]) - 1.0)
        cost_sum = float(costs[w0:e + 1].sum())
        exit_row = int(e) + 1
        exit_signal = int(e)
        forced = ev[exit_signal] != -1
        trades.append({
            "trade_id": i,
            "entry_signal_row": int(s) - 1,
            "entry_exec_row": int(s),
            "entry_exec_ts": str(ts.iloc[s]),
            "entry_price": float(opens[s]),
            "exit_signal_row": None if forced else exit_signal,
            "exit_exec_row": exit_row,
            "exit_exec_ts": str(ts.iloc[exit_row]),
            "exit_price": float(opens[exit_row]),
            "duration_minutes": int(e - s + 1),
            "gross_return": gross_t,
            "cost_rate_sum": cost_sum,
            "cost_sides": int(round(cost_sum / COST_RATE)),
            "net_return": net_t,
            "result": "GANHO" if net_t > 0 else ("PERDA" if net_t < 0 else "ZERO"),
            "exit_reason": "LIQUIDACAO_FORCADA_FIM_DO_BLOCO" if forced else "SINAL_DE_SAIDA",
        })
    return trades


def build_signals(feats, ev, pos_ext, trades, dev_end):
    entry_by_row = {t["entry_signal_row"]: t["trade_id"] for t in trades}
    exit_by_row = {t["exit_signal_row"]: t["trade_id"] for t in trades if t["exit_signal_row"] is not None}
    rows = []
    for i in np.flatnonzero(np.isin(ev, [1, -1])[:dev_end]):
        i = int(i)
        entry = ev[i] == 1
        exec_row = i + 1
        if entry:
            executed = exec_row < dev_end - 1 and pos_ext[exec_row] == 1.0
            motivo = flag_motivo_entry(feats.iloc[i])
            trade_id = entry_by_row.get(i, "")
        else:
            executed = pos_ext[i] == 1.0
            motivo = flag_motivo_exit(feats.iloc[i])
            trade_id = exit_by_row.get(i, "")
        rows.append({
            "row": i,
            "timestamp": str(feats["timestamp"].iloc[i]),
            "type": "ENTRADA" if entry else "SAIDA",
            "signal": int(ev[i]),
            "executed": bool(executed),
            "exec_row": exec_row if executed else "",
            "exec_timestamp": str(feats["timestamp"].iloc[exec_row]) if (executed and exec_row < dev_end) else "",
            "motivo": motivo,
            "trade_id": trade_id,
            "parent_direction": int(feats["parent_direction"].iloc[i]),
            "child_direction": int(feats["child_direction"].iloc[i]),
            "fibonacci_confirmed": bool(feats["fibonacci_confirmed"].iloc[i]),
            "regime_acceptable": bool(feats["regime_acceptable"].iloc[i]),
            "volume_confirmed": bool(feats["volume_confirmed"].iloc[i]),
            "momentum_confirmed": bool(feats["momentum_confirmed"].iloc[i]),
            "normalized_slope": float(feats["normalized_slope"].iloc[i]),
            "regime_zscore": float(feats["regime_zscore"].iloc[i]),
            "relative_volume": float(feats["relative_volume"].iloc[i]),
        })
    return rows


def cross_checks(bt, trades, m_dev, equity_last):
    checks = {}
    nets = np.array([t["net_return"] for t in trades], dtype=float)
    product = float(np.prod(1.0 + nets)) if len(nets) else 1.0
    checks["equity_engine_last"] = float(bt["equity"].iloc[-1])
    checks["product_of_trade_nets"] = product
    checks["metrics_net_total_return"] = float(m_dev["net_total_return"])
    checks["abs_diff_engine_vs_trades"] = abs(checks["equity_engine_last"] - product)
    checks["abs_diff_engine_vs_metric"] = abs(
        checks["equity_engine_last"] - (1.0 + checks["metrics_net_total_return"])
    )
    costs_total = float(bt["costs"].sum())
    checks["costs_sum"] = costs_total
    checks["costs_expected_2_sides_per_trade"] = 2.0 * COST_RATE * len(trades)
    checks["abs_diff_costs"] = abs(costs_total - checks["costs_expected_2_sides_per_trade"])
    checks["trades_engine"] = int(m_dev["trades"])
    checks["trades_reconstructed"] = len(trades)
    nn = float(-nets[nets < 0].sum())
    npo = float(nets[nets > 0].sum())
    checks["profit_factor_net_engine"] = float(m_dev["profit_factor_net"])
    checks["profit_factor_net_from_trades"] = npo / nn if nn > 0 else float("inf")
    checks["win_rate_engine"] = float(m_dev["net_win_rate"])
    checks["win_rate_from_trades"] = float((nets > 0).mean()) if len(nets) else 0.0
    checks["reproduced"] = bool(
        checks["abs_diff_engine_vs_trades"] < 1e-12
        and checks["abs_diff_engine_vs_metric"] < 1e-12
        and checks["abs_diff_costs"] < 1e-12
        and checks["trades_engine"] == checks["trades_reconstructed"]
        and np.isclose(
            checks["profit_factor_net_engine"],
            checks["profit_factor_net_from_trades"],
            rtol=1e-9,
        )
        and np.isclose(checks["win_rate_engine"], checks["win_rate_from_trades"], rtol=1e-12)
    )
    checks["equity_last"] = equity_last
    return checks


def prior_results_crosscheck(m_train, m_val) -> dict:
    out = {"available": False}
    path = ROOT / "research" / "out" / "research_results.json"
    if not path.is_file():
        return out
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        split = data["variants"]["M15_original"]["cost_scenarios"][COST.label]["by_split"]
    except Exception:
        return out
    out["available"] = True
    out["matches"] = {}
    for name, mine in (("train", m_train), ("validation", m_val)):
        ref = split[name]
        out["matches"][name] = {
            "net_total_return_equal": abs(ref["net_total_return"] - mine["net_total_return"]) < 1e-12,
            "trades_equal": ref["trades"] == mine["trades"],
            "max_drawdown_equal": abs(ref["max_drawdown_net"] - mine["max_drawdown_net"]) < 1e-12,
        }
    return out


def draw_equity_chart(path, eq_rows, eq, bh_rows, bh, start_ts, end_ts, bh_net, stats):
    W, H = 1400, 800
    Lm, Rm, Tm, Bm = 90, 30, 60, 60
    img = Raster(W, H)
    img.text(Lm, 16, "M15_ORIGINAL DEV SET (TRAIN+VALIDATION) - EQUITY VS BENCHMARKS", (0, 0, 0), 2)
    lo = float(min(eq.min(), bh.min(), 1.0))
    hi = float(max(eq.max(), bh.max(), 1.0))
    pad = max((hi - lo) * 0.06, 1e-6)
    lo, hi = lo - pad, hi + pad
    x0, x1 = Lm, W - Rm
    y0, y1 = H - Bm, Tm
    x_lo = int(min(int(eq_rows[0]), int(bh_rows[0])))
    x_hi = int(max(int(eq_rows[-1]), int(bh_rows[-1])))

    def mx(i):
        return x0 + (i - x_lo) / max(x_hi - x_lo, 1) * (x1 - x0)

    def my(v):
        return y1 + (hi - v) / (hi - lo) * (y0 - y1)

    for k in range(6):
        v = lo + (hi - lo) * k / 5
        y = my(v)
        img.line(x0, y, x1, y, (225, 225, 225), 1)
        label = f"{v:.2f}"
        img.text(x0 - 8 - img.text_width(label), y - FONT_H // 2, label, (0, 0, 0), 1)
    img.line(x0, y0, x1, y0, (0, 0, 0), 1)
    img.line(x0, y0, x0, y1, (0, 0, 0), 1)
    for k in range(6):
        i = x_lo + (x_hi - x_lo) * k // 5
        x = mx(i)
        img.line(x, y0, x, y0 + 5, (0, 0, 0), 1)
        frac = k / 5
        d0 = pd.Timestamp(start_ts)
        d1 = pd.Timestamp(end_ts)
        stamp = d0 + (d1 - d0) * frac
        img.text(min(x - img.text_width("2026-01-01") // 2, x1 - img.text_width("2026-01-01")),
                 y0 + 10, stamp.strftime("%Y-%m-%d"), (0, 0, 0), 1)
    img.polyline([mx(i) for i in bh_rows], [my(v) for v in bh], (230, 140, 30), 2)
    img.polyline([mx(i) for i in eq_rows], [my(v) for v in eq], (30, 90, 220), 2)
    cash_y = my(1.0)
    img.line(x0, cash_y, x1, cash_y, (120, 120, 120), 1)
    legend = [
        ((30, 90, 220), f"STRATEGY NET (ENGINE): {stats['net']:.4%}"),
        ((230, 140, 30), f"BTC BUY AND HOLD P4 ROUND TRIP: {bh_net:.4%}"),
        ((120, 120, 120), "CASH (ZERO RETURN): 0.0000%"),
    ]
    for k, (color, label) in enumerate(legend):
        y = Tm + 10 + k * 16
        img.line(x0 + 14, y + 3, x0 + 42, y + 3, color, 3)
        img.text(x0 + 50, y, label, (0, 0, 0), 1)
    img.save(path)


def draw_price_chart(path, ts_idx, close, trades, start_ts, end_ts):
    W, H = 1400, 800
    Lm, Rm, Tm, Bm = 100, 30, 60, 60
    img = Raster(W, H)
    img.text(Lm, 16, "M15_ORIGINAL DEV SET - BTC CLOSE 1M WITH EXECUTIONS (OPEN)", (0, 0, 0), 2)
    lo, hi = float(close.min()), float(close.max())
    pad = max((hi - lo) * 0.05, 1.0)
    lo, hi = lo - pad, hi + pad
    x0, x1 = Lm, W - Rm
    y0, y1 = H - Bm, Tm

    def mx(i):
        return x0 + i / max(ts_idx[-1], 1) * (x1 - x0)

    def my(v):
        return y1 + (hi - v) / (hi - lo) * (y0 - y1)

    for k in range(6):
        v = lo + (hi - lo) * k / 5
        y = my(v)
        img.line(x0, y, x1, y, (225, 225, 225), 1)
        label = f"{v:.0f}"
        img.text(x0 - 8 - img.text_width(label), y - FONT_H // 2, label, (0, 0, 0), 1)
    img.line(x0, y0, x1, y0, (0, 0, 0), 1)
    img.line(x0, y0, x0, y1, (0, 0, 0), 1)
    for k in range(6):
        i = ts_idx[-1] * k // 5
        x = mx(i)
        img.line(x, y0, x, y0 + 5, (0, 0, 0), 1)
        d0 = pd.Timestamp(start_ts)
        d1 = pd.Timestamp(end_ts)
        stamp = d0 + (d1 - d0) * (k / 5)
        img.text(min(x - img.text_width("2026-01-01") // 2, x1 - img.text_width("2026-01-01")),
                 y0 + 10, stamp.strftime("%Y-%m-%d"), (0, 0, 0), 1)
    img.polyline([mx(i) for i in ts_idx], [my(v) for v in close], (30, 90, 220), 1)
    for t in trades:
        img.marker(mx(t["entry_exec_row"]), my(t["entry_price"]), (0, 150, 0), 3)
        img.marker(mx(t["exit_exec_row"]), my(t["exit_price"]), (210, 40, 40), 3)
    legend = [
        ((30, 90, 220), "BTC CLOSE 1M"),
        ((0, 150, 0), "ENTRY EXECUTION (OPEN PRICE)"),
        ((210, 40, 40), "EXIT EXECUTION (OPEN PRICE)"),
    ]
    for k, (color, label) in enumerate(legend):
        y = Tm + 10 + k * 16
        img.line(x0 + 14, y + 3, x0 + 42, y + 3, color, 3)
        img.text(x0 + 50, y, label, (0, 0, 0), 1)
    img.save(path)


def main() -> int:
    digest = sha256_file(CSV)
    if digest != EXPECTED_SHA:
        print(f"BLOQUEIO: SHA do CSV diverge do constante do projeto: {digest}")
        return 1

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = ROOT / "research" / "out" / f"crossovers_dev_{stamp}"
    out_dir.mkdir(parents=True, exist_ok=False)

    candles = pd.read_csv(CSV)
    n = len(candles)
    train_end = int(n * rr.SPLIT_FRACS["train"])
    val_end = int(n * (rr.SPLIT_FRACS["train"] + rr.SPLIT_FRACS["validation"]))
    dev_end = val_end
    dev_slice = slice(0, dev_end)

    feats = rr.generate_features(candles, "15m", rr.ORIGINAL_CONFIG)
    rr.reconcile_full(feats)
    ev = feats["signal"].to_numpy()

    bt_dev, m_dev = rr.run_one(feats, ev, COST, window=dev_slice)
    _bt_tr, m_train = rr.run_one(feats, ev, COST, window=slice(0, train_end))
    _bt_val, m_val = rr.run_one(feats, ev, COST, window=slice(train_end, dev_end))

    frame = feats.iloc[dev_slice]
    target = event_targets(ev[:dev_end])
    pos_ext = extended_position(target, dev_end)
    trades = build_trades(bt_dev, pos_ext, frame, ev[:dev_end])
    signals = build_signals(feats, ev, pos_ext, trades, dev_end)

    equity_last = float(bt_dev["equity"].iloc[-1])
    checks = cross_checks(bt_dev, trades, m_dev, equity_last)
    prior = prior_results_crosscheck(m_train, m_val)

    opens = pd.to_numeric(frame["open"]).to_numpy(dtype=float)
    bh_ratio = float(opens[-1] / opens[0])
    bh_net = bh_ratio * (1.0 - COST_RATE) ** 2 - 1.0

    nets = np.array([t["net_return"] for t in trades], dtype=float)
    wins = nets[nets > 0]
    losses = nets[nets < 0]
    entries_ev = int((ev[:dev_end] == 1).sum())
    exits_ev = int((ev[:dev_end] == -1).sum())
    entries_exec = sum(1 for s in signals if s["type"] == "ENTRADA" and s["executed"])
    entries_not_exec = sum(1 for s in signals if s["type"] == "ENTRADA" and not s["executed"])

    ts = pd.to_datetime(frame["timestamp"], utc=True, errors="raise")
    start_ts, end_ts = str(ts.iloc[0]), str(ts.iloc[-1])
    last_row_ts = str(ts.iloc[-1])

    trades_df = pd.DataFrame(trades)
    trades_df.to_csv(out_dir / "trades.csv", index=False)
    signals_df = pd.DataFrame(signals)
    signals_df.to_csv(out_dir / "signals.csv", index=False)

    eq = bt_dev["equity"].to_numpy(dtype=float)
    eq_rows = np.array(bt_dev.index, dtype=int)
    bh_curve = (1.0 - COST_RATE) * opens / opens[0]
    bh_curve = bh_curve.copy()
    bh_curve[-1] = (1.0 - COST_RATE) ** 2 * opens[-1] / opens[0]
    draw_equity_chart(
        out_dir / "equity_vs_benchmarks.png",
        eq_rows, eq, np.arange(dev_end), bh_curve, start_ts, last_row_ts, bh_net,
        {"net": float(m_dev["net_total_return"])},
    )
    draw_price_chart(
        out_dir / "price_signals.png",
        np.arange(dev_end), pd.to_numeric(frame["close"]).to_numpy(dtype=float),
        trades, start_ts, last_row_ts,
    )

    losers = [t for t in trades if t["net_return"] < 0]
    sig_by_row = {s["row"]: s for s in signals}
    loser_lines = []
    for t in losers:
        entry_s = sig_by_row.get(t["entry_signal_row"], {})
        exit_row = t["exit_signal_row"]
        exit_s = sig_by_row.get(exit_row, {}) if exit_row is not None else {}
        motivo_e = entry_s.get("motivo", "?")
        motivo_x = exit_s.get("motivo", t["exit_reason"])
        loser_lines.append(
            f"| {t['trade_id']} | {t['entry_exec_ts']} | {t['exit_exec_ts']} | "
            f"{t['net_return'] * 100:.3f}% | {t['duration_minutes']} | {motivo_e} | {motivo_x} |"
        )

    md = []
    md.append("# Analise exploratoria — M15_original, conjunto de desenvolvimento\n")
    md.append(f"- Gerado (UTC): {stamp}")
    md.append(f"- Dados: `{CSV.relative_to(ROOT).as_posix()}` SHA-256 `{digest}`")
    md.append(f"- Variante: M15_original (config original, modo `15m`) | Cenario: {COST.label} "
              f"(fee {FEE:.0f} bps + slippage {SLIP:.0f} bps por lado = {2 * (FEE + SLIP):.0f} bps RT)")
    md.append(f"- Splits do projeto: treino [0, {train_end}), validacao [{train_end}, {dev_end}), "
              f"teste [{dev_end}, {n}) — **bloco de teste nao calculado**\n")
    md.append("## Periodo analisado (desenvolvimento)\n")
    md.append(f"- Linhas: 0 a {dev_end - 1} ({dev_end:,} de {n:,} candles 1m)")
    md.append(f"- Inicio: {start_ts}")
    md.append(f"- Fim: {end_ts}\n")
    md.append("## Sinais e operacoes\n")
    md.append(f"- Eventos de sinal no desenvolvimento: **{entries_ev + exits_ev}** "
              f"(entradas {entries_ev} + saidas {exits_ev})")
    md.append(f"- Entradas executadas: {entries_exec} | entradas nao executadas: {entries_not_exec}")
    md.append(f"- Operacoes concluidas: **{int(m_dev['trades'])}** (reconstrucao casou: "
              f"{checks['trades_reconstructed']})")
    md.append(f"- Taxa de acerto liquida: **{m_dev['net_win_rate'] * 100:.1f}%**")
    md.append(f"- Ganho medio (vitorias): **{(wins.mean() * 100 if len(wins) else 0):.3f}%** "
              f"(n={len(wins)})")
    md.append(f"- Perda media (derrotas): **{(losses.mean() * 100 if len(losses) else 0):.3f}%** "
              f"(n={len(losses)})")
    md.append(f"- Profit factor liquido: **{m_dev['profit_factor_net']:.3f}**")
    md.append(f"- Retorno liquido: **{m_dev['net_total_return'] * 100:.3f}%**")
    md.append(f"- Maximo drawdown liquido: **{m_dev['max_drawdown_net'] * 100:.3f}%**")
    md.append(f"- Exposicao: **{m_dev['exposure_fraction'] * 100:.3f}%** | "
              f"retencao media: {m_dev['avg_holding_bars']:.1f} min")
    md.append(f"- Retorno bruto: {m_dev['gross_total_return'] * 100:.3f}% | "
              f"custos pagos: {m_dev['sum_cost_returns'] * 100:.3f}%\n")
    md.append("## Convencoes (iguais ao motor)\n")
    md.append("- Capital inicial 1.0, posicao binaria 0/1 long-only, sem alavancagem.")
    md.append("- Retorno abertura-a-abertura: sinal conhecido no fechamento t executa no open t+1 "
              "(sem antecipacao); `net = gross - custo`, `equity = prod(1 + net)`.")
    md.append(f"- Custo aditivo {COST_RATE:.4f} por lado sobre turnover (entrada e saida); "
              "liquidacao forcada no ultimo open do bloco.")
    md.append(f"- Buy-and-hold: compra no primeiro open com custo de compra, ultimo ponto ja liquido "
              f"com custo de venda (P4). Terminal = (1-c)^2 * open[-1]/open[0] - 1 = "
              f"**{bh_net * 100:.3f}%**.")
    md.append("- Caixa: retorno zero (1.0).\n")
    md.append("## Reproducao do motor\n")
    md.append(f"- equity final (motor) = {checks['equity_engine_last']:.12f}")
    md.append(f"- prod(1+net dos trades reconstruidos) = {checks['product_of_trade_nets']:.12f} "
              f"(dif {checks['abs_diff_engine_vs_trades']:.2e})")
    md.append(f"- metrica net_total_return do motor difere em {checks['abs_diff_engine_vs_metric']:.2e}")
    md.append(f"- custos: soma motor {checks['costs_sum']:.6f} vs 2 lados x {len(trades)} trades = "
              f"{checks['costs_expected_2_sides_per_trade']:.6f} (dif {checks['abs_diff_costs']:.2e})")
    md.append(f"- PF motor {checks['profit_factor_net_engine']:.6f} vs reconstruido "
              f"{checks['profit_factor_net_from_trades']:.6f}")
    md.append(f"- REPRODUZIDO: **{'SIM' if checks['reproduced'] else 'NAO'}**")
    if prior.get("available"):
        md.append(f"- Cross-check vs research_results.json (so leitura): {json.dumps(prior['matches'])}")
    md.append("")
    md.append("## Comparacao no mesmo intervalo (desenvolvimento)\n")
    md.append("| Estrategia | Retorno liquido | Max DD liquido |")
    md.append("|---|---|---|")
    md.append(f"| M15_original @30bps | {m_dev['net_total_return'] * 100:.3f}% | "
              f"{m_dev['max_drawdown_net'] * 100:.3f}% |")
    md.append(f"| BTC buy-and-hold P4 | {bh_net * 100:.3f}% | (nao calculado para benchmark) |")
    md.append("| Caixa | 0.000% | 0.000% |\n")
    md.append("## Referencia por split (mesma definicao do projeto; ambos dentro do desenvolvimento)\n")
    md.append("| split | trades | retorno liq | maxDD liq | PF liq | win |")
    md.append("|---|---|---|---|---|---|")
    for name, m in (("train", m_train), ("validation", m_val)):
        md.append(f"| {name} | {m['trades']} | {m['net_total_return'] * 100:.3f}% | "
                  f"{m['max_drawdown_net'] * 100:.3f}% | {m['profit_factor_net']:.3f} | "
                  f"{m['net_win_rate'] * 100:.1f}% |")
    md.append("")
    md.append(f"## Operacoes perdedoras ({len(loser_lines)})\n")
    md.append("| id | entrada | saida | liq | min | motivo entrada | motivo saida |")
    md.append("|---|---|---|---|---|---|---|")
    md.extend(loser_lines)
    md.append("")
    md.append("## Limitacoes\n")
    md.append("- PNGs gerados por rasterizador embutido neste script: matplotlib/PIL nao estao "
              "instalados no .venv e a regra de offline proibe baixa-los.")
    md.append("- Analise em bloco unico continuo (treino+validacao); o projeto tambem reporta cada "
              "split separadamente (cada split liquidado no proprio fim), por isso os numeros por "
              "split podem diferir levemente da linha unica.")
    md.append("- O motivo de cada sinal e derivado das condicoes exatas de reconcile_full "
              "(run_research.py) sobre as colunas de features; nao ha regra nova.")
    md.append("- Bloco de teste (25% final) nao foi calculado nem consultado para escolhas.")
    (out_dir / "summary.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    print("=" * 100)
    print(f"PASTA DE RESULTADOS: {out_dir}")
    print("=" * 100)
    print(f"Periodo dev: {start_ts} -> {end_ts} (linhas 0..{dev_end - 1} de {n})")
    print(f"Sinais: {entries_ev + exits_ev} (entradas {entries_ev}, saidas {exits_ev}) | "
          f"entradas executadas {entries_exec} | nao executadas {entries_not_exec}")
    print(f"Operacoes: {int(m_dev['trades'])} | win {m_dev['net_win_rate'] * 100:.1f}% | "
          f"ganho medio {wins.mean() * 100 if len(wins) else 0:.3f}% | "
          f"perda media {losses.mean() * 100 if len(losses) else 0:.3f}%")
    print(f"PF liq {m_dev['profit_factor_net']:.3f} | retorno liq {m_dev['net_total_return'] * 100:.3f}% | "
          f"maxDD {m_dev['max_drawdown_net'] * 100:.3f}% | exposicao {m_dev['exposure_fraction'] * 100:.3f}%")
    print(f"Benchmarks: buy-and-hold P4 {bh_net * 100:.3f}% | caixa 0.000%")
    print(f"Reproducao do motor: {'SIM' if checks['reproduced'] else 'NAO'} "
          f"(dif equity {checks['abs_diff_engine_vs_trades']:.2e})")
    print("-" * 100)
    print(f"OPERACOES PERDEDORAS ({len(loser_lines)}):")
    for t in losers:
        entry_s = sig_by_row.get(t["entry_signal_row"], {})
        exit_s = sig_by_row.get(t["exit_signal_row"], {}) if t["exit_signal_row"] is not None else {}
        print(f"  #{t['trade_id']:>3} {t['entry_exec_ts']} -> {t['exit_exec_ts']} "
              f"{t['net_return'] * 100:8.3f}% {t['duration_minutes']:>5} min | "
              f"ENT: {entry_s.get('motivo', '?')} | SAI: {exit_s.get('motivo', t['exit_reason'])}")
    print("-" * 100)
    print(f"Arquivos: summary.md, trades.csv, signals.csv, equity_vs_benchmarks.png, price_signals.png")
    print(f"Bloco de teste [{dev_end}, {n}) NAO calculado. Rede: nao usada. Arquivos existentes: intactos.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
