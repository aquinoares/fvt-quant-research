# Backtest didático da Trilha A

**EXPLORATÓRIO — NÃO É PROVA.**

- Gerado em UTC: 2026-10-28T05:30:25Z
- Método: Baseline long-only SMA-20 não otimizado; sinal usa candles anteriores e custos por lado.
- Custo ida e volta: 30 bps.
- Treino (primeiros 70%): {"buy_hold_net_return": 0.26998372489636724, "candles": 331, "completed_trades": 16, "exposure_bars": 189, "max_drawdown": -0.10896142447892143, "net_return": 0.10585180142095907, "status": "ok"}
- Validação (últimos 30%): {"buy_hold_net_return": -0.2920970893349957, "candles": 143, "completed_trades": 5, "exposure_bars": 51, "max_drawdown": -0.10720801020778892, "net_return": 0.09325419841419769, "status": "ok"}

## Avisos obrigatórios

- EXPLORATÓRIO — NÃO É PROVA
- Baseline pedagógico SMA-20 fixo; seleção repetida de regras/parâmetros aumenta risco de sobreajuste.
- Retorno por candle considera open→close quando a posição está aberta; gaps entre candles são simplificados.
- Amostra de validação pequena: menos de 10 operações completas; resultado inconclusivo.

Não valida a Trilha B, não altera parâmetros congelados e não prova rentabilidade.
