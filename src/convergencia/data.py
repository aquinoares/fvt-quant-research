"""Validacao basica de candles OHLCV antes de qualquer calculo."""

import numpy as np
import pandas as pd

REQUIRED = ("open", "high", "low", "close", "volume")


def validate_ohlcv(frame: pd.DataFrame) -> pd.DataFrame:
    """Valida candles e devolve copia ordenada por timestamp, sem duplicatas."""
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        raise ValueError("Dados devem ser um DataFrame nao vazio.")
    out = frame.copy()
    if "timestamp" in out.columns:
        ts = pd.to_datetime(out["timestamp"], format="ISO8601", errors="coerce", utc=True)
    elif isinstance(out.index, pd.DatetimeIndex):
        ts = pd.to_datetime(out.index, errors="coerce", utc=True)
        out["timestamp"] = ts
    else:
        raise ValueError("Forneca coluna timestamp ou DatetimeIndex.")
    if ts.isna().any() or ts.duplicated().any():
        raise ValueError("Timestamp ausente/invalido ou duplicado.")
    out["timestamp"] = ts
    missing = [col for col in REQUIRED if col not in out.columns]
    if missing:
        raise ValueError(f"Colunas obrigatorias ausentes: {missing}")
    for col in REQUIRED:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    numeric = out.loc[:, REQUIRED].to_numpy(dtype="float64")
    if not np.isfinite(numeric).all():
        raise ValueError("OHLCV contem valores nao numericos ou nao finitos.")
    if (out[["open", "high", "low", "close"]] <= 0).any().any():
        raise ValueError("Precos OHLC devem ser positivos.")
    if (out["volume"] < 0).any():
        raise ValueError("Volume nao pode ser negativo.")
    invalid_range = (out["high"] < out[["open", "close", "low"]].max(axis=1)) | (out["low"] > out[["open", "close", "high"]].min(axis=1))
    if invalid_range.any():
        raise ValueError("Inconsistencia entre maxima, minima, abertura e fechamento.")
    return out.sort_values("timestamp", kind="stable").reset_index(drop=True)