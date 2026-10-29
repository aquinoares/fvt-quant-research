# Relatório de qualidade — Trilha A

**EXPLORATÓRIO — NÃO É PROVA.**

- Execução UTC: 2026-10-29T09:51:18Z
- Estado: backfill_pending
- Fonte pública: Binance Spot; símbolo BTCUSDT; intervalo 1m.
- Requisições: 10/10.
- Candles novos nesta execução: 7000.
- Candles únicos persistidos: 149458.
- Primeira data UTC: 2020-01-01T00:00:00Z.
- Cobertura desde o primeiro candle: 99.638667% (149458 / 150000 minutos).
- Dias com lacunas UTC registrados: 3.
- Lacunas encontradas antes: 3 intervalos / 542 minutos ausentes.
- Lacunas totalmente preenchidas: 0; candles recuperados dentro delas: 0.
- Lacunas remanescentes: 3 intervalos / 542 minutos ausentes.
- Duplicatas removidas/ignoradas: 0.
- Último candle fechado UTC: 2020-04-14T03:59:00Z.
- Idade do último candle (s desde abertura): 206430738.
- Backfill estimado pendente: 3440511 candles.
- Páginas vazias: 3; registros recebidos da API: 7000.
- HTTP: sem erro HTTP registrado.

## Observações

Backfill continua em próximas execuções; lacunas e atraso são registrados sem impedir nova coleta.

Candles de 4h são agregados localmente nos baldes UTC 00:00, 04:00, 08:00, 12:00, 16:00 e 20:00, somente com 240 candles de 1m contíguos e fechados.
Esta coleta não usa endpoints privados, chaves, ordens nem artefatos/estado da Trilha B.
