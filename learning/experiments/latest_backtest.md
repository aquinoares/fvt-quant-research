# Backtest didático da Trilha A

**EXPLORATÓRIO — NÃO É PROVA.**

- Gerado em UTC: 2026-10-26T22:38:15Z
- Método: Baseline long-only SMA-20 não otimizado; sinal usa candles anteriores e custos por lado.
- Custo ida e volta: 30 bps.
- Treino (primeiros 70%): {"buy_hold_net_return": 0.12584387260344276, "candles": 145, "completed_trades": 6, "exposure_bars": 87, "max_drawdown": -0.08049859821003347, "net_return": 0.10748038154872841, "status": "ok"}
- Validação (últimos 30%): {"buy_hold_net_return": 0.010739748160238483, "candles": 63, "completed_trades": 5, "exposure_bars": 28, "max_drawdown": -0.0593097974797645, "net_return": -0.01619458017260078, "status": "ok"}

## Avisos obrigatórios

- EXPLORATÓRIO — NÃO É PROVA
- Baseline pedagógico SMA-20 fixo; seleção repetida de regras/parâmetros aumenta risco de sobreajuste.
- Retorno por candle considera open→close quando a posição está aberta; gaps entre candles são simplificados.
- Amostra de treino pequena: menos de 10 operações completas; resultado inconclusivo.
- Amostra de validação pequena: menos de 10 operações completas; resultado inconclusivo.

Não valida a Trilha B, não altera parâmetros congelados e não prova rentabilidade.
