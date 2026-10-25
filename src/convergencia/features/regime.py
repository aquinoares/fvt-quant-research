"""Proxy estatistico de equilibrio; nao e um atrator estranho de Lorenz."""

import numpy as np
import pandas as pd


def rolling_equilibrium(prices, window: int = 20) -> dict[str, float]:
    """Calcula media, bandas de dois desvios-padrao e z-score no ultimo ponto."""
    if window < 2:
        raise ValueError("window deve ser >= 2.")
    serie = pd.Series(prices, dtype="float64")
    if len(serie) < window or not np.isfinite(serie.to_numpy()).all():
        raise ValueError("Precos insuficientes ou nao finitos.")
    media = serie.rolling(window=window, min_periods=window).mean().iloc[-1]
    desvio = serie.rolling(window=window, min_periods=window).std(ddof=1).iloc[-1]
    ultimo = float(serie.iloc[-1])
    z_score = 0.0 if desvio == 0 else (ultimo - media) / desvio
    return {
        "center": float(media),
        "upper": float(media + 2.0 * desvio),
        "lower": float(media - 2.0 * desvio),
        "z_score": float(z_score),
    }