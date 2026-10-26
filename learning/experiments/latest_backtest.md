# Backtest didático da Trilha A

**EXPLORATÓRIO — NÃO É PROVA.**

- Gerado em UTC: 2026-10-26T19:45:00Z
- Método: Baseline long-only SMA-20 não otimizado; sinal usa candles anteriores e custos por lado.
- Custo ida e volta: 30 bps.
- Treino (primeiros 70%): {"buy_hold_net_return": 0.09449844446274125, "candles": 58, "completed_trades": 1, "exposure_bars": 31, "max_drawdown": -0.05574980778385308, "net_return": 0.06928918941279005, "status": "ok"}
- Validação (últimos 30%): {"buy_hold_net_return": 0.07779415499350195, "candles": 25, "completed_trades": 1, "exposure_bars": 5, "max_drawdown": 0.0, "net_return": 0.07809898030956863, "status": "ok"}

## Avisos obrigatórios

- EXPLORATÓRIO — NÃO É PROVA
- Baseline pedagógico SMA-20 fixo; seleção repetida de regras/parâmetros aumenta risco de sobreajuste.
- Retorno por candle considera open→close quando a posição está aberta; gaps entre candles são simplificados.
- Amostra de treino pequena: menos de 10 operações completas; resultado inconclusivo.
- Amostra de validação pequena: menos de 10 operações completas; resultado inconclusivo.

Não valida a Trilha B, não altera parâmetros congelados e não prova rentabilidade.
