# Backtest didático da Trilha A

**EXPLORATÓRIO — NÃO É PROVA.**

- Gerado em UTC: 2026-10-27T14:23:22Z
- Método: Baseline long-only SMA-20 não otimizado; sinal usa candles anteriores e custos por lado.
- Custo ida e volta: 30 bps.
- Treino (primeiros 70%): {"buy_hold_net_return": 0.3937860902876822, "candles": 270, "completed_trades": 14, "exposure_bars": 176, "max_drawdown": -0.08398714422495102, "net_return": 0.18400615000303167, "status": "ok"}
- Validação (últimos 30%): {"buy_hold_net_return": -0.07186224482267345, "candles": 116, "completed_trades": 4, "exposure_bars": 33, "max_drawdown": -0.08132674289857855, "net_return": -0.03515818316073038, "status": "ok"}

## Avisos obrigatórios

- EXPLORATÓRIO — NÃO É PROVA
- Baseline pedagógico SMA-20 fixo; seleção repetida de regras/parâmetros aumenta risco de sobreajuste.
- Retorno por candle considera open→close quando a posição está aberta; gaps entre candles são simplificados.
- Amostra de validação pequena: menos de 10 operações completas; resultado inconclusivo.

Não valida a Trilha B, não altera parâmetros congelados e não prova rentabilidade.
