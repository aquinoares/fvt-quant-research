# Backtest didático da Trilha A

**EXPLORATÓRIO — NÃO É PROVA.**

- Gerado em UTC: 2026-10-31T13:35:44Z
- Método: Baseline long-only SMA-20 não otimizado; sinal usa candles anteriores e custos por lado.
- Custo ida e volta: 30 bps.
- Treino (primeiros 70%): {"buy_hold_net_return": -0.06402784946189732, "candles": 598, "completed_trades": 26, "exposure_bars": 331, "max_drawdown": -0.1663022341837631, "net_return": 0.26195153844944397, "status": "ok"}
- Validação (últimos 30%): {"buy_hold_net_return": 0.3541390102137696, "candles": 257, "completed_trades": 13, "exposure_bars": 160, "max_drawdown": -0.09565824626199093, "net_return": 0.19990786938081428, "status": "ok"}

## Avisos obrigatórios

- EXPLORATÓRIO — NÃO É PROVA
- Baseline pedagógico SMA-20 fixo; seleção repetida de regras/parâmetros aumenta risco de sobreajuste.
- Retorno por candle considera open→close quando a posição está aberta; gaps entre candles são simplificados.

Não valida a Trilha B, não altera parâmetros congelados e não prova rentabilidade.
