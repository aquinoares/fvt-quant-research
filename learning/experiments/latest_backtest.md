# Backtest didático da Trilha A

**EXPLORATÓRIO — NÃO É PROVA.**

- Gerado em UTC: 2026-10-27T20:02:11Z
- Método: Baseline long-only SMA-20 não otimizado; sinal usa candles anteriores e custos por lado.
- Custo ida e volta: 30 bps.
- Treino (primeiros 70%): {"buy_hold_net_return": 0.31643064274384747, "candles": 290, "completed_trades": 14, "exposure_bars": 176, "max_drawdown": -0.08398714422495102, "net_return": 0.18400615000303167, "status": "ok"}
- Validação (últimos 30%): {"buy_hold_net_return": -0.17928251342924995, "candles": 125, "completed_trades": 3, "exposure_bars": 39, "max_drawdown": -0.030809254229206662, "net_return": 0.004380119901624013, "status": "ok"}

## Avisos obrigatórios

- EXPLORATÓRIO — NÃO É PROVA
- Baseline pedagógico SMA-20 fixo; seleção repetida de regras/parâmetros aumenta risco de sobreajuste.
- Retorno por candle considera open→close quando a posição está aberta; gaps entre candles são simplificados.
- Amostra de validação pequena: menos de 10 operações completas; resultado inconclusivo.

Não valida a Trilha B, não altera parâmetros congelados e não prova rentabilidade.
