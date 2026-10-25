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
