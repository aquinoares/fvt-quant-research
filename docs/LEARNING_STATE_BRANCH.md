# Persistência da Trilha A em `learning-state`

## Por que existe esta branch

O GitHub Actions executa um evento `schedule` na branch padrão do repositório (atualmente `main`). O workflow `.github/workflows/learning-collect.yml` deve usar o código da referência que acionou a execução, mas **não deve gravar os resultados na branch que contém o código**. Para separar código e estado gerado, os dados públicos da Trilha A são persistidos na branch dedicada `learning-state`.

A branch `learning-state` foi criada separadamente para esse estado. A alteração não cria commits em `main` e não escreve em `p6-mom-runtime`.

## Fluxo do coletor

1. O workflow é acionado por cron ou manualmente e faz checkout do código da referência do evento.
2. Antes da coleta, ele busca `learning-state` e restaura dali os dados e relatórios anteriores, para que o backfill continue em execuções subsequentes.
3. Executa o coletor público e o backtest educativo na cópia de trabalho efêmera do runner.
4. Copia para um worktree baseado em `learning-state` somente os resultados gerados: `learning/data/`, `learning/reports/` e os resultados gerados `learning/experiments/latest_backtest.json` e `learning/experiments/latest_backtest.md`.
5. Faz commit/push explícito para `HEAD:refs/heads/learning-state`. Se não houver mudanças, não cria commit.

A permissão `contents: write` permanece restrita ao job `collect`. O workflow não possui gatilho `push`, para evitar que os commits de estado gerem uma cadeia de novas execuções.

## Como o painel lê os dados

O workflow `.github/workflows/fvt-dashboard.yml` busca a branch `learning-state` e restaura somente os três caminhos de estado listados acima antes de montar o feed. O código, os testes, o registro de experimentos e o arquivo de hipóteses continuam vindo da referência de código que está sendo construída. O link do relatório de qualidade aponta para `learning-state`.

A Trilha A continua rotulada **EXPLORATÓRIO — NÃO É PROVA** e permanece independente da Trilha B. A branch de estado destina-se a candles públicos e relatórios de qualidade; não deve receber credenciais, dados pessoais, estado de sessão da Trilha B, manifesto congelado ou ledger operacional.

## Verificações e limites

- Os testes de contrato verificam o alvo explícito de push, os paths restaurados pelo painel e o link ao relatório.
- Os testes não executam uma coleta real e não provam que o endpoint público esteja acessível em produção.
- Não acionar `workflow_dispatch` durante esta auditoria: nenhuma coleta real foi executada.
- GitHub Pages permanece sujeito ao gate explícito de opt-in existente. Esta alteração não habilita publicação.
