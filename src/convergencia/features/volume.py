"""Medidas descritivas de atividade de volume, sem inferir direcao futura."""

import numpy as np


def trapezoidal_activity(volume, interval: float = 1.0) -> float:
    """Integra amostras de volume pela regra trapezoidal; exige 2+ pontos."""
    values = np.asarray(volume, dtype="float64")
    if values.ndim != 1 or len(values) < 2:
        raise ValueError("Volume deve conter pelo menos duas amostras.")
    if not np.isfinite(values).all() or (values < 0).any():
        raise ValueError("Volume deve ser finito e nao negativo.")
    if not np.isfinite(interval) or interval <= 0:
        raise ValueError("interval deve ser positivo e finito.")
    return float(np.sum((values[:-1] + values[1:]) * 0.5 * interval))


def relative_volume(volume, lookback: int = 20) -> float:
    """Volume mais recente dividido pela media das `lookback` amostras anteriores."""
    values = np.asarray(volume, dtype="float64")
    if lookback < 1 or values.ndim != 1 or len(values) < lookback + 1:
        raise ValueError("Amostras insuficientes para o lookback informado.")
    if not np.isfinite(values).all() or (values < 0).any():
        raise ValueError("Volume deve ser finito e nao negativo.")
    baseline = float(np.mean(values[-lookback - 1:-1]))
    if baseline <= 0:
        raise ValueError("Media historica de volume deve ser positiva.")
    return float(values[-1] / baseline)