"""Regra inicial, explícita e conservadora de convergência."""


def convergence_signal(
    parent_direction: int,
    child_direction: int,
    retracement_confirmed: bool,
    volume_confirmed: bool,
    momentum_confirmed: bool,
) -> int:
    """Retorna 1 (compra), -1 (venda) ou 0 (sem sinal).

    As confirmações são fornecidas por módulos independentes e devem usar apenas
    dados conhecidos até o fechamento do candle de sinal.
    """
    valid = (-1, 0, 1)
    if parent_direction not in valid or child_direction not in valid:
        raise ValueError("Direcoes devem ser -1, 0 ou 1.")
    if parent_direction == 0 or child_direction != parent_direction:
        return 0
    if retracement_confirmed and volume_confirmed and momentum_confirmed:
        return int(parent_direction)
    return 0