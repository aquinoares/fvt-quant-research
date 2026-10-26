# Backtest didático da Trilha A

**EXPLORATÓRIO — NÃO É PROVA.**

- Gerado em UTC: 2026-10-26T18:50:08Z
- Método: Baseline long-only SMA-20 não otimizado; sinal usa candles anteriores e custos por lado.
- Custo ida e volta: 30 bps.
- Treino (primeiros 70%): {"buy_hold_net_return": 0.013335739046739237, "candles": 28, "completed_trades": 1, "exposure_bars": 8, "max_drawdown": -0.007180302922909498, "net_return": 0.013281854740563759, "status": "ok"}
- Validação (últimos 30%): {"buy_hold_net_return": null, "candles": 13, "completed_trades": 0, "exposure_bars": 0, "max_drawdown": null, "net_return": null, "status": "insufficient_data"}

## Avisos obrigatórios

- EXPLORATÓRIO — NÃO É PROVA
- Baseline pedagógico SMA-20 fixo; seleção repetida de regras/parâmetros aumenta risco de sobreajuste.
- Retorno por candle considera open→close quando a posição está aberta; gaps entre candles são simplificados.
- Amostra de treino pequena: menos de 10 operações completas; resultado inconclusivo.
- Amostra de validação pequena: menos de 10 operações completas; resultado inconclusivo.
- Dados insuficientes para comparar treino e validação com confiança.

Não valida a Trilha B, não altera parâmetros congelados e não prova rentabilidade.
