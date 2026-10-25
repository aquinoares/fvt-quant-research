# Decisão pendente: login e proteção do painel

**Nenhum login foi implementado.** Esta nota documenta as opções para decisão posterior do responsável.

## Limite fundamental do site estático público

Um formulário de login feito apenas em JavaScript **não protege dados**. O navegador pode baixar e inspecionar o HTML/JavaScript, e arquivos como `dashboard/data.json` ou outros feeds versionados no repositório público continuam acessíveis diretamente. Um porteiro visual só altera a experiência da tela; não pode autorizar acesso real nem esconder conteúdo que já foi publicado. Não guardar senhas, hashes de senha, tokens ou segredos no código do painel ou em arquivos versionados.

## Opções

### (a) Não ter login

Manter o painel assumidamente público e somente de leitura. É o caminho mais simples enquanto os dados publicados forem destinados ao público; antes de versionar novos resultados, revisar o checklist de publicação.

### (b) Porteiro visual — explicitamente não é segurança

Mostrar uma tela inicial de apresentação ou um botão “Entrar”, com aviso visível de que “isso não protege dados”. É apenas uma decisão de apresentação/navegação. Não bloquearia acesso direto a `data.json`, HTML, código, relatórios ou URLs públicas.

### (c) Autenticação do lado do servidor, usando serviço externo

Exige um provedor de identidade e uma camada confiável no servidor ou middleware/edge para validar sessão e autorização antes de entregar dados privados. Os dados que precisarem de proteção devem sair do repositório público e não podem continuar acessíveis em feeds públicos estáticos. Credenciais de integração ficam apenas em variáveis/segredos do ambiente de servidor; usar cookies de sessão seguros, autorização por recurso, expiração/renovação, proteção contra CSRF, limitação de tentativas, recuperação de acesso e logs sem segredos. Também é necessário definir domínio/redirects, política de privacidade, rotina de revogação e testes de acesso não autorizado.

Antes de escolher um plano gratuito, verificar os limites atuais de usuários ativos, requisições/API, projetos e ambientes, autenticação por e-mail/SMS, custom domains, MFA, funções server-side/edge, logs e retenção, suporte, quotas e regras de suspensão. Os limites variam e devem ser confirmados nas páginas oficiais do serviço escolhido, não presumidos.

## Ponto de parada

O responsável deve escolher explicitamente (a), (b) ou (c). Até essa escolha, manter o painel sem login e não adicionar código de autenticação.
