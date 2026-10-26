# Backtest didático da Trilha A

**EXPLORATÓRIO — NÃO É PROVA.**

- Gerado em UTC: 2026-10-26T20:38:30Z
- Método: Baseline long-only SMA-20 não otimizado; sinal usa candles anteriores e custos por lado.
- Custo ida e volta: 30 bps.
- Treino (primeiros 70%): {"buy_hold_net_return": 0.18451037861797182, "candles": 87, "completed_trades": 3, "exposure_bars": 59, "max_drawdown": -0.06272293928849693, "net_return": 0.14638730307996384, "status": "ok"}
- Validação (últimos 30%): {"buy_hold_net_return": -0.045073624694228265, "candles": 38, "completed_trades": 1, "exposure_bars": 4, "max_drawdown": -0.05337427875940681, "net_return": -0.02819098491995564, "status": "ok"}

## Avisos obrigatórios

- EXPLORATÓRIO — NÃO É PROVA
- Baseline pedagógico SMA-20 fixo; seleção repetida de regras/parâmetros aumenta risco de sobreajuste.
- Retorno por candle considera open→close quando a posição está aberta; gaps entre candles são simplificados.
- Amostra de treino pequena: menos de 10 operações completas; resultado inconclusivo.
- Amostra de validação pequena: menos de 10 operações completas; resultado inconclusivo.

Não valida a Trilha B, não altera parâmetros congelados e não prova rentabilidade.
