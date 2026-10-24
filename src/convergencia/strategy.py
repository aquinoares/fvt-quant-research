"""Causal baseline strategy for Pai/Filho/Trindade convergence.

This is an exploratory rule set, not evidence of profitability. It uses only
completed 1-minute candles and fully closed 15-minute aggregates.
"""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np
import pandas as pd

from .data import validate_ohlcv


@dataclass(frozen=True)
class StrategyConfig:
    parent_fast: int = 20
    parent_slow: int = 50
    child_fast: int = 9
    child_slow: int = 21
    fib_lookback: int = 60
    atr_window: int = 14
    volume_lookback: int = 20
    relative_volume_min: float = 1.2
    momentum_window: int = 10
    regime_window: int = 60
    min_regime_z: float = -2.5
    max_regime_z: float = 2.0

    def __post_init__(self) -> None:
        for name in (
            "parent_fast", "parent_slow", "child_fast", "child_slow",
            "fib_lookback", "atr_window", "volume_lookback",
            "momentum_window", "regime_window",
        ):
            if getattr(self, name) < 2:
                raise ValueError(f"{name} must be >= 2")
        if self.parent_fast >= self.parent_slow:
            raise ValueError("parent_fast must be less than parent_slow")
        if self.child_fast >= self.child_slow:
            raise ValueError("child_fast must be less than child_slow")
        if not np.isfinite(self.relative_volume_min) or self.relative_volume_min < 0:
            raise ValueError("relative_volume_min must be finite and non-negative")
        if not np.isfinite([self.min_regime_z, self.max_regime_z]).all():
            raise ValueError("regime thresholds must be finite")
        if self.min_regime_z >= self.max_regime_z:
            raise ValueError("min_regime_z must be less than max_regime_z")


def _parent_direction(frame: pd.DataFrame, config: StrategyConfig) -> pd.DataFrame:
    """Create 15m bars and expose each direction only after that bar closes."""
    indexed = frame.set_index("timestamp")
    aggregation = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }
    # A quote-volume sum is not required for the parent trend, but retaining it
    # makes the aggregation explicit and useful for future extensions.
    if "quote_volume" in frame.columns:
        aggregation["quote_volume"] = "sum"

    parent = indexed.resample("15min", label="left", closed="left").agg(aggregation)
    parent["bar_count"] = indexed["close"].resample("15min", label="left", closed="left").count()
    parent = parent.loc[parent["bar_count"] == 15].copy()
    if parent.empty:
        raise ValueError("Not enough complete 15-minute candles to build parent context")

    close = pd.to_numeric(parent["close"], errors="coerce")
    fast = close.ewm(span=config.parent_fast, adjust=False, min_periods=config.parent_fast).mean()
    slow = close.ewm(span=config.parent_slow, adjust=False, min_periods=config.parent_slow).mean()
    fast_rising = fast > fast.shift(3)
    fast_falling = fast < fast.shift(3)

    bullish = (close > fast) & (fast > slow) & fast_rising
    bearish = (close < fast) & (fast < slow) & fast_falling
    direction = pd.Series(0, index=parent.index, dtype="int8")
    direction.loc[bullish] = 1
    direction.loc[bearish] = -1

    mapped = pd.DataFrame({
        "available_at": parent.index + pd.Timedelta(minutes=15),
        "parent_direction": direction.to_numpy(),
        "parent_close": close.to_numpy(),
    }).sort_values("available_at")
    return mapped


def _rolling_log_slope(values: np.ndarray) -> float:
    """OLS slope of log-price over a fixed window, computed from current data."""
    if not np.isfinite(values).all() or (values <= 0).any():
        return np.nan
    logs = np.log(values)
    x = np.arange(len(logs), dtype="float64")
    x = x - x.mean()
    denom = float(np.dot(x, x))
    if denom <= 0:
        return 0.0
    centered_y = logs - logs.mean()
    return float(np.dot(x, centered_y) / denom)


def generate_strategy_signals(
    candles: pd.DataFrame,
    config: StrategyConfig | None = None,
) -> pd.DataFrame:
    """Return OHLCV plus causal features and event signals (1=buy, -1=exit, 0=hold).

    This first hypothesis is long-only spot: Fibonacci pullback, bullish alignment
    between the closed 15m parent and 1m child, acceptable regime, elevated volume,
    and positive slope plus positive change in normalized slope must all agree.
    A -1 is an exit instruction, never a short-sale instruction.
    """
    cfg = config or StrategyConfig()
    frame = validate_ohlcv(candles)
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], format="ISO8601", utc=True, errors="raise")
    frame = frame.sort_values("timestamp", kind="stable").reset_index(drop=True)

    timestamps = frame["timestamp"]
    differences = timestamps.diff().dropna()
    if not differences.eq(pd.Timedelta(minutes=1)).all():
        raise ValueError("Strategy requires contiguous 1-minute candles; fix gaps before signaling")

    out = frame.copy()
    close = out["close"].astype("float64")
    open_ = out["open"].astype("float64")
    high = out["high"].astype("float64")
    low = out["low"].astype("float64")

    # PAI: the 15m candle is only joinable once its timestamp + 15m is known.
    minute_map = pd.DataFrame({
        "minute_available_at": timestamps + pd.Timedelta(minutes=1),
    })
    parents = _parent_direction(out, cfg)
    mapped = pd.merge_asof(
        minute_map.sort_values("minute_available_at"),
        parents,
        left_on="minute_available_at",
        right_on="available_at",
        direction="backward",
        tolerance=pd.Timedelta(minutes=15),
        allow_exact_matches=True,
    )
    out["parent_direction"] = mapped["parent_direction"].fillna(0).astype("int8").to_numpy()
    out["parent_close"] = mapped["parent_close"].to_numpy()

    # FILHO: direction based only on the 1m close and its prior history.
    child_fast = close.ewm(span=cfg.child_fast, adjust=False, min_periods=cfg.child_fast).mean()
    child_slow = close.ewm(span=cfg.child_slow, adjust=False, min_periods=cfg.child_slow).mean()
    child_up = (close > child_fast) & (child_fast > child_slow) & (child_fast > child_fast.shift(3))
    child_down = (close < child_fast) & (child_fast < child_slow) & (child_fast < child_fast.shift(3))
    child_direction = pd.Series(0, index=out.index, dtype="int8")
    child_direction.loc[child_up] = 1
    child_direction.loc[child_down] = -1
    out["child_direction"] = child_direction

    # MODELO 1: the range reference excludes the current candle (shift(1)).
    prior_high = high.shift(1).rolling(cfg.fib_lookback, min_periods=cfg.fib_lookback).max()
    prior_low = low.shift(1).rolling(cfg.fib_lookback, min_periods=cfg.fib_lookback).min()
    out["fib_618"] = prior_high - 0.6180339887498949 * (prior_high - prior_low)

    # True range and ATR as a scale-aware touch tolerance.
    prev_close = close.shift(1)
    true_range = pd.concat(
        [(high - low), (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    out["atr"] = true_range.rolling(cfg.atr_window, min_periods=cfg.atr_window).mean()
    tolerance = 0.25 * out["atr"]
    fib_touch = (
        (low <= out["fib_618"] + tolerance)
        & (high >= out["fib_618"] - tolerance)
        & (close >= out["fib_618"])
        & (close > open_)
        & (close > prev_close)
    )
    out["fibonacci_confirmed"] = fib_touch.fillna(False)

    # MODELO 3: statistical regime proxy, not a Lorenz attractor.
    regime_mean = close.rolling(cfg.regime_window, min_periods=cfg.regime_window).mean()
    regime_std = close.rolling(cfg.regime_window, min_periods=cfg.regime_window).std(ddof=1)
    out["regime_zscore"] = ((close - regime_mean) / regime_std.replace(0.0, np.nan)).fillna(0.0)
    out["regime_acceptable"] = out["regime_zscore"].between(cfg.min_regime_z, cfg.max_regime_z, inclusive="both")

    # MODELO 4: quote-volume when available; otherwise estimated quote activity.
    if "quote_volume" in out.columns:
        quote_volume = pd.to_numeric(out["quote_volume"], errors="coerce")
        if quote_volume.isna().any() or not np.isfinite(quote_volume.to_numpy()).all() or (quote_volume < 0).any():
            raise ValueError("quote_volume contains invalid values")
    else:
        quote_volume = close * out["volume"].astype("float64")
    baseline = quote_volume.shift(1).rolling(cfg.volume_lookback, min_periods=cfg.volume_lookback).mean()
    out["relative_volume"] = quote_volume / baseline.replace(0.0, np.nan)
    out["volume_confirmed"] = out["relative_volume"] >= cfg.relative_volume_min

    # MODELO 5: normalized log-price slope and change in slope over a second window.
    log_slope = close.rolling(cfg.momentum_window, min_periods=cfg.momentum_window).apply(
        _rolling_log_slope, raw=True
    )
    log_returns = np.log(close).diff()
    return_volatility = log_returns.rolling(cfg.momentum_window, min_periods=cfg.momentum_window).std(ddof=1)
    out["normalized_slope"] = (log_slope / return_volatility.replace(0.0, np.nan)).replace([np.inf, -np.inf], np.nan)
    out["normalized_acceleration"] = out["normalized_slope"] - out["normalized_slope"].shift(cfg.momentum_window)
    out["momentum_confirmed"] = (out["normalized_slope"] > 0) & (out["normalized_acceleration"] > 0)

    # TRINDADE: all five model families contribute an explicit, auditable condition.
    buy = (
        (out["parent_direction"] == 1)
        & (out["child_direction"] == 1)
        & out["fibonacci_confirmed"]
        & out["regime_acceptable"]
        & out["volume_confirmed"]
        & out["momentum_confirmed"]
    )
    # Exit conditions are meaningful only while a simulated spot position is open.
    # Emit trade EVENTS (entry=1, exit=-1, otherwise 0), not a bearish/flat
    # classification on every bar. This keeps event counts interpretable and makes
    # the signal stream match run_backtest's event contract.
    exit_condition = (
        (out["parent_direction"] != 1)
        | (out["child_direction"] == -1)
        | (out["normalized_slope"] < 0)
    )
    events = np.zeros(len(out), dtype="int8")
    in_position = False
    buy_values = buy.fillna(False).to_numpy(dtype=bool)
    exit_values = exit_condition.fillna(False).to_numpy(dtype=bool)
    for i in range(len(out)):
        if not in_position and buy_values[i]:
            events[i] = 1
            in_position = True
        elif in_position and exit_values[i]:
            events[i] = -1
            in_position = False
    out["signal"] = events
    out["buy_confirmations"] = (
        (out["parent_direction"] == 1).astype("int8")
        + (out["child_direction"] == 1).astype("int8")
        + out["fibonacci_confirmed"].astype("int8")
        + out["regime_acceptable"].astype("int8")
        + out["volume_confirmed"].fillna(False).astype("int8")
        + out["momentum_confirmed"].fillna(False).astype("int8")
    )
    return out
