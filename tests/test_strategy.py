import numpy as np
import pandas as pd
import pytest

from convergencia.strategy import StrategyConfig, generate_strategy_signals


def sample_candles(n=1800, seed=7):
    rng = np.random.default_rng(seed)
    t = np.arange(n, dtype="float64")
    close = 100.0 * np.exp(0.00012 * t + 0.002 * np.sin(t / 13.0) + np.cumsum(rng.normal(0, 0.0007, n)))
    open_ = np.r_[close[0], close[:-1]]
    high = np.maximum(open_, close) * (1 + rng.uniform(0.0001, 0.0015, n))
    low = np.minimum(open_, close) * (1 - rng.uniform(0.0001, 0.0015, n))
    volume = rng.lognormal(mean=4.2, sigma=0.5, size=n)
    quote_volume = volume * close
    return pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01T00:00:00Z", periods=n, freq="min"),
        "open": open_, "high": high, "low": low, "close": close,
        "volume": volume, "quote_volume": quote_volume,
    })


def test_strategy_outputs_one_valid_signal_per_candle():
    frame = sample_candles(1800)
    result = generate_strategy_signals(frame)
    assert len(result) == len(frame)
    assert result["signal"].isin([-1, 0, 1]).all()
    assert set(result["parent_direction"].unique()).issubset({-1, 0, 1})
    assert set(result["child_direction"].unique()).issubset({-1, 0, 1})


def test_no_buy_before_parent_context_warmup():
    frame = sample_candles(700)
    result = generate_strategy_signals(frame)
    assert not (result["signal"] == 1).any()


def test_future_changes_do_not_change_past_features_or_signals():
    frame = sample_candles(1800)
    original = generate_strategy_signals(frame)
    changed = frame.copy()
    cut = 1500
    changed.loc[cut:, "open"] *= 1.35
    changed.loc[cut:, "high"] *= 1.35
    changed.loc[cut:, "low"] *= 1.35
    changed.loc[cut:, "close"] *= 1.35
    changed.loc[cut:, "quote_volume"] *= 1.7
    altered = generate_strategy_signals(changed)
    columns = ["parent_direction", "child_direction", "fib_618", "regime_zscore", "relative_volume", "normalized_slope", "normalized_acceleration", "signal"]
    pd.testing.assert_frame_equal(
        original.loc[:cut - 1, columns].reset_index(drop=True),
        altered.loc[:cut - 1, columns].reset_index(drop=True),
        check_dtype=False,
        check_exact=False,
        rtol=1e-10,
        atol=1e-10,
    )


def test_gaps_are_rejected():
    frame = sample_candles(1800)
    frame = frame.drop(index=500).reset_index(drop=True)
    with pytest.raises(ValueError, match="contiguous 1-minute"):
        generate_strategy_signals(frame)


def test_invalid_configuration_is_rejected():
    with pytest.raises(ValueError, match="parent_fast"):
        StrategyConfig(parent_fast=50, parent_slow=20)


def test_buy_requires_all_confirmation_modules():
    frame = sample_candles(1800)
    result = generate_strategy_signals(frame)
    buys = result.loc[result["signal"] == 1]
    if len(buys):
        assert (buys["parent_direction"] == 1).all()
        assert (buys["child_direction"] == 1).all()
        assert buys["fibonacci_confirmed"].all()
        assert buys["regime_acceptable"].all()
        assert buys["volume_confirmed"].all()
        assert buys["momentum_confirmed"].all()


def test_exit_events_only_occur_while_position_is_open():
    frame = sample_candles(3600, seed=19)
    result = generate_strategy_signals(frame)
    in_position = False
    entries = 0
    exits = 0
    for event in result["signal"].to_numpy():
        if event == 1:
            assert not in_position, "duplicate entry event while already long"
            in_position = True
            entries += 1
        elif event == -1:
            assert in_position, "exit event emitted while flat"
            in_position = False
            exits += 1
    assert entries >= exits
    assert entries - exits in (0, 1)  # final open position may be liquidated by the backtester
