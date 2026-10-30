# Backtest didático da Trilha A

**EXPLORATÓRIO — NÃO É PROVA.**

- Gerado em UTC: 2026-10-30T08:32:54Z
- Método: Baseline long-only SMA-20 não otimizado; sinal usa candles anteriores e custos por lado.
- Custo ida e volta: 30 bps.
- Treino (primeiros 70%): {"buy_hold_net_return": -0.09663377031936393, "candles": 510, "completed_trades": 22, "exposure_bars": 269, "max_drawdown": -0.1663022341837631, "net_return": 0.2816058331936715, "status": "ok"}
- Validação (últimos 30%): {"buy_hold_net_return": 0.47297107902236224, "candles": 220, "completed_trades": 9, "exposure_bars": 148, "max_drawdown": -0.0867825621921432, "net_return": 0.21677380092501952, "status": "ok"}

## Avisos obrigatórios

- EXPLORATÓRIO — NÃO É PROVA
- Baseline pedagógico SMA-20 fixo; seleção repetida de regras/parâmetros aumenta risco de sobreajuste.
- Retorno por candle considera open→close quando a posição está aberta; gaps entre candles são simplificados.
- Amostra de validação pequena: menos de 10 operações completas; resultado inconclusivo.

Não valida a Trilha B, não altera parâmetros congelados e não prova rentabilidade.
