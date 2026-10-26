# Trilha A — Aprendizado

**EXPLORATÓRIO — NÃO É PROVA.** Esta trilha existe para coleta pública, qualidade de dados e experimentos didáticos. É independente da Trilha B e não importa seus parâmetros, manifesto, ledger, sessão ou estado.

## Coleta

- Endpoint público anônimo: https://data-api.binance.vision/api/v3/klines
- Mercado: Binance Spot, BTCUSDT, candles de 1 minuto.
- O coletor só pede candles fechados, pagina por startTime e endTime, limita cada execução a 10 páginas por padrão e continua o backfill nas execuções seguintes.
- A data inicial configurável para uma base vazia é 2020-01-01 00:00:00 UTC. Para alterar esse ponto de partida, defina LEARNING_START_UTC com ISO 8601 e fuso explícito. Isso é apenas o limite inicial da pesquisa, não uma afirmação sobre o início do mercado.
- Os dados 1m são particionados por mês em learning/data/BTCUSDT_1m. A chave lógica é símbolo + intervalo + open_time_ms. Duplicatas e linhas inválidas são ignoradas/removidas.
- Candles 4h são agregados localmente em baldes UTC iniciados às 00:00, 04:00, 08:00, 12:00, 16:00 e 20:00; só são escritos quando todas as 240 barras de 1m estão contíguas e fechadas.
- Cada execução grava learning/reports/latest.json, latest.md e cópias arquivadas por execução. O resumo também é publicado no GitHub Actions.
- HTTP 403/451 é tratado como possível bloqueio geográfico/regional: a execução gera relatório e falha claramente; não usa chaves nem tenta contornar restrições.

## Execução local

python -m learning.collector --root learning --max-requests 10

python -m learning.experiments.backtest --root learning

O workflow cloud roda por agendamento horário (`13 * * * *`) ou por `workflow_dispatch`, sem gatilho push. O evento schedule é executado na branch padrão; antes da coleta, o workflow restaura o estado persistido da branch dedicada `learning-state`. Após a coleta, grava somente `learning/data/`, `learning/reports/` e os relatórios gerados `learning/experiments/latest_backtest.json` e `learning/experiments/latest_backtest.md` nessa branch, usando um worktree separado e destino explícito. Assim, o workflow não cria commits de estado em `main` e não toca na `p6-mom-runtime`. O painel restaura esses caminhos da `learning-state`; código, testes, registro de experimentos e hipóteses vêm da referência que está sendo construída. Consulte [docs/LEARNING_STATE_BRANCH.md](../docs/LEARNING_STATE_BRANCH.md). O workflow usa concurrency fixo sem cancelar execuções em andamento; em falha de push, faz fetch, reaplica artefatos e tenta novamente até três vezes, sem force push. Um relatório ausente/vazio/corrompido deve deixar os campos de qualidade como `—` com o motivo.

## Backtest didático

O exemplo usa uma regra SMA-20 fixa sobre candles agregados em 4h, divisão temporal 70% treino / 30% validação e custo declarado de 30 bps por ida e volta (15 bps por lado). O baseline não é otimizado e simplifica o retorno para open→close durante barras com posição; gaps entre barras limitam a validade. A amostra inferior a 10 operações completas é sinalizada como inconclusiva. Selecionar regras repetidamente pode causar sobreajuste. Não copiar resultados para a Trilha B nem interpretar os como prova de rentabilidade.

## Segurança e operação


## Skill do agente

O workflow local de pesquisa pode ser invocado por Codex como trader-skill em .agents/skills/trader-skill/SKILL.md. Ele é uma adaptação instrucional de strategy-generate do HKUDS/Vibe-Trading, com atribuição e licença em .agents/skills/trader-skill/UPSTREAM.md. Ele não importa o runtime nem substitui os testes do projeto.

## Repositório público

O repositório está público por decisão do responsável. Revise o histórico e as credenciais de acordo com [docs/PUBLICACAO_CHECKLIST.md](../docs/PUBLICACAO_CHECKLIST.md).
