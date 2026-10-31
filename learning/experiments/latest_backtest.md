# Backtest didático da Trilha A

**EXPLORATÓRIO — NÃO É PROVA.**

- Gerado em UTC: 2026-10-31T00:43:07Z
- Método: Baseline long-only SMA-20 não otimizado; sinal usa candles anteriores e custos por lado.
- Custo ida e volta: 30 bps.
- Treino (primeiros 70%): {"buy_hold_net_return": -0.0868537579378309, "candles": 563, "completed_trades": 25, "exposure_bars": 303, "max_drawdown": -0.1663022341837631, "net_return": 0.19770516429890295, "status": "ok"}
- Validação (últimos 30%): {"buy_hold_net_return": 0.3401278221952755, "candles": 242, "completed_trades": 12, "exposure_bars": 147, "max_drawdown": -0.09565824626199015, "net_return": 0.27570825272532096, "status": "ok"}

## Avisos obrigatórios

- EXPLORATÓRIO — NÃO É PROVA
- Baseline pedagógico SMA-20 fixo; seleção repetida de regras/parâmetros aumenta risco de sobreajuste.
- Retorno por candle considera open→close quando a posição está aberta; gaps entre candles são simplificados.

Não valida a Trilha B, não altera parâmetros congelados e não prova rentabilidade.
