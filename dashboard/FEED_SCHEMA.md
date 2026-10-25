# Schema real do feed FVT Dashboard (snapshot 2026-10-25)

Fonte observada: artefato privado fvt-dashboard-preview-40145053949 do workflow FVT Dashboard.

A versão do feed efetivamente inspecionada continha:
- `schema_version`, `dashboard_version`, `updated_at_utc`, `source_label`.
- `strategy`: `protocol`, `variant`, `symbol`, `signal_timeframe_minutes`, `lookback`, `threshold`, `risk_limit`, `window_start_utc`, `window_end_utc`, `costs`, `winner_id`, `manifest_sha256`.
- `historical.train` e `historical.validation` com métricas agregadas; o feed não continha lista individual das operações nem buy-and-hold.
- `shadow`: `status`, `status_label`, `status_detail`, `max_drawdown_net`, `breached`, `last_timestamp`, `segments_count`, `candles_observed`, `continuity`, `events`.
- O feed inspecionado não continha relógio de servidor, contagem de candles/lacunas em 48h, horário da próxima barra de 4h, posição/preço/horário de entrada, timeline de sinais, algoritmo de hash, nem metadados dos commits.

A v0.3 do workflow anexa metadados de saúde derivados dos CSVs da sessão, crons reais e metadados de auditoria do GitHub. Campos ainda ausentes na sessão permanecem `null` ou ausentes; não são sintetizados.

Contrato opcional de timeline: o verificador só roda quando um feed futuro trouxer `signal_timeline.records` e `signal_timeline.integrity` com `algorithm="SHA-256"`, `canonicalization="JSON.stringify(record_without_hash)_UTF8"`, `hash_field="record_hash"`, `previous_hash_field="prev_hash"` e `initial_previous_hash` explicitamente presente. Este contrato opcional não existia no feed real de 2026-10-25; os fixtures de hash são sintéticos e servem exclusivamente para testar a condição de segurança.


Metadados de auditoria da v0.3: `audit.panel_commit_sha` identifica o commit do painel; `audit.panel_run` contém o ID/URL da execução do workflow que gerou o snapshot, quando disponíveis; `audit.collector_last_run` representa a execução do coletor consultada e não prova a validade da sessão. Os incidentes são apresentados a partir de `shadow.events[]` (`event`, `at_utc`, `detail`). O painel só exibe decisão humana quando o evento já contém `human_decision` com horário, responsável, decisão e assinatura/commit; caso contrário, mantém “decisão pendente do responsável” e não cria uma decisão.

## Campos estruturados da ocorrência e frescor do coletor

O workflow FVT Dashboard acrescenta o objeto **shadow.incident** sem editar o estado persistido do coletor:

| Campo | Tipo | Origem / regra |
|---|---|---|
| shadow.incident.event | string ou null | event do último evento operacional relevante já presente em shadow.events[]; nenhum evento novo é criado. |
| shadow.incident.at_utc | string UTC ou null | at_utc do mesmo evento persistido. |
| shadow.incident.tolerance_seconds | inteiro não negativo ou null | Lido, somente para leitura, do workflow existente .github/workflows/p6-mom-cloud-live.yml. O builder exige encontrar exatamente uma guarda para age_seconds e uma para seconds_after_start, e que ambas declarem o mesmo inteiro. Se a estrutura faltar, for ambígua ou divergir, publica null. |
| shadow.incident.delay_seconds | inteiro não negativo ou null | Copiado exclusivamente de delay_seconds numérico já existente no objeto do evento. Não é extraído do texto detail nem calculado a partir da hora de criação do run. Se não existir como campo estruturado, permanece null. |

O painel exibe “— · tolerância não informada no feed” quando a tolerância é nula e “— · atraso não informado no feed” quando o atraso é nulo. A comparação só aparece quando os dois números estiverem presentes. Não há fallback para um número fixo nem parsing do texto em inglês.

### Proveniência e idade da execução do coletor

| Campo | Tipo | Origem / regra |
|---|---|---|
| audit.collector_last_run.head_branch | string ou null | head_branch retornado pela API de workflow runs do GitHub. |
| audit.collector_last_run.main_commit_sha | string SHA ou null | Copia head_sha somente quando a API informa head_branch igual a main. O painel não chama esse SHA de commit que criou o coletor. |
| audit.collector_last_run.created_at | timestamp UTC ou null | Horário de criação do run retornado pela API do GitHub. É a base da idade exibida. |
| audit.collector_last_run.run_started_at | timestamp UTC ou null | Horário de início retornado pela API, se disponível. |

A idade do coletor é calculada no painel como agora menos created_at. O limiar do aviso é 1,5 vezes o intervalo derivado de health_schedule.collector_cron. Acima dele, o painel mostra um aviso separado “coletor sem execução recente — verificar Actions”. Esse aviso não substitui nem altera shadow.status (inclusive protocol_stopped). Se created_at ou o cron estiver ausente/inválido, a idade/comparação é “—” com o motivo.
