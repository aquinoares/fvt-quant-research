# Backtest didático da Trilha A

**EXPLORATÓRIO — NÃO É PROVA.**

- Gerado em UTC: 2026-10-28T12:43:38Z
- Método: Baseline long-only SMA-20 não otimizado; sinal usa candles anteriores e custos por lado.
- Custo ida e volta: 30 bps.
- Treino (primeiros 70%): {"buy_hold_net_return": 0.18665552284316633, "candles": 352, "completed_trades": 16, "exposure_bars": 189, "max_drawdown": -0.10896142447892143, "net_return": 0.10585180142095907, "status": "ok"}
- Validação (últimos 30%): {"buy_hold_net_return": -0.24626693230585806, "candles": 151, "completed_trades": 6, "exposure_bars": 66, "max_drawdown": -0.10720801020778947, "net_return": 0.15240730902638489, "status": "ok"}

## Avisos obrigatórios

- EXPLORATÓRIO — NÃO É PROVA
- Baseline pedagógico SMA-20 fixo; seleção repetida de regras/parâmetros aumenta risco de sobreajuste.
- Retorno por candle considera open→close quando a posição está aberta; gaps entre candles são simplificados.
- Amostra de validação pequena: menos de 10 operações completas; resultado inconclusivo.

Não valida a Trilha B, não altera parâmetros congelados e não prova rentabilidade.
