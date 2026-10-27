# Backtest didático da Trilha A

**EXPLORATÓRIO — NÃO É PROVA.**

- Gerado em UTC: 2026-10-27T01:46:09Z
- Método: Baseline long-only SMA-20 não otimizado; sinal usa candles anteriores e custos por lado.
- Custo ida e volta: 30 bps.
- Treino (primeiros 70%): {"buy_hold_net_return": 0.3299392170044666, "candles": 224, "completed_trades": 12, "exposure_bars": 138, "max_drawdown": -0.08398714422495102, "net_return": 0.21134649119717985, "status": "ok"}
- Validação (últimos 30%): {"buy_hold_net_return": -0.01090345629506484, "candles": 97, "completed_trades": 4, "exposure_bars": 30, "max_drawdown": -0.0863883817348775, "net_return": -0.06974399132981424, "status": "ok"}

## Avisos obrigatórios

- EXPLORATÓRIO — NÃO É PROVA
- Baseline pedagógico SMA-20 fixo; seleção repetida de regras/parâmetros aumenta risco de sobreajuste.
- Retorno por candle considera open→close quando a posição está aberta; gaps entre candles são simplificados.
- Amostra de validação pequena: menos de 10 operações completas; resultado inconclusivo.

Não valida a Trilha B, não altera parâmetros congelados e não prova rentabilidade.
