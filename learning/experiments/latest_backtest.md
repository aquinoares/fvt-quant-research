# Backtest didático da Trilha A

**EXPLORATÓRIO — NÃO É PROVA.**

- Gerado em UTC: 2026-10-29T02:23:32Z
- Método: Baseline long-only SMA-20 não otimizado; sinal usa candles anteriores e custos por lado.
- Custo ida e volta: 30 bps.
- Treino (primeiros 70%): {"buy_hold_net_return": 0.05388588472300104, "candles": 413, "completed_trades": 18, "exposure_bars": 219, "max_drawdown": -0.11429163048288316, "net_return": 0.12362742281084116, "status": "ok"}
- Validação (últimos 30%): {"buy_hold_net_return": 0.30280348531039003, "candles": 177, "completed_trades": 7, "exposure_bars": 109, "max_drawdown": -0.101052004592874, "net_return": 0.1830659384249802, "status": "ok"}

## Avisos obrigatórios

- EXPLORATÓRIO — NÃO É PROVA
- Baseline pedagógico SMA-20 fixo; seleção repetida de regras/parâmetros aumenta risco de sobreajuste.
- Retorno por candle considera open→close quando a posição está aberta; gaps entre candles são simplificados.
- Amostra de validação pequena: menos de 10 operações completas; resultado inconclusivo.

Não valida a Trilha B, não altera parâmetros congelados e não prova rentabilidade.
