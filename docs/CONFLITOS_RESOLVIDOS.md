# Resoluções de conflito — integração v0.3 + Trilha A

## Base e origem

- Base da nova branch: `feat/fvt-dashboard-v0.3-feed-driven` (head anterior à integração: `d034984ba0d4303a92ce9fbb7e646ad29d5b4bbf`).
- Segunda ponta do merge: `feat/learning-track-public-safety` (head: `4b5cdde3d3be8b22a38c097623df9afe50e5f7e4`).
- O commit de integração terá os dois heads como pais. PR #1 e PR #2 não serão movidos nem mesclados.

## 1. `.github/workflows/fvt-dashboard.yml`

**Conflito:** v0.3 tem verificações de integridade do manifesto, testes Node, avaliação da saúde do feed, auditoria e permissões de Pages opt-in; Trilha A adiciona alimentação do relatório de candles.

**Resolução:** preservado o workflow v0.3 e adicionada a leitura somente de artefatos versionados da Trilha A (`learning/reports/latest.json`, `learning/experiments/registry.json`, `learning/experiments/latest_backtest.json` e `learning/hypotheses.jsonl`). Campos B&H, melhor trade, cobertura e projeção permanecem ausentes se sua fonte não estiver acessível. `pages: write` e `id-token: write` ficam somente no job de deploy. O opt-in existente `ENABLE_PUBLIC_PAGES == 'true'` é preservado; nenhuma variável foi criada.

## 2. `dashboard/index.html`

**Conflito:** as interfaces eram diferentes. Substituir o HTML robusto de v0.3 pelo HTML simples da Trilha A perderia controles de frescor, integridade de hash, estado de risco, auditoria e fixtures do v0.3.

**Resolução:** mantida a interface v0.3 como base; adicionadas faixa das trilhas, histórico derivado de fonte, seção Aprendizado e aba Decisões. Dados externos são apresentados por nós DOM e `textContent`; o painel não usa `innerHTML` para conteúdo dinâmico nem scripts externos. Após erro de consulta, os números anteriores são ocultados.

## 3. `dashboard/data.json`

**Conflito:** o schema de Trilha A era reduzido e omitiria campos de saúde, auditoria, critérios congelados e estado sombra do v0.3.

**Resolução:** preservados os campos originais do v0.3, incluindo estratégia, histórico, shadow, collection_health, health_schedule, audit e frozen_acceptance_criteria. Acrescentados objetos independentes para learning, operations_projection, decision e incident_timeline. O status da emenda é consumido apenas do campo `decision.amendment_status`; o painel não interpreta o texto da minuta.

## Escopo protegido

Não se altera `.github/workflows/p6-mom-cloud-live.yml`, manifesto congelado, ledger, arquivos de estratégia, estado da sessão ou branch `p6-mom-runtime`. Nenhuma sessão foi reiniciada, lacuna preenchida retroativamente, nem emenda escolhida ou assinada.
