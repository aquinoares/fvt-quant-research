import numpy as np
import pandas as pd
import pytest

from convergencia.features.fibonacci import retracement_levels
from convergencia.features.fractal import direction_alignment
from convergencia.features.momentum import normalized_slope
from convergencia.features.regime import rolling_equilibrium
from convergencia.features.volume import trapezoidal_activity, relative_volume
from convergencia.signals import convergence_signal
from convergencia.data import validate_ohlcv
from convergencia.backtest import run_backtest


def test_fibonacci_618_level():
    levels = retracement_levels(100, 200)
    assert levels["61.8%"] == pytest.approx(138.2)


def test_fibonacci_rejects_invalid_wave():
    with pytest.raises(ValueError):
        retracement_levels(200, 100)


def test_fractal_alignment_only_compares_directions():
    assert direction_alignment(1, 1) == 1
    assert direction_alignment(-1, -1) == -1
    assert direction_alignment(1, -1) == 0
    assert direction_alignment(0, 0) == 0


def test_rolling_equilibrium():
    result = rolling_equilibrium([1, 2, 3], window=3)
    assert result["center"] == pytest.approx(2.0)
    assert result["upper"] == pytest.approx(4.0)
    assert result["lower"] == pytest.approx(0.0)


def test_trapezoidal_activity():
    assert trapezoidal_activity([2, 4, 6], interval=1) == pytest.approx(8.0)


def test_relative_volume_uses_previous_bars_as_baseline():
    assert relative_volume([2, 2, 2, 6], lookback=3) == pytest.approx(3.0)


def test_normalized_slope_constant_prices_is_zero():
    assert normalized_slope([100, 100, 100, 100]) == pytest.approx(0.0)


def test_convergence_requires_all_confirmations():
    assert convergence_signal(1, 1, True, True, True) == 1
    assert convergence_signal(1, 1, True, False, True) == 0
    assert convergence_signal(1, -1, True, True, True) == 0


def test_validate_ohlcv_sorts_timestamps():
    frame = pd.DataFrame({
        "timestamp": ["2026-01-01T00:01:00Z", "2026-01-01T00:00:00Z"],
        "open": [101, 100], "high": [102, 101], "low": [100, 99],
        "close": [101, 100], "volume": [10, 12],
    })
    result = validate_ohlcv(frame)
    assert result["timestamp"].is_monotonic_increasing


def test_backtest_delays_signal_charges_costs_and_spot_is_long_only():
    candles = pd.DataFrame({"open": [100.0, 100.0, 110.0, 110.0]})
    # BUY no fechamento do candle 0; SELL/EXIT no fechamento do candle 2.
    result = run_backtest(candles, [1, 0, -1, 0], fee_bps=10, slippage_bps=5)
    assert result["position"].tolist() == [0.0, 1.0, 1.0]
    assert set(result["position"].unique()).issubset({0.0, 1.0})
    assert result["gross_return"].iloc[1] == pytest.approx(0.10)
    assert result["costs"].iloc[0] == pytest.approx(0.0015)  # entrada no open seguinte
    assert result["costs"].iloc[2] == pytest.approx(0.0015)  # saida no open seguinte
    assert result["net_return"].iloc[1] == pytest.approx(0.10)
    assert result["net_return"].iloc[2] == pytest.approx(-0.0015)
    assert len(result) == len(candles) - 1