"""Alinhamento de direcao entre escalas; nao prova auto-similaridade fractal."""


def direction_alignment(parent_direction: int, child_direction: int) -> int:
    """Retorna 1 ou -1 se as direcoes nao nulas coincidirem; caso contrario 0."""
    valid = (-1, 0, 1)
    if parent_direction not in valid or child_direction not in valid:
        raise ValueError("Direcoes devem ser -1, 0 ou 1.")
    if parent_direction != 0 and parent_direction == child_direction:
        return int(parent_direction)
    return 0