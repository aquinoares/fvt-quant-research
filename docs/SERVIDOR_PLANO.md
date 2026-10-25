# Plano de preparação de servidor — somente planejamento

Este documento não escolhe provedor, não cria servidor e não inicia nem reinicia sessão da Trilha B.

## Trilha A — coletor reutilizável

- O coletor deve ser importável como módulo Python em `learning/collector/` e executado com `python -m learning.collector`.
- GitHub Actions e um servidor futuro devem chamar a mesma CLI e explicitar o diretório de dados e orçamento máximo de requisições.
- Persistir apenas candles públicos e relatórios de qualidade versionados; manter tempos UTC, lacunas, duplicatas, idade e backfill auditáveis.
- Planejar serviço com reinício automático, logs rotacionados, limites de recursos, tratamento de bloqueio regional e ping de saúde.

## Saúde e alertas

O ping de saúde deve informar se o processo está vivo e quando a última coleta terminou. Processo vivo não significa dados recentes, qualidade boa ou retorno financeiro. Diferenciar estado ativo, feed antigo, erro de API e backfill pendente.

## Trilha B — bloqueio antes de qualquer nova janela

Não provisionar nem iniciar a Trilha B com base neste plano. Antes de qualquer nova janela, o responsável deve aprovar e registrar uma emenda formal **antes do início**, contendo a regra de tolerância, a política de backfill, a janela e a autorização. Até essa decisão, a Trilha B permanece parada. Não preencher lacunas retroativamente, mudar parâmetros congelados ou reabilitar o workflow desabilitado.
