"""Deflated Sharpe Ratio — implementacao propria, somente stdlib.

Bailey e Lopez de Prado (2014), JPM 40(5), eq. 2-4:

    E[Z_max] = sqrt(2*ln(M)) - (ln(ln(M)) + ln(4*pi)) / (2*sqrt(2*ln(M)))  # eq. 2 (Gumbel)
    SR_max   = E[Z_max] * sqrt(1/(T-1))          # Sharpe esperado do vencedor ao acaso
    SE(SR)   = sqrt((1 - skew*SR + ((kurt-1)/4)*SR^2) / (T-1))             # eq. 3
    DSR      = (SR_obs - SR_max) / SE(SR)                                    # eq. 4
    p        = 1 - Phi(DSR)                          # teste unilateral

UNIDADE: SR em base POR OBSERVACAO (diario, nao anualizado) — a mesma escala de
SR_max (ancora numerica: M=100, T=1000 -> SR_max = 0,0749, um Sharpe diario).
Passar SR anualizado mistura escalas e invalida o p-valor.

Diferencas declaradas vs mnemox-ai/deflated-sharpe (referencia Apache-2.0):
- entradas invalidas lancam ValueError (a referencia devolve (0.0, 1.0));
- variancia de SR nao positiva lanca ValueError (a referencia usa chao 1e-12);
- sem arredondamento (a referencia arredonda em 6 casas);
- apenas o nucleo do DSR (sem min_backtest_length nem Benjamini-Hochberg).

Uso (P1c, ainda nao ligado em run_research): deflated_sharpe_ratio(
    observed_sr=daily_mean/daily_std, num_trials=N_HONESTO, num_obs=daily_observations).
"""

from __future__ import annotations

import math


def norm_cdf(x: float) -> float:
    """Phi(x) via math.erf (sem scipy)."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def expected_max_sharpe_z(num_trials: int) -> float:
    """E[Z_max] de Gumbel (eq. 2). M=1 -> 0.0 (nenhuma correcao por multiplicidade)."""
    if num_trials < 1:
        raise ValueError(f"num_trials deve ser >= 1: {num_trials}")
    if num_trials == 1:
        return 0.0
    ln_m = math.log(num_trials)
    z = math.sqrt(2.0 * ln_m)
    return z - (math.log(ln_m) + math.log(4.0 * math.pi)) / (2.0 * z)


def max_sharpe_bound(num_trials: int, num_obs: int) -> float:
    """SR_max = E[Z_max] * sqrt(1/(T-1))."""
    if num_obs < 2:
        raise ValueError(f"num_obs deve ser >= 2: {num_obs}")
    return expected_max_sharpe_z(num_trials) * math.sqrt(1.0 / (num_obs - 1))


def sharpe_standard_error(
    sr: float, num_obs: int, skewness: float = 0.0, kurtosis: float = 3.0
) -> float:
    """SE(SR) com correcao de nao normalidade (eq. 3). kurtosis nao excedente (3 = normal)."""
    if num_obs < 2:
        raise ValueError(f"num_obs deve ser >= 2: {num_obs}")
    var = (1.0 - skewness * sr + ((kurtosis - 1.0) / 4.0) * sr * sr) / (num_obs - 1)
    if var <= 0.0:
        raise ValueError(
            f"variancia do SR nao positiva: {var} (skew={skewness}, kurt={kurtosis})"
        )
    return math.sqrt(var)


def deflated_sharpe_ratio(
    observed_sr: float,
    num_trials: int,
    num_obs: int,
    skewness: float = 0.0,
    kurtosis: float = 3.0,
) -> tuple[float, float]:
    """(DSR, p_value); p unilateral: H1 = SR observado supera o maximo ao acaso."""
    sr_max = max_sharpe_bound(num_trials, num_obs)
    se = sharpe_standard_error(observed_sr, num_obs, skewness, kurtosis)
    dsr = (observed_sr - sr_max) / se
    return dsr, 1.0 - norm_cdf(dsr)
