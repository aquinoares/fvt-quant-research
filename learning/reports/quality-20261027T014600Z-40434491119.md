# Relatório de qualidade — Trilha A

**EXPLORATÓRIO — NÃO É PROVA.**

- Execução UTC: 2026-10-27T01:46:00Z
- Estado: backfill_pending
- Fonte pública: Binance Spot; símbolo BTCUSDT; intervalo 1m.
- Requisições: 10/10.
- Candles novos nesta execução: 8646.
- Candles únicos persistidos: 77586.
- Primeira data UTC: 2020-01-01T00:00:00Z.
- Cobertura desde o primeiro candle: 99.469231% (77586 / 78000 minutos).
- Dias com lacunas UTC registrados: 2.
- Lacunas encontradas antes: 1 intervalos / 60 minutos ausentes.
- Lacunas totalmente preenchidas: 0; candles recuperados dentro delas: 0.
- Lacunas remanescentes: 2 intervalos / 414 minutos ausentes.
- Duplicatas removidas/ignoradas: 0.
- Último candle fechado UTC: 2020-02-24T03:59:00Z.
- Idade do último candle (s desde abertura): 210548820.
- Backfill estimado pendente: 3509146 candles.
- Páginas vazias: 1; registros recebidos da API: 8646.
- HTTP: sem erro HTTP registrado.

## Observações

Backfill continua em próximas execuções; lacunas e atraso são registrados sem impedir nova coleta.

Candles de 4h são agregados localmente nos baldes UTC 00:00, 04:00, 08:00, 12:00, 16:00 e 20:00, somente com 240 candles de 1m contíguos e fechados.
Esta coleta não usa endpoints privados, chaves, ordens nem artefatos/estado da Trilha B.
