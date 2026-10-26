# Backtest didático da Trilha A

**EXPLORATÓRIO — NÃO É PROVA.**

- Gerado em UTC: 2026-10-26T21:37:44Z
- Método: Baseline long-only SMA-20 não otimizado; sinal usa candles anteriores e custos por lado.
- Custo ida e volta: 30 bps.
- Treino (primeiros 70%): {"buy_hold_net_return": 0.1757099956675523, "candles": 116, "completed_trades": 3, "exposure_bars": 83, "max_drawdown": -0.06272293928849693, "net_return": 0.1401498822106655, "status": "ok"}
- Validação (últimos 30%): {"buy_hold_net_return": 0.07654117110881953, "candles": 50, "completed_trades": 1, "exposure_bars": 13, "max_drawdown": -0.009436916904449033, "net_return": 0.06163442747655079, "status": "ok"}

## Avisos obrigatórios

- EXPLORATÓRIO — NÃO É PROVA
- Baseline pedagógico SMA-20 fixo; seleção repetida de regras/parâmetros aumenta risco de sobreajuste.
- Retorno por candle considera open→close quando a posição está aberta; gaps entre candles são simplificados.
- Amostra de treino pequena: menos de 10 operações completas; resultado inconclusivo.
- Amostra de validação pequena: menos de 10 operações completas; resultado inconclusivo.

Não valida a Trilha B, não altera parâmetros congelados e não prova rentabilidade.
