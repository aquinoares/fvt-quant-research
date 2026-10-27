# Backtest didático da Trilha A

**EXPLORATÓRIO — NÃO É PROVA.**

- Gerado em UTC: 2026-10-27T07:44:31Z
- Método: Baseline long-only SMA-20 não otimizado; sinal usa candles anteriores e custos por lado.
- Custo ida e volta: 30 bps.
- Treino (primeiros 70%): {"buy_hold_net_return": 0.3215418118117215, "candles": 247, "completed_trades": 12, "exposure_bars": 156, "max_drawdown": -0.08398714422495102, "net_return": 0.1950010075350741, "status": "ok"}
- Validação (últimos 30%): {"buy_hold_net_return": -0.15862244437528406, "candles": 107, "completed_trades": 3, "exposure_bars": 16, "max_drawdown": -0.07579815371594445, "net_return": -0.06663424465462553, "status": "ok"}

## Avisos obrigatórios

- EXPLORATÓRIO — NÃO É PROVA
- Baseline pedagógico SMA-20 fixo; seleção repetida de regras/parâmetros aumenta risco de sobreajuste.
- Retorno por candle considera open→close quando a posição está aberta; gaps entre candles são simplificados.
- Amostra de validação pequena: menos de 10 operações completas; resultado inconclusivo.

Não valida a Trilha B, não altera parâmetros congelados e não prova rentabilidade.
