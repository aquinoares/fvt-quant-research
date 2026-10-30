# Backtest didático da Trilha A

**EXPLORATÓRIO — NÃO É PROVA.**

- Gerado em UTC: 2026-10-30T15:51:57Z
- Método: Baseline long-only SMA-20 não otimizado; sinal usa candles anteriores e custos por lado.
- Custo ida e volta: 30 bps.
- Treino (primeiros 70%): {"buy_hold_net_return": -0.198754032789356, "candles": 528, "completed_trades": 23, "exposure_bars": 274, "max_drawdown": -0.1663022341837631, "net_return": 0.21380962718004648, "status": "ok"}
- Validação (últimos 30%): {"buy_hold_net_return": 0.3798732694378637, "candles": 227, "completed_trades": 12, "exposure_bars": 150, "max_drawdown": -0.09565824626199027, "net_return": 0.21507499019110843, "status": "ok"}

## Avisos obrigatórios

- EXPLORATÓRIO — NÃO É PROVA
- Baseline pedagógico SMA-20 fixo; seleção repetida de regras/parâmetros aumenta risco de sobreajuste.
- Retorno por candle considera open→close quando a posição está aberta; gaps entre candles são simplificados.

Não valida a Trilha B, não altera parâmetros congelados e não prova rentabilidade.
