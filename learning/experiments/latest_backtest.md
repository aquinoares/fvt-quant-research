# Backtest didático da Trilha A

**EXPLORATÓRIO — NÃO É PROVA.**

- Gerado em UTC: 2026-10-29T09:51:28Z
- Método: Baseline long-only SMA-20 não otimizado; sinal usa candles anteriores e custos por lado.
- Custo ida e volta: 30 bps.
- Treino (primeiros 70%): {"buy_hold_net_return": -0.24370844042322837, "candles": 434, "completed_trades": 19, "exposure_bars": 220, "max_drawdown": -0.12827876631926116, "net_return": 0.08187739912270664, "status": "ok"}
- Validação (últimos 30%): {"buy_hold_net_return": 0.3033150964338607, "candles": 186, "completed_trades": 8, "exposure_bars": 111, "max_drawdown": -0.10105200459287411, "net_return": 0.15443570697646058, "status": "ok"}

## Avisos obrigatórios

- EXPLORATÓRIO — NÃO É PROVA
- Baseline pedagógico SMA-20 fixo; seleção repetida de regras/parâmetros aumenta risco de sobreajuste.
- Retorno por candle considera open→close quando a posição está aberta; gaps entre candles são simplificados.
- Amostra de validação pequena: menos de 10 operações completas; resultado inconclusivo.

Não valida a Trilha B, não altera parâmetros congelados e não prova rentabilidade.
