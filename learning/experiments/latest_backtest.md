# Backtest didático da Trilha A

**EXPLORATÓRIO — NÃO É PROVA.**

- Gerado em UTC: 2026-10-31T06:56:25Z
- Método: Baseline long-only SMA-20 não otimizado; sinal usa candles anteriores e custos por lado.
- Custo ida e volta: 30 bps.
- Treino (primeiros 70%): {"buy_hold_net_return": -0.007068232400748942, "candles": 581, "completed_trades": 26, "exposure_bars": 320, "max_drawdown": -0.1663022341837631, "net_return": 0.2853187049761732, "status": "ok"}
- Validação (últimos 30%): {"buy_hold_net_return": 0.41753308129486855, "candles": 249, "completed_trades": 13, "exposure_bars": 155, "max_drawdown": -0.09565824626199071, "net_return": 0.22256617365090547, "status": "ok"}

## Avisos obrigatórios

- EXPLORATÓRIO — NÃO É PROVA
- Baseline pedagógico SMA-20 fixo; seleção repetida de regras/parâmetros aumenta risco de sobreajuste.
- Retorno por candle considera open→close quando a posição está aberta; gaps entre candles são simplificados.

Não valida a Trilha B, não altera parâmetros congelados e não prova rentabilidade.
