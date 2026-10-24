#!/usr/bin/env python3
"""Prospective shadow test for Convergencia Pai/Filho/Trindade.

This script reads public Binance Spot market data only. It never accepts API
keys and never sends orders. It copies the audited historical CSV into a new
session folder, appends completed public candles there, and records forward
signals/trades in paper mode. The original historical CSV and strategy modules
are read-only inputs.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import sys
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd

BASE_URL = "https://data-api.binance.vision/api/v3/klines"
ONE_MINUTE_MS = 60_000
LIMIT = 1000
EXPECTED_BASE_SHA256 = "604835C55D98319CF6F26516040F6F285E02152B6EE984238C0D3359C2DBDE41"
EXPECTED_ORIGINAL_SHA256 = "95A40C752E8BF464220314EB2CA22022B3BA7F80941EC775EE53E639036E5D56"
CSV_COLUMNS = [
    "timestamp", "open", "high", "low", "close", "volume", "close_time",
    "quote_volume", "trades", "taker_buy_base_volume", "taker_buy_quote_volume",
]
SIGNAL_COLUMNS = [
    "decision_timestamp_utc", "execution_timestamp_utc", "execution_open",
    "action", "action_reason", "entry_qualified", "exit_condition",
    "parent_direction", "child_direction", "fib_618", "fibonacci_confirmed",
    "regime_zscore", "regime_acceptable", "relative_volume", "volume_confirmed",
    "normalized_slope", "normalized_acceleration", "momentum_confirmed",
    "position_before", "position_after", "equity_after_execution",
    "fee_bps_per_side", "slippage_bps_per_side",
]
class FatalSessionError(RuntimeError):
    """Stop a shadow session when execution history can no longer be trusted."""


TRADE_COLUMNS = [
    "entry_signal_timestamp_utc", "entry_execution_timestamp_utc", "entry_price",
    "exit_signal_timestamp_utc", "exit_execution_timestamp_utc", "exit_price",
    "holding_minutes", "gross_price_return", "net_return_on_entry_equity",
    "entry_equity_before_cost", "equity_after_exit", "fee_bps_per_side",
    "slippage_bps_per_side", "exit_reason",
]
EQUITY_COLUMNS = [
    "execution_timestamp_utc", "execution_open", "position_after",
    "equity_after_execution", "peak_equity", "drawdown_from_peak",
]
EVENT_COLUMNS = [
    "event_timestamp_utc", "event_type", "previous_decision_timestamp_utc",
    "new_decision_timestamp_utc", "missed_decision_bars", "position_before",
    "forced_exit", "equity_after_event", "note",
]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest().upper()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_utc(value: Any) -> str:
    stamp = pd.Timestamp(value)
    if stamp.tzinfo is None:
        stamp = stamp.tz_localize("UTC")
    else:
        stamp = stamp.tz_convert("UTC")
    return stamp.isoformat()


def write_json_atomic(path: Path, payload: dict) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    os.replace(temp, path)


def request_klines(symbol: str, start_ms: int, timeout: int = 20) -> list[list[Any]]:
    params = urlencode({"symbol": symbol.upper(), "interval": "1m", "startTime": int(start_ms), "limit": LIMIT})
    request = Request(
        f"{BASE_URL}?{params}",
        headers={"User-Agent": "ConvergenciaShadowResearch/1.0", "Accept": "application/json"},
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"Binance HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"Falha de rede ao consultar dados publicos: {exc.reason}") from exc
    if not isinstance(payload, list):
        raise RuntimeError(f"Resposta inesperada da API publica: {str(payload)[:500]}")
    return payload


def parse_kline(raw: list[Any]) -> dict[str, Any]:
    if len(raw) < 11:
        raise ValueError("Kline retornada com menos de 11 campos")
    open_ms = int(raw[0])
    close_ms = int(raw[6])
    return {
        "timestamp": pd.to_datetime(open_ms, unit="ms", utc=True).isoformat(),
        "open": float(raw[1]),
        "high": float(raw[2]),
        "low": float(raw[3]),
        "close": float(raw[4]),
        "volume": float(raw[5]),
        "close_time": pd.to_datetime(close_ms, unit="ms", utc=True).isoformat(),
        "quote_volume": float(raw[7]),
        "trades": int(raw[8]),
        "taker_buy_base_volume": float(raw[9]),
        "taker_buy_quote_volume": float(raw[10]),
        "_open_ms": open_ms,
        "_close_ms": close_ms,
    }


def read_cache_last_timestamp(cache_path: Path) -> pd.Timestamp:
    # Read only the final data row so the 20MB cache is not fully loaded just to sync.
    with cache_path.open("rb") as f:
        f.seek(0, os.SEEK_END)
        size = f.tell()
        if size == 0:
            raise RuntimeError(f"Cache vazio: {cache_path}")
        pos = max(0, size - 8192)
        f.seek(pos)
        tail = f.read().decode("utf-8-sig", errors="strict").splitlines()
    for line in reversed(tail):
        if line.strip() and not line.lower().startswith("timestamp,"):
            first = next(csv.reader([line]))[0]
            return pd.to_datetime(first, utc=True, errors="raise")
    # A very long final line is not expected, but safely fall back to pandas.
    last = pd.read_csv(cache_path, usecols=["timestamp"]).iloc[-1, 0]
    return pd.to_datetime(last, utc=True, errors="raise")


def append_closed_candles(cache_path: Path, symbol: str) -> tuple[int, dict[str, Any] | None]:
    """Backfill all new closed candles; return count and current in-progress kline."""
    last_ts = read_cache_last_timestamp(cache_path)
    start_ms = int(last_ts.timestamp() * 1000) + ONE_MINUTE_MS
    all_raw: list[list[Any]] = []
    next_start = start_ms
    latest_live: dict[str, Any] | None = None
    while True:
        page = request_klines(symbol, next_start)
        if not page:
            break
        all_raw.extend(page)
        last_open = int(page[-1][0])
        now_ms = int(time.time() * 1000)
        current_floor_ms = (now_ms // ONE_MINUTE_MS) * ONE_MINUTE_MS
        if len(page) < LIMIT or last_open >= current_floor_ms:
            break
        next_start = last_open + ONE_MINUTE_MS
        time.sleep(0.15)

    now_ms = int(time.time() * 1000)
    parsed = [parse_kline(row) for row in all_raw]
    # Store completed candles only. A still-forming candle is used solely as the
    # next candle's observable open for delayed paper execution.
    new_closed: list[dict[str, Any]] = []
    latest_open_ms = -1
    for row in parsed:
        open_ms = int(row["_open_ms"])
        close_ms = int(row["_close_ms"])
        if open_ms + ONE_MINUTE_MS <= now_ms and open_ms > latest_open_ms:
            if pd.Timestamp(row["timestamp"]) <= last_ts:
                continue
            new_closed.append({k: v for k, v in row.items() if not k.startswith("_")})
            latest_open_ms = open_ms
        elif open_ms <= now_ms < open_ms + ONE_MINUTE_MS:
            if latest_live is None or open_ms > int(latest_live["_open_ms"]):
                latest_live = row

    expected_ms = int(last_ts.timestamp() * 1000) + ONE_MINUTE_MS
    for row in new_closed:
        row_ms = int(pd.Timestamp(row["timestamp"]).timestamp() * 1000)
        if row_ms != expected_ms:
            raise FatalSessionError(
                "Lacuna/duplicata ao atualizar o cache sombra: "
                f"esperado {pd.to_datetime(expected_ms, unit='ms', utc=True).isoformat()}, "
                f"recebido {row['timestamp']}. Dados nao foram anexados. A sessao foi interrompida."
            )
        expected_ms += ONE_MINUTE_MS

    if new_closed:
        with cache_path.open("a", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=CSV_COLUMNS, extrasaction="ignore")
            for row in new_closed:
                writer.writerow(row)

    return len(new_closed), latest_live


def create_new_session(root: Path, symbol: str, source_csv: Path, source_hash: str,
                       fee_bps: float, slippage_bps: float) -> tuple[Path, dict]:
    stamp = utc_now().strftime("%Y%m%dT%H%M%SZ")
    session = root / "data" / "shadow" / f"session_{symbol.upper()}_{stamp}"
    session.mkdir(parents=True, exist_ok=False)
    cache = session / f"{symbol.upper()}_1m_cache.csv"
    shutil.copy2(source_csv, cache)
    state = {
        "schema_version": 1,
        "mode": "SHADOW_ONLY_NO_REAL_ORDERS",
        "symbol": symbol.upper(),
        "base_csv_sha256": source_hash,
        "started_at_utc": utc_now().isoformat(),
        "fee_bps_per_side": float(fee_bps),
        "slippage_bps_per_side": float(slippage_bps),
        "last_decision_timestamp_utc": None,
        "last_open_timestamp_utc": None,
        "last_open_price": None,
        "position_open": False,
        "equity": 1.0,
        "peak_equity": 1.0,
        "max_drawdown": 0.0,
        "open_trade": None,
        "closed_trades": 0,
        "decisions_processed": 0,
        "data_gap_count": 0,
        "missed_decision_bars": 0,
        "max_drawdown_is_lower_bound_due_to_gap": False,
    }
    return session, state


def init_logs(session: Path) -> None:
    for filename, columns in (
        ("shadow_signals.csv", SIGNAL_COLUMNS),
        ("shadow_trades.csv", TRADE_COLUMNS),
        ("shadow_equity.csv", EQUITY_COLUMNS),
        ("shadow_events.csv", EVENT_COLUMNS),
    ):
        path = session / filename
        if not path.exists():
            with path.open("w", newline="", encoding="utf-8") as stream:
                csv.writer(stream).writerow(columns)


def append_csv(session: Path, filename: str, columns: list[str], row: dict[str, Any]) -> None:
    with (session / filename).open("a", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
        writer.writerow({key: row.get(key, "") for key in columns})


def feature_entry_condition(row: pd.Series) -> bool:
    return bool(
        int(row["parent_direction"]) == 1
        and int(row["child_direction"]) == 1
        and bool(row["fibonacci_confirmed"])
        and bool(row["regime_acceptable"])
        and bool(row["volume_confirmed"])
        and bool(row["momentum_confirmed"])
    )


def exit_reasons(row: pd.Series) -> list[str]:
    reasons: list[str] = []
    if int(row["parent_direction"]) != 1:
        reasons.append("PAI_CONTEXT_LOST")
    if int(row["child_direction"]) == -1:
        reasons.append("FILHO_TREND_DOWN")
    slope = pd.to_numeric(pd.Series([row["normalized_slope"]]), errors="coerce").iloc[0]
    if pd.notna(slope) and float(slope) < 0:
        reasons.append("MOMENTUM_SLOPE_NEGATIVE")
    return reasons


def update_drawdown(state: dict) -> None:
    equity = float(state["equity"])
    state["peak_equity"] = max(float(state["peak_equity"]), equity)
    peak = float(state["peak_equity"])
    dd = equity / peak - 1.0 if peak > 0 else 0.0
    state["max_drawdown"] = min(float(state["max_drawdown"]), dd)


def process_decisions(root: Path, session: Path, state: dict, latest_live: dict[str, Any] | None) -> int:
    cache = session / f"{state['symbol']}_1m_cache.csv"
    frame = pd.read_csv(cache)
    if frame.empty:
        raise RuntimeError("Cache sombra sem candles")

    # Require no gaps before calculating rolling indicators.
    ts = pd.to_datetime(frame["timestamp"], format="ISO8601", utc=True, errors="raise")
    deltas = ts.diff().dropna()
    if not deltas.eq(pd.Timedelta(minutes=1)).all():
        raise RuntimeError("Cache sombra tem lacunas; sinais pausados para nao calcular com dados incompletos.")

    src = root / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    from convergencia.strategy import StrategyConfig, generate_strategy_signals

    features = generate_strategy_signals(frame, StrategyConfig())
    feature_ts = pd.to_datetime(features["timestamp"], format="ISO8601", utc=True, errors="raise")
    feature_map = {stamp.value: idx for idx, stamp in enumerate(feature_ts)}

    # Next-open prices are from closed cache candles or the currently forming
    # candle's public open. The forming candle is never fed into feature calc.
    open_map: dict[int, float] = {}
    for i, stamp in enumerate(feature_ts):
        open_map[stamp.value] = float(features.iloc[i]["open"])
    if latest_live is not None:
        open_map[int(pd.Timestamp(latest_live["timestamp"]).value)] = float(latest_live["open"])

    marker = pd.Timestamp(state["last_decision_timestamp_utc"])
    if marker.tzinfo is None:
        marker = marker.tz_localize("UTC")
    else:
        marker = marker.tz_convert("UTC")
    ready = [i for i, stamp in enumerate(feature_ts) if stamp > marker and (stamp + pd.Timedelta(minutes=1)).value in open_map]
    if not ready:
        return 0
    # Never retroactively simulate fills at historical next-open prices after
    # a process/network outage. This session is no longer a valid prospective
    # observation; stop and start a fresh session instead of inventing fills.
    if len(ready) > 1:
        # Do not invent executions at past openings. Re-anchor the shadow account
        # at the current live open; if a paper position was open, mark its endpoint
        # return and force-close it now. The report flags drawdown as a lower bound
        # because intra-gap prices were not observed by this process.
        current_live_ts = pd.Timestamp(latest_live["timestamp"]) if latest_live is not None else None
        latest_closed_ts = feature_ts.iloc[-1]
        if current_live_ts is None or current_live_ts != latest_closed_ts + pd.Timedelta(minutes=1):
            raise FatalSessionError("Nao foi possivel reancorar a sessao no open corrente depois de uma lacuna.")
        old_marker = state["last_decision_timestamp_utc"]
        was_open = bool(state["position_open"])
        current_price = float(latest_live["open"])
        if was_open:
            previous_price = float(state["last_open_price"])
            if previous_price <= 0 or current_price <= 0:
                raise FatalSessionError("Preco invalido ao reancorar posicao sombra.")
            state["equity"] = float(state["equity"]) * (current_price / previous_price)
            trade = state.get("open_trade")
            if not trade:
                raise FatalSessionError("Posicao sombra aberta sem metadados ao recuperar lacuna.")
            cost_rate = (float(state["fee_bps_per_side"]) + float(state["slippage_bps_per_side"])) / 10_000.0
            state["equity"] = float(state["equity"]) * (1.0 - cost_rate)
            entry_price = float(trade["entry_price"])
            entry_equity = float(trade["entry_equity_before_cost"])
            append_csv(session, "shadow_trades.csv", TRADE_COLUMNS, {
                "entry_signal_timestamp_utc": trade["entry_signal_timestamp_utc"],
                "entry_execution_timestamp_utc": trade["entry_execution_timestamp_utc"],
                "entry_price": entry_price,
                "exit_signal_timestamp_utc": "",
                "exit_execution_timestamp_utc": current_live_ts.isoformat(),
                "exit_price": current_price,
                "holding_minutes": int((current_live_ts - pd.Timestamp(trade["entry_execution_timestamp_utc"])).total_seconds() / 60),
                "gross_price_return": current_price / entry_price - 1.0,
                "net_return_on_entry_equity": float(state["equity"]) / entry_equity - 1.0 if entry_equity > 0 else "",
                "entry_equity_before_cost": entry_equity,
                "equity_after_exit": float(state["equity"]),
                "fee_bps_per_side": state["fee_bps_per_side"],
                "slippage_bps_per_side": state["slippage_bps_per_side"],
                "exit_reason": "DATA_GAP_FORCED_EXIT_NOT_STRATEGY_SIGNAL",
            })
            state["position_open"] = False
            state["open_trade"] = None
            state["closed_trades"] = int(state["closed_trades"]) + 1
        update_drawdown(state)
        state["data_gap_count"] = int(state.get("data_gap_count", 0)) + 1
        state["missed_decision_bars"] = int(state.get("missed_decision_bars", 0)) + len(ready)
        state["max_drawdown_is_lower_bound_due_to_gap"] = True
        state["last_decision_timestamp_utc"] = latest_closed_ts.isoformat()
        state["last_open_timestamp_utc"] = current_live_ts.isoformat()
        state["last_open_price"] = current_price
        append_csv(session, "shadow_events.csv", EVENT_COLUMNS, {
            "event_timestamp_utc": utc_now().isoformat(),
            "event_type": "DATA_GAP_REANCHORED_NO_RETROACTIVE_FILLS",
            "previous_decision_timestamp_utc": old_marker,
            "new_decision_timestamp_utc": latest_closed_ts.isoformat(),
            "missed_decision_bars": len(ready),
            "position_before": was_open,
            "forced_exit": was_open,
            "equity_after_event": float(state["equity"]),
            "note": "Sinais perdidos foram ignorados; nenhum fill em abertura historica foi simulado. DD intralacuna nao e conhecido.",
        })
        print(
            f"LACUNA DE DADOS: {len(ready)} decisoes nao foram processadas em tempo real. "
            "Nenhum fill retroativo foi criado; estado reancorado no open atual."
        )
        return 0
    if latest_live is None or (feature_ts.iloc[ready[0]] + pd.Timedelta(minutes=1)) != pd.Timestamp(latest_live["timestamp"]):
        raise FatalSessionError(
            "A abertura de execucao nao e a vela corrente; evitar fill retroativo. Sessao interrompida."
        )

    cost_rate = (float(state["fee_bps_per_side"]) + float(state["slippage_bps_per_side"])) / 10_000.0
    last_open_ts = pd.Timestamp(state["last_open_timestamp_utc"])
    if last_open_ts.tzinfo is None:
        last_open_ts = last_open_ts.tz_localize("UTC")
    else:
        last_open_ts = last_open_ts.tz_convert("UTC")
    last_open_price = float(state["last_open_price"])
    processed = 0

    for idx in ready:
        row = features.iloc[idx]
        decision_ts = feature_ts.iloc[idx]
        execution_ts = decision_ts + pd.Timedelta(minutes=1)
        execution_key = execution_ts.value
        if execution_key not in open_map:
            continue
        execution_open = float(open_map[execution_key])

        # Keep strict 1m state continuity. A skipped candle invalidates results.
        if decision_ts != last_open_ts:
            raise FatalSessionError(
                "Estado sombra fora de sequencia: decisao em " + decision_ts.isoformat()
                + " mas ultimo open processado foi " + last_open_ts.isoformat()
                + ". A sessao foi interrompida para evitar simulacao incorreta."
            )

        position_before = bool(state["position_open"])
        equity_before_action = float(state["equity"])

        # Realize the open-to-open price move while the existing position was active.
        if position_before:
            if last_open_price <= 0 or execution_open <= 0:
                raise RuntimeError("Preco de abertura invalido no passo sombra")
            state["equity"] = float(state["equity"]) * (execution_open / last_open_price)

        entry_ok = feature_entry_condition(row)
        exits = exit_reasons(row)
        action = "HOLD"
        reason = ""

        if position_before and exits:
            action = "SELL_EXIT"
            reason = "+".join(exits)
            trade = state.get("open_trade")
            if not trade:
                raise RuntimeError("Posicao aberta sem metadados de operacao")
            equity_before_exit_cost = float(state["equity"])
            state["equity"] = equity_before_exit_cost * (1.0 - cost_rate)
            entry_price = float(trade["entry_price"])
            gross_trade = execution_open / entry_price - 1.0
            entry_equity = float(trade["entry_equity_before_cost"])
            trade_row = {
                "entry_signal_timestamp_utc": trade["entry_signal_timestamp_utc"],
                "entry_execution_timestamp_utc": trade["entry_execution_timestamp_utc"],
                "entry_price": entry_price,
                "exit_signal_timestamp_utc": decision_ts.isoformat(),
                "exit_execution_timestamp_utc": execution_ts.isoformat(),
                "exit_price": execution_open,
                "holding_minutes": int((execution_ts - pd.Timestamp(trade["entry_execution_timestamp_utc"])).total_seconds() / 60),
                "gross_price_return": gross_trade,
                "net_return_on_entry_equity": (float(state["equity"]) / entry_equity - 1.0) if entry_equity > 0 else float("nan"),
                "entry_equity_before_cost": entry_equity,
                "equity_after_exit": float(state["equity"]),
                "fee_bps_per_side": state["fee_bps_per_side"],
                "slippage_bps_per_side": state["slippage_bps_per_side"],
                "exit_reason": reason,
            }
            append_csv(session, "shadow_trades.csv", TRADE_COLUMNS, trade_row)
            state["position_open"] = False
            state["open_trade"] = None
            state["closed_trades"] = int(state["closed_trades"]) + 1
        elif not position_before and entry_ok:
            action = "BUY_ENTRY"
            reason = "ALL_ENTRY_CONFIRMATIONS"
            state["open_trade"] = {
                "entry_signal_timestamp_utc": decision_ts.isoformat(),
                "entry_execution_timestamp_utc": execution_ts.isoformat(),
                "entry_price": execution_open,
                "entry_equity_before_cost": float(state["equity"]),
            }
            state["equity"] = float(state["equity"]) * (1.0 - cost_rate)
            state["position_open"] = True
        elif position_before:
            action = "HOLD_POSITION"
            reason = "EXIT_NOT_CONFIRMED"
        else:
            reason = "ENTRY_CONFIRMATIONS_NOT_ALL_MET"

        update_drawdown(state)
        signal_row = {
            "decision_timestamp_utc": decision_ts.isoformat(),
            "execution_timestamp_utc": execution_ts.isoformat(),
            "execution_open": execution_open,
            "action": action,
            "action_reason": reason,
            "entry_qualified": entry_ok,
            "exit_condition": bool(exits),
            "parent_direction": int(row["parent_direction"]),
            "child_direction": int(row["child_direction"]),
            "fib_618": float(row["fib_618"]) if pd.notna(row["fib_618"]) else "",
            "fibonacci_confirmed": bool(row["fibonacci_confirmed"]),
            "regime_zscore": float(row["regime_zscore"]) if pd.notna(row["regime_zscore"]) else "",
            "regime_acceptable": bool(row["regime_acceptable"]),
            "relative_volume": float(row["relative_volume"]) if pd.notna(row["relative_volume"]) else "",
            "volume_confirmed": bool(row["volume_confirmed"]),
            "normalized_slope": float(row["normalized_slope"]) if pd.notna(row["normalized_slope"]) else "",
            "normalized_acceleration": float(row["normalized_acceleration"]) if pd.notna(row["normalized_acceleration"]) else "",
            "momentum_confirmed": bool(row["momentum_confirmed"]),
            "position_before": position_before,
            "position_after": bool(state["position_open"]),
            "equity_after_execution": float(state["equity"]),
            "fee_bps_per_side": state["fee_bps_per_side"],
            "slippage_bps_per_side": state["slippage_bps_per_side"],
        }
        append_csv(session, "shadow_signals.csv", SIGNAL_COLUMNS, signal_row)
        append_csv(session, "shadow_equity.csv", EQUITY_COLUMNS, {
            "execution_timestamp_utc": execution_ts.isoformat(),
            "execution_open": execution_open,
            "position_after": bool(state["position_open"]),
            "equity_after_execution": float(state["equity"]),
            "peak_equity": float(state["peak_equity"]),
            "drawdown_from_peak": float(state["equity"]) / float(state["peak_equity"]) - 1.0 if state["peak_equity"] else 0.0,
        })
        state["last_decision_timestamp_utc"] = decision_ts.isoformat()
        state["last_open_timestamp_utc"] = execution_ts.isoformat()
        state["last_open_price"] = execution_open
        state["decisions_processed"] = int(state["decisions_processed"]) + 1
        last_open_ts = execution_ts
        last_open_price = execution_open
        processed += 1

    if processed:
        write_json_atomic(session / "state.json", state)
    return processed


def bootstrap_state(state: dict, cache_path: Path, live: dict[str, Any]) -> dict:
    frame = pd.read_csv(cache_path, usecols=["timestamp"])
    if frame.empty:
        raise RuntimeError("Cache inicial sem candles fechados")
    latest_closed = pd.to_datetime(frame["timestamp"].iloc[-1], utc=True)
    live_ts = pd.to_datetime(live["timestamp"], utc=True)
    expected_live = latest_closed + pd.Timedelta(minutes=1)
    if live_ts != expected_live:
        raise RuntimeError(
            f"Candle em formacao inesperado. Esperado {expected_live.isoformat()}, recebido {live_ts.isoformat()}"
        )
    state["last_decision_timestamp_utc"] = latest_closed.isoformat()
    state["last_open_timestamp_utc"] = live_ts.isoformat()
    state["last_open_price"] = float(live["open"])
    return state


def write_summary(session: Path, state: dict, latest_live: dict[str, Any] | None) -> None:
    equity = float(state["equity"])
    marked_equity = equity
    if state.get("position_open") and latest_live is not None and state.get("last_open_price"):
        # This is display-only mark-to-market; state remains anchored at the last processed open.
        latest_close = float(latest_live["close"])
        marked_equity = equity * (latest_close / float(state["last_open_price"]))
    summary = {
        **state,
        "updated_at_utc": utc_now().isoformat(),
        "equity_marked_to_latest_price_display_only": marked_equity,
        "open_position_unrealized_display_only": bool(state.get("position_open")),
        "session_directory": str(session),
        "orders_sent": 0,
        "live_broker_connected": False,
        "notes": [
            "Somente shadow/paper trading com dados publicos; nenhuma ordem real e enviada.",
            "O CSV historico base e preservado; cache e logs ficam nesta pasta de sessao.",
            "Sinais sao calculados apos candle de 1m fechar e simulados na abertura seguinte.",
            "Taxa e slippage sao hipoteses; resultado prospectivo nao garante rentabilidade futura.",
            "O saldo marcado pelo ultimo preco e apenas informativo e nao substitui o estado persistido ao open.",
            "Se houver lacuna/downtime, sinais perdidos nao sao executados retroativamente; a posicao pode ser encerrada no open atual e o drawdown maximo passa a ser apenas limite inferior.",
        ],
    }
    write_json_atomic(session / "summary.json", summary)


def run_self_test() -> None:
    # Check candle parsing and edge timing without any network request or file writes.
    raw = [1761000000000, "100", "102", "99", "101", "10", 1761000059999, "1010", 25, "4", "404", "0"]
    parsed = parse_kline(raw)
    assert parsed["open"] == 100.0 and parsed["close"] == 101.0
    assert parsed["quote_volume"] == 1010.0
    assert parsed["timestamp"].endswith("+00:00")
    # Position return + entry and exit costs: entry/exit costs are multiplicative.
    equity = 1.0
    cost = 0.0015
    equity *= 1.0 - cost
    equity *= 105.0 / 100.0
    equity *= 1.0 - cost
    assert math.isclose(equity, (1 - cost) * 1.05 * (1 - cost), rel_tol=1e-12)
    print("SELF-TEST PASSED: kline parsing and paper cost arithmetic; no network, no file writes.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1], help="Raiz do projeto 3 Pro")
    parser.add_argument("--symbol", default="BTCUSDT", help="Par Spot publico, ex.: BTCUSDT")
    parser.add_argument("--fee-bps", type=float, default=10.0, help="Taxa estimada por lado em basis points")
    parser.add_argument("--slippage-bps", type=float, default=5.0, help="Slippage estimado por lado em basis points")
    parser.add_argument("--poll-seconds", type=int, default=10, help="Intervalo de verificacao, entre 5 e 60 segundos")
    parser.add_argument("--once", action="store_true", help="Sincroniza e prepara uma sessao, depois sai")
    parser.add_argument("--resume", type=Path, help="Retoma uma sessao sombra existente")
    parser.add_argument("--self-test", action="store_true", help="Testes locais sem rede ou alteracao de arquivos")
    args = parser.parse_args()

    if args.self_test:
        run_self_test()
        return 0
    if not (5 <= args.poll_seconds <= 60):
        parser.error("--poll-seconds precisa estar entre 5 e 60")
    if not np.isfinite([args.fee_bps, args.slippage_bps]).all() or min(args.fee_bps, args.slippage_bps) < 0:
        parser.error("Taxa e slippage precisam ser finitos e nao negativos")

    root = args.root.resolve()
    source_csv = root / "data" / "raw" / f"{args.symbol.upper()}_1m.csv"
    original_txt = root / "Matematica trindade.txt"
    if not source_csv.is_file():
        raise FileNotFoundError(f"Historico base nao encontrado: {source_csv}")
    if not original_txt.is_file():
        raise FileNotFoundError(f"Arquivo original nao encontrado: {original_txt}")

    base_hash = sha256_file(source_csv)
    original_hash = sha256_file(original_txt)
    if base_hash != EXPECTED_BASE_SHA256:
        raise RuntimeError("SHA256 do historico base difere do CSV auditado. Sessao cancelada.")
    if original_hash != EXPECTED_ORIGINAL_SHA256:
        raise RuntimeError("SHA256 do arquivo matematico original difere do inventario. Sessao cancelada.")

    is_new = args.resume is None
    if is_new:
        session, state = create_new_session(root, args.symbol, source_csv, base_hash, args.fee_bps, args.slippage_bps)
        cache_path = session / f"{args.symbol.upper()}_1m_cache.csv"
        init_logs(session)
        print("Nova sessao sombra criada:", session)
        print("Historico base copiado para cache separado; original nao sera alterado.")
    else:
        session = args.resume.resolve()
        if not session.is_dir():
            raise FileNotFoundError(f"Pasta de sessao nao encontrada: {session}")
        cache_path = session / f"{args.symbol.upper()}_1m_cache.csv"
        state_path = session / "state.json"
        if not cache_path.is_file() or not state_path.is_file():
            raise RuntimeError("Sessao nao contem cache e state.json validos para retomar")
        state = json.loads(state_path.read_text(encoding="utf-8"))
        if state.get("base_csv_sha256") != base_hash or state.get("symbol") != args.symbol.upper():
            raise RuntimeError("A sessao pertence a outro historico-base/par. Retomada cancelada.")
        if float(state.get("fee_bps_per_side")) != float(args.fee_bps) or float(state.get("slippage_bps_per_side")) != float(args.slippage_bps):
            raise RuntimeError("Os custos informados diferem dos custos congelados na sessao. Retomada cancelada.")
        init_logs(session)
        print("Retomando sessao sombra:", session)

    print("Fonte de dados: endpoint publico Binance Spot; nenhuma chave API e utilizada.")
    print(f"Par={args.symbol.upper()} | taxa={args.fee_bps:g} bps/lado | slippage={args.slippage_bps:g} bps/lado")
    print("Modo: SHADOW ONLY. Nenhuma corretora e conectada e nenhuma ordem real pode ser enviada por este script.")

    try:
        while True:
            try:
                added, live = append_closed_candles(cache_path, args.symbol)
                if live is None:
                    raise RuntimeError("A API ainda nao retornou o candle em formacao; tentando novamente")

                if is_new and state.get("last_decision_timestamp_utc") is None:
                    state = bootstrap_state(state, cache_path, live)
                    write_json_atomic(session / "state.json", state)
                    write_summary(session, state, live)
                    print("Baseline da sessao definido em:", state["last_decision_timestamp_utc"])
                    print("Primeira execucao futura ocorrera somente apos um novo candle fechado.")
                    is_new = False
                else:
                    # Recompute only when there is a closed candle beyond the last
                    # committed decision. This also retries a transient processing
                    # failure even when the candle was already appended in a prior cycle.
                    latest_cached_ts = read_cache_last_timestamp(cache_path)
                    last_decision_ts = pd.Timestamp(state["last_decision_timestamp_utc"])
                    if last_decision_ts.tzinfo is None:
                        last_decision_ts = last_decision_ts.tz_localize("UTC")
                    else:
                        last_decision_ts = last_decision_ts.tz_convert("UTC")
                    has_unprocessed = latest_cached_ts > last_decision_ts
                    processed = process_decisions(root, session, state, live) if has_unprocessed else 0
                    if added or processed:
                        write_json_atomic(session / "state.json", state)
                        write_summary(session, state, live)
                        print(
                            f"[{utc_now().isoformat()}] candles novos={added} | decisoes processadas={processed} "
                            f"| trades fechados={state['closed_trades']} | posicao={'ABERTA' if state['position_open'] else 'FLAT'} "
                            f"| equity no ultimo open={float(state['equity']):.6f} | maxDD={float(state['max_drawdown']):.2%}"
                        )
                if args.once:
                    write_summary(session, state, live)
                    print("SESSAO PREPARADA. Nenhuma ordem real foi enviada.")
                    print("Diretorio da sessao para retomar:", session)
                    print("Comando de retomada: python scripts/run_shadow_convergencia.py --root . --resume \"" + str(session) + "\"")
                    return 0
                time.sleep(args.poll_seconds)
            except KeyboardInterrupt:
                raise
            except FatalSessionError as exc:
                print(f"ERRO FATAL DA SESSAO: {exc}", file=sys.stderr)
                write_json_atomic(session / "state.json", state)
                write_summary(session, state, None)
                print("Nenhuma ordem real foi enviada. Use uma nova sessao apos verificar o historico.", file=sys.stderr)
                return 2
            except Exception as exc:
                print(f"AVISO: ciclo sombra nao processado: {exc}", file=sys.stderr)
                # Retry transient network/API failures. A missed execution sequence
                # raises FatalSessionError above and is never replayed retroactively.
                write_json_atomic(session / "state.json", state)
                write_summary(session, state, None)
                if args.once:
                    raise
                time.sleep(max(args.poll_seconds, 10))
    except KeyboardInterrupt:
        write_json_atomic(session / "state.json", state)
        write_summary(session, state, None)
        print("\nSessao pausada pelo usuario. Estado e logs preservados.")
        print("Pasta da sessao:", session)
        print("Retomar com: python scripts/run_shadow_convergencia.py --root . --resume \"" + str(session) + "\"")
        return 130


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        raise SystemExit(2)
