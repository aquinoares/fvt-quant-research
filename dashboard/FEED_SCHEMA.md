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
