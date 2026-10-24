"""Inclinação e mudança de inclinação normalizadas, sem ângulos dependentes de escala."""

import numpy as np


def normalized_slope(prices) -> float:
    """Inclinação linear dos log-precos dividida pelo desvio dos retornos log."""
    values = np.asarray(prices, dtype="float64")
    if values.ndim != 1 or len(values) < 3:
        raise ValueError("Sao necessarios ao menos tres precos.")
    if not np.isfinite(values).all() or (values <= 0).any():
        raise ValueError("Precos devem ser positivos e finitos.")
    logs = np.log(values)
    slope = float(np.polyfit(np.arange(len(logs)), logs, 1)[0])
    returns = np.diff(logs)
    volatility = float(np.std(returns, ddof=1))
    return 0.0 if volatility <= 1e-12 and abs(slope) <= 1e-12 else float(slope / max(volatility, 1e-12))


def normalized_acceleration(prices, window: int = 10) -> float:
    """Diferenca entre inclinações normalizadas em duas janelas consecutivas."""
    values = np.asarray(prices, dtype="float64")
    if window < 3 or values.ndim != 1 or len(values) < 2 * window:
        raise ValueError("Exige window >= 3 e ao menos 2*window precos.")
    anterior = normalized_slope(values[-2 * window:-window])
    recente = normalized_slope(values[-window:])
    return float(recente - anterior)