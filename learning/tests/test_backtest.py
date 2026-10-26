from learning.experiments.backtest import ROUND_TRIP_COST_BPS, run_experiment


def test_backtest_has_temporal_split_cost_and_required_warnings():
    candles, price = [], 100.0
    for i in range(240):
        open_price = price
        price *= 1.004 if i % 11 != 0 else 0.995
        candles.append({"open_time_ms": i * 14_400_000, "open": open_price, "close": price})
    result = run_experiment(candles)
    assert result["label"] == "EXPLORATÓRIO — NÃO É PROVA"
    assert result["round_trip_cost_bps"] == ROUND_TRIP_COST_BPS == 30
    assert result["train_fraction"] == 0.70
    assert result["train"]["candles"] == 168
    assert result["validation"]["candles"] == 72
    assert any("sobreajuste" in warning for warning in result["warnings"])
    assert "net_return" in result["train"] and "buy_hold_net_return" in result["validation"]


def test_small_sample_does_not_claim_performance():
    result = run_experiment([{"open_time_ms": i, "open": 100.0, "close": 101.0} for i in range(10)])
    assert result["train"]["status"] == "insufficient_data"
    assert result["validation"]["status"] == "insufficient_data"
    assert any("inconclusivo" in warning for warning in result["warnings"])
