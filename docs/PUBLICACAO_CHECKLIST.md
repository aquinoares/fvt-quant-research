# Checklist de segurança para repositório público

Checklist manual para o responsável. A inclusão deste arquivo não executa nenhuma etapa.

- [ ] Em clone local completo, rodar Gitleaks em todas as refs e no histórico, com valores sensíveis redigidos na saída.
- [ ] Se for encontrada credencial real, revogá-la e investigar a origem; não basta apagar o valor do arquivo atual.
- [ ] Revisar e-mails usados como autor/committer nos commits e decidir o padrão futuro (por exemplo, endereço noreply do GitHub). Não reescrever o histórico sem decisão explícita.
- [ ] Em Settings → Rules/Rulesets, configurar proteção de `main`: impedir force-push/exclusão e exigir revisão e checks necessários depois de confirmar seus nomes reais.
- [ ] Confirmar visualmente em Actions que **P6-MOM Cloud Shadow Live** continua desabilitado. Não reabilitar nem despachar o workflow.
- [ ] Revisar arquivos, feeds, relatórios e artefatos antes de cada nova publicação; números públicos precisam ter fonte versionada.
- [ ] Conferir permissões mínimas por job; `pages: write` e `id-token: write` só podem existir no job de deploy.
- [ ] Confirmar que nenhum segredo, e-mail ou dado pessoal aparece no HTML, feeds, logs ou relatórios do painel.
- [ ] Confirmar que esta mudança não cria `ENABLE_PUBLIC_PAGES` e não altera a visibilidade do repositório.

## Primeira coleta manual após o merge: o que verificar

Execute esta lista somente depois dos PRs serem revisados/mesclados na ordem documentada; esta alteração não dispara a coleta.

1. [ ] Antes da execução, confirmar visualmente em Actions que **P6-MOM Cloud Shadow Live** segue desabilitado. Não habilitar nem despachar esse workflow.
2. [ ] Abrir **Learning Track — Public Candle Collector** e usar `workflow_dispatch` na referência de código pós-merge. Não usar force push nem mudar permissões/visibilidade.
3. [ ] Conferir o resultado do run. Para HTTP **403/451**, confirmar que o relatório registra `status: blocked`, `api_http_status` e a mensagem de possível bloqueio geográfico/regional; não tentar contornar a restrição.
4. [ ] Confirmar que o commit de estado, quando houver mudanças, está em `learning-state`, não em `main` nem em `p6-mom-runtime`. O commit deve conter somente `learning/data/`, `learning/reports/` e saídas geradas de `learning/experiments/`.
5. [ ] Abrir `learning/reports/latest.json` e `latest.md` na branch `learning-state`. Verificar `run_at_utc`, status, candle count, cobertura, lacunas, duplicatas e HTTP. Se o relatório estiver ausente, vazio ou corrompido, a aba Aprendizado deve mostrar `—` e um motivo, sem reutilizar métricas antigas nem converter ausência em zero.
6. [ ] Conferir o backtest gerado em `learning/experiments/latest_backtest.json` e `latest_backtest.md`: rótulo `EXPLORATÓRIO — NÃO É PROVA`, custos declarados e avisos de amostra. Não usar isso como prova de rentabilidade nem como entrada da Trilha B.
7. [ ] Depois da primeira execução válida, fazer uma segunda execução manual para testar idempotência. Verificar que não há chaves duplicadas `(symbol, interval, open_time_ms)` nos CSVs e que candles já persistidos não são contados duas vezes; aceitar candles novos legítimos entre as execuções.
8. [ ] Se houver falha de push, confirmar que os logs mostram fetch/reaplicação e no máximo três tentativas, sem force push. Se esgotadas, o workflow deve falhar com mensagem clara.
9. [ ] Depois da execução, confirmar novamente que **P6-MOM Cloud Shadow Live** continua desabilitado, que `main` não recebeu commit de dados de aprendizado e que GitHub Pages não foi publicado/habilitado.
