import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from convergencia.backtest import run_backtest


def _load_lab_v2():
    # O modulo consulta argv[1] ao ser carregado; apontamos para a raiz.
    old_argv = sys.argv[:]
    try:
        sys.argv = ["labv2", str(ROOT)]
        spec = importlib.util.spec_from_file_location(
            "adaptive_timeframe_lab_v2_test",
            ROOT / "scripts" / "run_adaptive_timeframe_lab_v2.py",
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.argv = old_argv


def _candles(n=8):
    opens = np.array([100.0 + i for i in range(n)])
    closes = opens + 0.5
    return pd.DataFrame({"open": opens, "close": closes})


def test_engine_drops_last_row_without_next_open_return():
    frame = _candles(8)
    events = np.array([1, 0, 0, 0, 0, 0, 0, 0], dtype=float)

    result = run_backtest(frame, events, fee_bps=10.0, slippage_bps=5.0)

    # Contrato atual do motor: a última linha não tem próxima abertura.
    assert len(result) == len(frame) - 1
    assert "position" in result.columns
    assert "costs" in result.columns
    assert "equity" in result.columns


def test_lab_v2_open_position_end_convention_is_explicit():
    frame = _candles(8)
    events = np.array([1, 0, 0, 0, 0, 0, 0, 0], dtype=float)
    lab = _load_lab_v2()

    result = lab.run_metrics(frame, events, wrong_semantics=False)

    # A v2 calcula seu próprio caminho e liquida no fim.
    # Não exigimos igualdade de retorno com o motor: as convenções de
    # última barra e de temporização dos custos diferem atualmente.
    assert result["forced_end_liquidations"] == 1
    assert result["executed_entries"] >= 1
    assert result["executed_exits"] <= result["executed_entries"]
    assert np.isfinite(float(result["net_return_pct"]))
    assert np.isfinite(float(result["max_drawdown_pct"]))


def test_engine_costs_are_finite_and_nonnegative():
    frame = _candles(8)
    events = np.array([1, 0, 0, 0, 0, 0, 0, 0], dtype=float)

    result = run_backtest(frame, events, fee_bps=10.0, slippage_bps=5.0)

    assert np.isfinite(result["costs"].to_numpy(dtype=float)).all()
    assert (result["costs"].to_numpy(dtype=float) >= 0).all()