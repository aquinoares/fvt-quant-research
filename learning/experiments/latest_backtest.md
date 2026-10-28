# Backtest didático da Trilha A

**EXPLORATÓRIO — NÃO É PROVA.**

- Gerado em UTC: 2026-10-28T23:09:03Z
- Método: Baseline long-only SMA-20 não otimizado; sinal usa candles anteriores e custos por lado.
- Custo ida e volta: 30 bps.
- Treino (primeiros 70%): {"buy_hold_net_return": 0.23334938328962562, "candles": 392, "completed_trades": 18, "exposure_bars": 215, "max_drawdown": -0.11429163048288316, "net_return": 0.14950629266793958, "status": "ok"}
- Validação (últimos 30%): {"buy_hold_net_return": -0.16807093001774365, "candles": 169, "completed_trades": 7, "exposure_bars": 82, "max_drawdown": -0.10105200459287411, "net_return": 0.06580035592484945, "status": "ok"}

## Avisos obrigatórios

- EXPLORATÓRIO — NÃO É PROVA
- Baseline pedagógico SMA-20 fixo; seleção repetida de regras/parâmetros aumenta risco de sobreajuste.
- Retorno por candle considera open→close quando a posição está aberta; gaps entre candles são simplificados.
- Amostra de validação pequena: menos de 10 operações completas; resultado inconclusivo.

Não valida a Trilha B, não altera parâmetros congelados e não prova rentabilidade.
