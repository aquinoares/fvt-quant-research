# Backtest didático da Trilha A

**EXPLORATÓRIO — NÃO É PROVA.**

- Gerado em UTC: 2026-10-29T21:46:24Z
- Método: Baseline long-only SMA-20 não otimizado; sinal usa candles anteriores e custos por lado.
- Custo ida e volta: 30 bps.
- Treino (primeiros 70%): {"buy_hold_net_return": -0.16045079339830748, "candles": 474, "completed_trades": 21, "exposure_bars": 240, "max_drawdown": -0.1663022341837631, "net_return": 0.20897712472736707, "status": "ok"}
- Validação (últimos 30%): {"buy_hold_net_return": 0.1497814329947369, "candles": 204, "completed_trades": 11, "exposure_bars": 117, "max_drawdown": -0.101052004592874, "net_return": 0.0007306410720122614, "status": "ok"}

## Avisos obrigatórios

- EXPLORATÓRIO — NÃO É PROVA
- Baseline pedagógico SMA-20 fixo; seleção repetida de regras/parâmetros aumenta risco de sobreajuste.
- Retorno por candle considera open→close quando a posição está aberta; gaps entre candles são simplificados.

Não valida a Trilha B, não altera parâmetros congelados e não prova rentabilidade.
