# Backtest didático da Trilha A

**EXPLORATÓRIO — NÃO É PROVA.**

- Gerado em UTC: 2026-10-30T01:55:26Z
- Método: Baseline long-only SMA-20 não otimizado; sinal usa candles anteriores e custos por lado.
- Custo ida e volta: 30 bps.
- Treino (primeiros 70%): {"buy_hold_net_return": -0.1224976154937234, "candles": 493, "completed_trades": 22, "exposure_bars": 252, "max_drawdown": -0.1663022341837631, "net_return": 0.24551202496840885, "status": "ok"}
- Validação (últimos 30%): {"buy_hold_net_return": 0.14834029607076826, "candles": 212, "completed_trades": 11, "exposure_bars": 125, "max_drawdown": -0.08993034212327788, "net_return": -0.007446923842984843, "status": "ok"}

## Avisos obrigatórios

- EXPLORATÓRIO — NÃO É PROVA
- Baseline pedagógico SMA-20 fixo; seleção repetida de regras/parâmetros aumenta risco de sobreajuste.
- Retorno por candle considera open→close quando a posição está aberta; gaps entre candles são simplificados.

Não valida a Trilha B, não altera parâmetros congelados e não prova rentabilidade.
