import pandas as pd
import pytest

from convergencia.data import validate_ohlcv


def _frame(timestamps):
    count = len(timestamps)
    return pd.DataFrame({
        "timestamp": timestamps,
        "open": [100.0] * count,
        "high": [101.0] * count,
        "low": [99.0] * count,
        "close": [100.5] * count,
        "volume": [10.0] * count,
    })


def test_validate_ohlcv_accepts_mixed_iso8601_precision():
    frame = _frame([
        "2026-10-21T01:51:00.000000+00:00",
        "2026-10-21T01:52:00+00:00",
        "2026-10-21T01:53:00.000000+00:00",
    ])
    result = validate_ohlcv(frame)
    assert len(result) == 3
    assert result["timestamp"].notna().all()
    assert result["timestamp"].is_unique
    assert result["timestamp"].is_monotonic_increasing


def test_validate_ohlcv_still_rejects_duplicate_instants_with_different_text():
    frame = _frame([
        "2026-10-21T01:51:00.000000+00:00",
        "2026-10-21T01:51:00+00:00",
    ])
    with pytest.raises(ValueError, match="Timestamp ausente/invalido ou duplicado"):
        validate_ohlcv(frame)