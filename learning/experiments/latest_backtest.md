# Backtest didático da Trilha A

**EXPLORATÓRIO — NÃO É PROVA.**

- Gerado em UTC: 2026-10-27T23:44:02Z
- Método: Baseline long-only SMA-20 não otimizado; sinal usa candles anteriores e custos por lado.
- Custo ida e volta: 30 bps.
- Treino (primeiros 70%): {"buy_hold_net_return": 0.3072503481026916, "candles": 311, "completed_trades": 15, "exposure_bars": 180, "max_drawdown": -0.09858703872309171, "net_return": 0.1187272632605445, "status": "ok"}
- Validação (últimos 30%): {"buy_hold_net_return": -0.4289255644608144, "candles": 134, "completed_trades": 3, "exposure_bars": 31, "max_drawdown": -0.06648936020599527, "net_return": -0.02167957972980339, "status": "ok"}

## Avisos obrigatórios

- EXPLORATÓRIO — NÃO É PROVA
- Baseline pedagógico SMA-20 fixo; seleção repetida de regras/parâmetros aumenta risco de sobreajuste.
- Retorno por candle considera open→close quando a posição está aberta; gaps entre candles são simplificados.
- Amostra de validação pequena: menos de 10 operações completas; resultado inconclusivo.

Não valida a Trilha B, não altera parâmetros congelados e não prova rentabilidade.
