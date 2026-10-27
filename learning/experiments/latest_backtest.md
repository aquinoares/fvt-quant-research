# Backtest didático da Trilha A

**EXPLORATÓRIO — NÃO É PROVA.**

- Gerado em UTC: 2026-10-27T00:47:16Z
- Método: Baseline long-only SMA-20 não otimizado; sinal usa candles anteriores e custos por lado.
- Custo ida e volta: 30 bps.
- Treino (primeiros 70%): {"buy_hold_net_return": 0.27109768024670533, "candles": 200, "completed_trades": 11, "exposure_bars": 127, "max_drawdown": -0.08398714422495102, "net_return": 0.1674735343839675, "status": "ok"}
- Validação (últimos 30%): {"buy_hold_net_return": -0.015295666659769669, "candles": 86, "completed_trades": 3, "exposure_bars": 42, "max_drawdown": -0.043565870411348406, "net_return": -0.024005708031330508, "status": "ok"}

## Avisos obrigatórios

- EXPLORATÓRIO — NÃO É PROVA
- Baseline pedagógico SMA-20 fixo; seleção repetida de regras/parâmetros aumenta risco de sobreajuste.
- Retorno por candle considera open→close quando a posição está aberta; gaps entre candles são simplificados.
- Amostra de validação pequena: menos de 10 operações completas; resultado inconclusivo.

Não valida a Trilha B, não altera parâmetros congelados e não prova rentabilidade.
