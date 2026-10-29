# Backtest didático da Trilha A

**EXPLORATÓRIO — NÃO É PROVA.**

- Gerado em UTC: 2026-10-29T16:53:11Z
- Método: Baseline long-only SMA-20 não otimizado; sinal usa candles anteriores e custos por lado.
- Custo ida e volta: 30 bps.
- Treino (primeiros 70%): {"buy_hold_net_return": -0.2852762066996777, "candles": 454, "completed_trades": 20, "exposure_bars": 222, "max_drawdown": -0.13755847415758482, "net_return": 0.06875498139203517, "status": "ok"}
- Validação (últimos 30%): {"buy_hold_net_return": 0.1685399714044562, "candles": 195, "completed_trades": 10, "exposure_bars": 115, "max_drawdown": -0.10105200459287411, "net_return": 0.034468489276902936, "status": "ok"}

## Avisos obrigatórios

- EXPLORATÓRIO — NÃO É PROVA
- Baseline pedagógico SMA-20 fixo; seleção repetida de regras/parâmetros aumenta risco de sobreajuste.
- Retorno por candle considera open→close quando a posição está aberta; gaps entre candles são simplificados.

Não valida a Trilha B, não altera parâmetros congelados e não prova rentabilidade.
