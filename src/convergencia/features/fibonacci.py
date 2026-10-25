"""Niveis de retracao Fibonacci para uma onda ja identificada."""

LEVELS = (("23.6%", 0.236), ("38.2%", 0.382), ("50.0%", 0.5), ("61.8%", 0.618), ("78.6%", 0.786))


def retracement_levels(low: float, high: float) -> dict[str, float]:
    """Retorna niveis de retracao medidos a partir da maxima da onda de alta.

    `low` e `high` devem ser extremos conhecidos no instante do calculo.
    A funcao nao identifica pivots nem garante reacao do mercado.
    """
    low = float(low)
    high = float(high)
    if not (low > 0 and high > low):
        raise ValueError("Esperado 0 < low < high.")
    amplitude = high - low
    return {nome: high - amplitude * proporcao for nome, proporcao in LEVELS}