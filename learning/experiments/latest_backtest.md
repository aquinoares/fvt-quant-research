# Backtest didático da Trilha A

**EXPLORATÓRIO — NÃO É PROVA.**

- Gerado em UTC: 2026-10-28T18:49:08Z
- Método: Baseline long-only SMA-20 não otimizado; sinal usa candles anteriores e custos por lado.
- Custo ida e volta: 30 bps.
- Treino (primeiros 70%): {"buy_hold_net_return": 0.1876324386193462, "candles": 372, "completed_trades": 17, "exposure_bars": 196, "max_drawdown": -0.11032351322450973, "net_return": 0.10250509579754219, "status": "ok"}
- Validação (últimos 30%): {"buy_hold_net_return": -0.3028814762403501, "candles": 160, "completed_trades": 6, "exposure_bars": 59, "max_drawdown": -0.10360654673794445, "net_return": 0.05277451466701266, "status": "ok"}

## Avisos obrigatórios

- EXPLORATÓRIO — NÃO É PROVA
- Baseline pedagógico SMA-20 fixo; seleção repetida de regras/parâmetros aumenta risco de sobreajuste.
- Retorno por candle considera open→close quando a posição está aberta; gaps entre candles são simplificados.
- Amostra de validação pequena: menos de 10 operações completas; resultado inconclusivo.

Não valida a Trilha B, não altera parâmetros congelados e não prova rentabilidade.
