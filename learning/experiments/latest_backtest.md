# Backtest didático da Trilha A

**EXPLORATÓRIO — NÃO É PROVA.**

- Gerado em UTC: 2026-10-26T23:33:19Z
- Método: Baseline long-only SMA-20 não otimizado; sinal usa candles anteriores e custos por lado.
- Custo ida e volta: 30 bps.
- Treino (primeiros 70%): {"buy_hold_net_return": 0.26205713883464177, "candles": 174, "completed_trades": 7, "exposure_bars": 108, "max_drawdown": -0.08398714422495102, "net_return": 0.2116398683058449, "status": "ok"}
- Validação (últimos 30%): {"buy_hold_net_return": 0.08153091673870105, "candles": 75, "completed_trades": 3, "exposure_bars": 33, "max_drawdown": -0.033881940243074116, "net_return": 0.004284388055467714, "status": "ok"}

## Avisos obrigatórios

- EXPLORATÓRIO — NÃO É PROVA
- Baseline pedagógico SMA-20 fixo; seleção repetida de regras/parâmetros aumenta risco de sobreajuste.
- Retorno por candle considera open→close quando a posição está aberta; gaps entre candles são simplificados.
- Amostra de treino pequena: menos de 10 operações completas; resultado inconclusivo.
- Amostra de validação pequena: menos de 10 operações completas; resultado inconclusivo.

Não valida a Trilha B, não altera parâmetros congelados e não prova rentabilidade.
