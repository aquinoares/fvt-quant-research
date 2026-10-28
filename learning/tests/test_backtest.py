import csv
import math

from learning.experiments import backtest
from learning.experiments.backtest import (
    COST_PER_SIDE,
    LABEL,
    MIN_COMPLETED_TRADES,
    ROUND_TRIP_COST_BPS,
    evaluate_segment,
    load_candles,
    run_experiment,
)

BAR_MS = 14_400_000


def make_candles(prices):
    return [
        {"open_time_ms": index * BAR_MS, "open": open_price, "close": close_price}
        for index, (open_price, close_price) in enumerate(prices)
    ]


def trending_candles(count=240):
    candles, price = [], 100.0
    for index in range(count):
        open_price = price
        price *= 1.004 if index % 11 != 0 else 0.995
        candles.append({"open_time_ms": index * BAR_MS, "open": open_price, "close": price})
    return candles


def oscillating_candles(count=600):
    candles, price = [], 100.0
    for index in range(count):
        open_price = price
        price *= 1.008 if (index // 15) % 2 == 0 else 0.992
        candles.append({"open_time_ms": index * BAR_MS, "open": open_price, "close": price})
    return candles


def test_backtest_has_temporal_split_cost_and_required_warnings():
    result = run_experiment(trending_candles())
    assert result["label"] == LABEL == "EXPLORATÓRIO — NÃO É PROVA"
    assert result["round_trip_cost_bps"] == ROUND_TRIP_COST_BPS == 30
    assert result["train_fraction"] == 0.70
    assert result["train"]["candles"] == 168
    assert result["validation"]["candles"] == 72
    assert any("sobreajuste" in warning for warning in result["warnings"])
    assert "net_return" in result["train"] and "buy_hold_net_return" in result["validation"]
    assert any("validação" in warning and "parâmetros" in warning for warning in result["warnings"])
    assert "1 barra" in result["execution_policy"]
    assert "30 bps" in result["benchmark_policy"]


def test_small_sample_does_not_claim_performance():
    result = run_experiment([{"open_time_ms": i, "open": 100.0, "close": 101.0} for i in range(10)])
    for segment in (result["train"], result["validation"]):
        assert segment["status"] == "insufficient_data"
        assert segment["net_return"] is None
        assert segment["raw_metrics"] is None
        assert segment["reason"]
    assert any("inconclusivo" in warning for warning in result["warnings"])


def test_signal_uses_only_past_data():
    candles = trending_candles()
    modified = [dict(row) for row in candles]
    modified[-1]["close"] *= 5.0
    baseline, changed = run_experiment(candles), run_experiment(modified)
    assert baseline["train"] == changed["train"]
    assert evaluate_segment(candles[:100]) == evaluate_segment(modified[:100])


def test_decision_bar_n_executes_at_open_of_bar_n_plus_1():
    prices = [(100.0, 100.0)] * 20 + [(100.0, 105.0), (90.0, 90.0)]
    segment = evaluate_segment(make_candles(prices))
    assert segment["completed_trades"] == 1
    expected = (1.0 - COST_PER_SIDE) ** 2 - 1.0
    assert math.isclose(segment["raw_metrics"]["net_return"], expected, rel_tol=0, abs_tol=1e-15)
    same_bar_wrong = (105.0 / 100.0) * (1.0 - COST_PER_SIDE) ** 2 - 1.0
    assert not math.isclose(segment["raw_metrics"]["net_return"], same_bar_wrong, rel_tol=0, abs_tol=1e-9)
    assert segment["raw_metrics"]["net_return"] < 0


def test_holding_return_is_contiguous_across_bar_gaps():
    prices = (
        [(100.0, 100.0)] * 20
        + [(100.0, 105.0), (100.0, 101.0), (110.0, 110.0), (110.0, 80.0), (80.0, 80.0)]
    )
    segment = evaluate_segment(make_candles(prices))
    assert segment["gap_transitions"] == 0
    expected = 0.8 * (1.0 - COST_PER_SIDE) ** 2 - 1.0
    assert math.isclose(segment["raw_metrics"]["net_return"], expected, rel_tol=0, abs_tol=1e-15)


def test_temporal_gap_is_detected_and_metrics_suppressed():
    candles = trending_candles()
    gapped = candles[:100] + candles[101:]
    segment = evaluate_segment(gapped[:168])
    assert segment["gap_transitions"] == 1
    assert segment["missing_bars_estimate"] == 1
    assert segment["status"] == "inconclusive"
    assert "lacuna" in segment["reason"]
    assert segment["net_return"] is None
    assert segment["raw_metrics"]["net_return"] is not None


def test_costs_are_applied_once_per_side_not_per_bar(monkeypatch):
    candles = oscillating_candles()
    segment = evaluate_segment(candles)
    assert segment["status"] == "ok"
    with_cost = segment["raw_metrics"]["net_return"] if segment["raw_metrics"] else segment["net_return"]
    trades = segment["completed_trades"]
    assert trades >= MIN_COMPLETED_TRADES
    monkeypatch.setattr(backtest, "COST_PER_SIDE", 0.0)
    without_cost_segment = evaluate_segment(candles)
    without_cost = (
        without_cost_segment["raw_metrics"]["net_return"]
        if without_cost_segment["raw_metrics"]
        else without_cost_segment["net_return"]
    )
    expected = (1.0 + without_cost) * (1.0 - COST_PER_SIDE) ** (2 * trades) - 1.0
    assert math.isclose(with_cost, expected, rel_tol=0, abs_tol=1e-12)


def test_split_is_strictly_temporal_without_validation_leakage():
    candles = trending_candles()
    result = run_experiment(candles)
    train_times = [row["open_time_ms"] for row in candles[:168]]
    validation_times = [row["open_time_ms"] for row in candles[168:]]
    assert max(train_times) < min(validation_times)
    assert result["train"]["candles"] + result["validation"]["candles"] == len(candles)
    modified = [dict(row) for row in candles]
    modified[-1]["close"] *= 7.0
    assert run_experiment(modified)["train"] == result["train"]


def test_fewer_than_ten_trades_is_inconclusive_with_null_headline_metrics():
    segment = evaluate_segment(trending_candles()[:60])
    assert segment["completed_trades"] < MIN_COMPLETED_TRADES
    assert segment["status"] == "inconclusive"
    assert "inconclusiva" in segment["reason"]
    assert segment["net_return"] is None
    assert segment["buy_hold_net_return"] is None
    assert segment["max_drawdown"] is None
    assert segment["raw_metrics"]["buy_hold_net_return"] is not None


def test_duplicate_timestamps_are_dropped_and_reported():
    candles = trending_candles()
    duplicated = candles + [dict(candles[50]), dict(candles[51])]
    result = run_experiment(duplicated)
    assert result["data_quality"]["duplicate_timestamps_dropped"] == 2
    assert result["train"]["candles"] == 168
    assert result["validation"]["candles"] == 72


def test_buy_hold_benchmark_matches_same_period_and_costs():
    candles = trending_candles()
    segment = evaluate_segment(candles)
    expected = (candles[-1]["close"] / candles[20]["open"]) * (1.0 - COST_PER_SIDE) ** 2 - 1.0
    value = segment["buy_hold_net_return"] or segment["raw_metrics"]["buy_hold_net_return"]
    assert math.isclose(value, expected, rel_tol=0, abs_tol=1e-12)


def test_load_candles_filters_invalid_rows(tmp_path):
    data_dir = tmp_path / "data" / "BTCUSDT_4h"
    data_dir.mkdir(parents=True)
    path = data_dir / "part.csv"
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=["open_time_ms", "open", "close"]
        )
        writer.writeheader()
        writer.writerow({"open_time_ms": 0, "open": "100", "close": "101"})
        writer.writerow({"open_time_ms": BAR_MS, "open": "nan", "close": "101"})
        writer.writerow({"open_time_ms": 2 * BAR_MS, "open": "-5", "close": "101"})
        writer.writerow({"open_time_ms": 3 * BAR_MS, "open": "100"})
        writer.writerow({"open_time_ms": "not-a-number", "open": "100", "close": "101"})
        writer.writerow({"open_time_ms": 4 * BAR_MS, "open": "100", "close": "102"})
    rows = load_candles(tmp_path)
    assert [row["open_time_ms"] for row in rows] == [0, 4 * BAR_MS]
    assert all(row["open"] > 0 and row["close"] > 0 for row in rows)


def test_report_labels_are_exploratory_and_include_policies(tmp_path):
    result = run_experiment(trending_candles())
    backtest.write_report(tmp_path, result)
    markdown = (tmp_path / "experiments" / "latest_backtest.md").read_text(encoding="utf-8")
    assert "EXPLORATÓRIO — NÃO É PROVA" in markdown
    assert "sobreajuste" in markdown
    assert result["validation_policy"] in markdown
    assert result["execution_policy"] in markdown
