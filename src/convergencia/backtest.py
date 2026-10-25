"""Backtest spot long-only, with BUY/SELL events, delayed execution and costs."""

import numpy as np
import pandas as pd


def run_backtest(candles: pd.DataFrame, signals, fee_bps: float = 10.0, slippage_bps: float = 5.0) -> pd.DataFrame:
    """Simula spot sem alavancagem: 1=BUY, -1=SELL/EXIT, 0=manter estado.

    Cada sinal e conhecido no fechamento do candle e so pode afetar a posicao
    na abertura seguinte. A posicao e apenas 0 (fora) ou 1 (comprado), nunca
    vendida a descoberto. A posicao aberta e liquidada no ultimo preco de
    abertura disponivel; custos da transacao no fim de cada intervalo sao
    debitados no intervalo que termina nessa abertura.

    Modelo inicial: retornos abertura-a-abertura; stop, alvos e sizing ainda
    nao fazem parte desta etapa.
    """
    if not isinstance(candles, pd.DataFrame) or "open" not in candles.columns:
        raise ValueError("candles deve conter a coluna open.")
    opens = pd.to_numeric(candles["open"], errors="coerce")
    if len(opens) < 2 or not np.isfinite(opens.to_numpy()).all() or (opens <= 0).any():
        raise ValueError("Sao necessarias ao menos duas aberturas positivas e finitas.")
    if not np.isfinite([fee_bps, slippage_bps]).all() or fee_bps < 0 or slippage_bps < 0:
        raise ValueError("Custos devem ser finitos e nao negativos.")
    events = np.asarray(signals, dtype="float64")
    if events.ndim != 1 or len(events) != len(candles) or not np.isfinite(events).all():
        raise ValueError("Deve existir um sinal finito por candle.")
    if not np.isin(events, [-1, 0, 1]).all():
        raise ValueError("Sinais permitidos: -1 (SELL/EXIT), 0 (HOLD), 1 (BUY).")

    # Converter eventos em estado-alvo: BUY abre, SELL fecha e HOLD conserva.
    estado = 0
    estados = []
    for evento in events:
        if evento == 1:
            estado = 1
        elif evento == -1:
            estado = 0
        estados.append(estado)
    target = pd.Series(estados, index=candles.index, name="target_position", dtype="float64")

    # Um evento no fechamento t so vale a partir da abertura t+1.
    position = target.shift(1, fill_value=0.0).rename("position")
    # Liquidacao obrigatoria no ultimo preco observado para nao deixar risco aberto.
    if len(position) >= 2:
        position.iloc[-1] = 0.0

    next_open_return = (opens.shift(-1) / opens - 1.0).rename("next_open_return")
    turnover = position.diff().abs()
    if len(turnover):
        turnover.iloc[0] = abs(float(position.iloc[0]))
    # Transacao no proximo open afeta o intervalo que termina nesse open.
    cost_rate = (fee_bps + slippage_bps) / 10_000.0
    costs = (turnover.shift(-1).fillna(0.0) * cost_rate).rename("costs")
    gross = (position * next_open_return).rename("gross_return")
    net = (gross - costs).rename("net_return")
    result = pd.concat([pd.Series(events, index=candles.index, name="signal"), position,
                        next_open_return, gross, costs, net], axis=1)
    result = result.loc[next_open_return.notna()].copy()
    result["equity"] = (1.0 + result["net_return"]).cumprod()
    return result