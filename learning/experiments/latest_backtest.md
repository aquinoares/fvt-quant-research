# Backtest didático da Trilha A

**EXPLORATÓRIO — NÃO É PROVA.**

- Gerado em UTC: 2026-10-30T20:43:22Z
- Método: Baseline long-only SMA-20 não otimizado; sinal usa candles anteriores e custos por lado.
- Custo ida e volta: 30 bps.
- Treino (primeiros 70%): {"buy_hold_net_return": -0.1586570674870441, "candles": 546, "completed_trades": 24, "exposure_bars": 287, "max_drawdown": -0.1663022341837631, "net_return": 0.1856644788208217, "status": "ok"}
- Validação (últimos 30%): {"buy_hold_net_return": 0.2755771198919583, "candles": 234, "completed_trades": 12, "exposure_bars": 150, "max_drawdown": -0.09565824626199015, "net_return": 0.23169974992457965, "status": "ok"}

## Avisos obrigatórios

- EXPLORATÓRIO — NÃO É PROVA
- Baseline pedagógico SMA-20 fixo; seleção repetida de regras/parâmetros aumenta risco de sobreajuste.
- Retorno por candle considera open→close quando a posição está aberta; gaps entre candles são simplificados.

Não valida a Trilha B, não altera parâmetros congelados e não prova rentabilidade.
