# Baseline da estrategia Pai / Filho / Trindade

## Escopo

Primeira hipoteses operacional para BTC/USDT spot, candles de 1 minuto e contexto de 15 minutos. O motor e apenas de pesquisa/backtest; nao acessa chaves de corretora nem envia ordens.

## Regras iniciais

- **Pai (15m):** tendencia por EMA rapida/lenta e inclinacao da EMA rapida. Cada candle de 15 minutos so fica disponivel depois do seu horario de fechamento.
- **Filho (1m):** alinhamento da direcao por EMAs e inclinacao recente.
- **Fibonacci:** nivel 61,8% de uma faixa rolante conhecida antes do candle atual; o contato exige tolerancia baseada em ATR e reacao altista observavel.
- **Regime:** z-score da distancia para a media rolante, usado apenas como filtro estatistico, nao como atrator de Lorenz.
- **Atividade/volume:** volume cotado relativo a media das barras anteriores; nao infere direcao por si so.
- **Momentum:** inclinacao de log-preco normalizada pela volatilidade e variacao dessa inclinacao em uma janela posterior.
- **Trindade:** compra somente quando todos os filtros estiverem alinhados. O fluxo de sinais e de eventos: `1` abre uma posicao spot, `-1` fecha apenas uma posicao aberta e `0` nao altera o estado. `-1` nunca e uma venda a descoberto.

## Cuidados de causalidade

O nivel Fibonacci usa `high` e `low` atrasados uma barra. A media de volume compara o volume atual com uma media deslocada que contem apenas barras anteriores. O contexto Pai e unido ao minuto pelo instante de disponibilidade do candle de 15 minutos, nao pelo inicio dele. O teste de causalidade modifica candles futuros e verifica que features/sinais passados permanecem iguais.

## Hipotese a testar

A convergencia de todos os modelos melhora o retorno liquido ajustado ao risco em relacao a benchmarks simples e a versoes sem cada filtro, fora da amostra e apos custos. Nenhuma formula implica lucro por si so.

## Semantica dos sinais

A funcao mantem um estado interno para emitir eventos de entrada/saida em vez de classificar cada candle lateral como uma saida. A ultima posicao eventualmente aberta e liquidada pelo contrato do backtester no ultimo preco disponivel.

## Limites desta primeira baseline

- Spot long-only; nenhuma venda a descoberto ou alavancagem.
- A execucao simulada usa abertura seguinte conforme o contrato do backtester existente.
- Taxas e slippage sao parametros assumidos; devem ser calibrados e stressados.
- Sem sizing por risco, stop-loss/target intrabar ou modelo de impacto de mercado nesta etapa.
- O resultado de 90 dias e exploratorio. Reservar periodos cronologicos para walk-forward e holdout antes de conclusoes.
- Se nao houver entradas, relatar frequencia zero em vez de interpretar retorno zero como sucesso.
