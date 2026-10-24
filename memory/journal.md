# Journal de Pesquisa — FVT Quant Research

Registro cronologico de ciclos de trabalho. Append-only: nunca reescrever entradas antigas;
correcoes entram como nova entrada com referencia a anterior.

---

## 2026-10-22 — Ciclo de correcao, auditoria e P0

### 1. Bug de dupla conversão (H5) — achado, corrigido, travado
- Defeito em `scripts/run_backtest.py`: `events_to_position_targets()` antes de `run_backtest`
  transformava a saida `-1` em `0`, e o motor lia `0` como "manter estado" (nunca saia).
- Efeito medido (30 bps RT): bugado 1/0, exposicao 97,19%, liquido +29,20%, DD -8,55%
  -> corrigido 88/88, exposicao 0,78%, liquido -21,13%, DD -21,13%.
- Correcao aprovada pelo usuario: remocao do wrapper (eventos crus direto ao motor).
  Estado git: `M scripts/run_backtest.py` (**nao commitado**; commit e proibido sem pedido).
- Trava: `tests/test_run_backtest_regression.py` (5 testes; a assinatura do bug falha contra a versao antiga).

### 2. Auditoria fechada (etapa de correcao)
- Integridade do CSV: PASS — SHA256 `604835c5...`, 129.600 linhas, 0 saltos/duplicados.
- Suite: 24/24 na epoca; backtest exit 0; pesquisa exit 0 x2 (deterministica).
- `research/run_research.py`: check de lookahead corrigido para separar
  `final_position_signal_open_at_end` / `final_forced_liquidation_cost_charged_when_open`
  / `final_liquidation_cost_free_bias_bps` (errata 6.2 sincronizada no relatorio, ~linha 233).
- JSON regenerado deterministicamente: `research/out/research_results.json`
  SHA256 `71801c52...` (identico em duas execucoes); verificador report<->JSON: 129 PASS / 0 FAIL.
- Nenhuma metrica de pesquisa alterada pelo re-etiquetar do check.

### 3. Auditoria arquitetural vs referencia "Self-Improving AI Trading Research Loop" (A-F)
- Sem ledger de hipoteses, sem previsoes, sem journal (este arquivo), sem Sharpe/Sortino/Calmar/DSR
  (busca: zero ocorrencias), sem walk-forward real (`validacao_temporal_convergencia` se auto-rotula
  `IN_SAMPLE_TEMPORAL_DIAGNOSTIC_NOT_HELD_OUT`), sem kill switch (maxDD so e reportado).
- Sombra prospectiva EXISTE (`scripts/run_shadow_convergencia.py`, zero ordens) — confirmada como H9.
- Split 50/25/25 declarado a priori (P1), mas **bloco final 25% ja exposto** (relatorio 5.3).
- Lab adaptativo ranqueia `TESTE_30` por retorno liquido; JSON admite que nao e holdout limpo.
- Saida de ablation/validacao/lab nao persiste em `reports/` (gitignored); nenhum artefato de
  pesquisa esta versionado (3 commits historicos).
- Sequencia proposta: P0 ledger+journal -> P1 metricas honestas -> P2 walk-forward/stress ->
  P3 periodo selado.

### 4. Paridade motor vs lab v2 (H10) — divergencia medida
- Caso sintetico de 8 candles (compra no candle 0 e nunca sai, 15 bps/lado, fora do periodo selado):
  motor **+5,6245%** vs lab v2 **+6,6132%** -> delta **+0,9887 p.p.**
- Mecanismos: (a) motor descarta a ultima linha e zera `position.iloc[-1]`, v2 inclui
  `open[-1]->close[-1]` e mantem a posicao; (b) custo deslocado 1 linha (`turnover.shift(-1)`
  vs `turnover * rate`); (c) v2 conta `forced_end_liquidations` como saida executada.
- Custo TOTAL igual nos dois; exposicao 0,8571 vs 0,8750.
- Números do relatorio NAO sao afetados (caminho do motor). Risco: comparar colunas de mesmo nome.
- Guarda criada (aprovada): `tests/test_lab_engine_parity.py` documenta as duas convencoes;
  **o delta numerico nao esta travado** (decisao consciente nesta etapa).
- Hashes protegidos verificados pos-teste: `backtest.py` `727F9A8D...`,
  lab v1 `39CA3524...`, lab v2 `EEEB1B3F...` — inalterados.

### 5. Decisoes do proximo ciclo (definidas pelo usuario em 2026-10-22)
1. Sequencia: **P0 (ledger + journal) -> P1 (metricas honestas)**.
2. Sharpe: retornos diarios da estrategia, **incluindo dias em caixa com retorno zero**.
3. Versionamento: **NAO** executar `git add` nesta etapa.
4. DSR: **implementacao propria pequena**, com testes e sem dependencia externa.

### 6. Execucao do P0 (esta entrada)
- `memory/hypotheses_ledger.jsonl` — 14 registros: H1..H10 (hipoteses) + P1..P4 (protocolos/fatos),
  com `source`, `status` e `evidence` por registro. IDs reconstruidos em 2026-10-22 a partir de
  `research/RESEARCH_REPORT.md` (1.2 e 5.3), `docs/strategy_baseline.md:23` e desta auditoria.
- `memory/journal.md` — este arquivo.
- `tests/test_memory_ledger.py` — valida esquema, IDs unicos, enums de status, existencia dos
  arquivos citados em `source` e a regra P2 (bloco final queimado) travada por conteudo.
- Nenhum arquivo existente alterado; nenhum commit; nenhum `git add`.

### 7. Execucao do P1 (mesmo dia; diffs apresentados e aprovados antes da gravacao)

- **Novos:** `research/dsr.py` (DSR proprio, so stdlib — Bailey & Lopez de Prado 2014,
  eq. 2-4: Gumbel para E[Z_max], SE com skew/kurt, p unilateral; sem scipy) e
  `tests/test_dsr.py` (9 testes, ancoras numericas do paper: M=100/T=1000 ->
  E=2,366 e SR_max=0,0749; identidade M=1; monotonicidade; M=10000).
- **Editado:** `research/run_research.py` — `DAYS_PER_YEAR=365`,
  `daily_returns_with_flat_days(equity, timestamps)` e 4 chaves de Sharpe novas em
  `metrics_block` (`daily_observations`, `sharpe_ratio_daily_mean/std`,
  `sharpe_ratio_annualized`), conforme decisao 2 (dias em caixa = zero).
- **Defeito na execucao do P1 e correcao minima:** a primeira execucao falhou com
  `AttributeError: 'int' object has no attribute 'normalize'` — o backtest herda o
  RangeIndex do CSV (o tempo vive na coluna `timestamp`, nao no indice). Correcao:
  timestamps passados por `run_one` alinhados por rotulo, com validacao de ausencia;
  falha barulhenta mantida (sem Sharpe falso). **Nenhum JSON foi gravado na falha**
  (o SHA continuou `71801c52...` ate a correcao).
- **JSON regenerado:** SHA256 `B6846495396EE711FCE87543BB224E0324C1F562E14E81CB9198E018DBBFAFC0`
  (106.272 bytes; antes `71801c52...`/91.533 bytes). Apenas adicao das chaves de Sharpe:
  a tabela impressa e todas as metricas antigas permanecem identicas (saida na tela confere
  com o relatorio).
- **Verificador relatorio<->JSON: 129 PASS / 0 FAIL (exit 0).**
- **Suite: 43/43** (34 anteriores + 9 do DSR).
- **Relatorio:** nova secao 5.6 com o Sharpe diario: M15_original @30bps FULL = **-12,98**
  (90 dias); ZERO FULL = +1,71; ZERO teste final = -8,76; demais variantes @30bps entre
  -12,03 e -27,64. Dias observados 45+22+23 = 90.
- **DSR nos numeros: adiado (P1c)** — `n_trials` ainda nao definido pelo usuario; a
  biblioteca fica pronta e testada em `research/dsr.py`.
- Ledger H6 permanece `pendente` (Sharpe medido; DSR nao ligado; ablation nao persistida).
- Nenhum `git add`; nenhum commit; `src/`, `data/` e testes pre-existentes intactos.

---

## 2026-10-22 — FASE 2: pre-registro do protocolo prospectivo (P5)

- **Escopo:** acrescentar P5 a `memory/hypotheses_ledger.jsonl` e esta entrada; nenhum
  outro arquivo alterado; sem git add, sem commits, sem downloads, sem execucao de
  estrategias.
- **Leitura previa:** ledger com 14 registros (H1..H10, P1..P4), proximo ID livre `P5`;
  journal com 98 linhas antes desta entrada (append-only preservado).
- **Regras formalizadas em P5:** inicio por regra (00:00 UTC do primeiro dia futuro com
  protocolo registrado + prontidao confirmada; nunca declarar antes), encerramento
  exatamente 30 dias depois com avaliacao final unica, apenas integridade de dados
  durante a janela (metricas proibidas), proibicao de ajuste com dados da janela,
  dados exploratorios nao misturados, limite de risco previo registrado como
  interrupcao (excecao unica de monitoramento), DSR bloqueado, elementos congelados
  antes do inicio.
- **Versao congelada da estrategia (hashes do working tree):**
  - `src/convergencia/strategy.py` 1C438D27945833AA61E84BC9BFDE3900BFEC50B6DE135E6ACBD2D9EB4ACEDF3B
  - `src/convergencia/backtest.py` 727F9A8D01700FEC98464E43DE2347E3F24DD6F5A0AC350C4ECD98A30B8A50FF
  - `src/convergencia/signals.py` EAFFC3D8762BE1BAD50002329EC8DFD4B9C75AAD50E6F94295CEF4AD4D1936A8
  - `src/convergencia/data.py` 6760EB50A6286556289879B157A09F9316B5FBE6B607E170C5420A264FC4D3BE
  - `src/convergencia/features/fibonacci.py` 9D1F56B01DC690817F3B63DD3C8EA7201225435E9D73BADDD07606A91AFF739B
  - `src/convergencia/features/fractal.py` DDB3BD5BE92A12F2BA35BA79B979E249731EB16208D0768B77D280C0B7A09636
  - `src/convergencia/features/momentum.py` F292C436D71CF7ACE286F0FB2ED5BCF960F9AB72D69F2A042F832FF39240CB83
  - `src/convergencia/features/regime.py` B4BD942FCFC9EA36A0A19FD2A80FC983CDDED35D750C52ECA7167C044BA23411
  - `src/convergencia/features/volume.py` 47C3E422A59A1623645837A6A73D1409ECE1C5A3AE3545171AC76A74D748A1F4
  - `scripts/run_backtest.py` 9C58030762A92E158FB449FCB61064C15090908CF0CCD5361470B2BF71256B78 (correcao H5, nao commitada)
  - `research/run_research.py` D4E8E3D72FB215CA0D257BECCFEF7D7F6F948F88D0A0EB64721A7FB8B227E1AD
  - `scripts/run_shadow_convergencia.py` 8D834AAA594B3E2139028C9A31AA214283A797626C2CDFB06E5ABD024F2A2413
  - Variante `M15_original` (relatorio 1.5); custos P4 (10+5 bps/lado); benchmark
    buy-and-hold liquido (2 lados) + caixa.
- **Pendencias registradas sem inventar valores:** data concreta de inicio; prontidao
  operacional (coletor nunca executado ao vivo; gravador continuo parado desde
  2026-10-21T04:08Z; procedimento de avaliacao final inexistente - run_research sem CLI
  e fixo no CSV de 90 dias); limite de risco (proposta -10% de drawdown liquido, aguarda
  aprovacao; sem ele a declaracao de inicio fica bloqueada); limiar de decisao
  (inexistente nos artefatos); n_trials (DSR bloqueado); nome dos arquivos da janela.
- Hashes de arquivos com alteracoes locais nao commitadas identificam o working tree;
  versionamento segue proibido sem ordem explicita (sem git add, sem commits).


## 20261023T013703Z â€” AprovaÃ§Ã£o do limite de risco P5

- Registro: P5-RISK
- Campos de auditoria: statement, source e recorded_at preenchidos.
- Limite: \limit_drawdown_net = -0.10\.
- Regra: \reached = max_dd <= limit_drawdown_net\.
- Atingimento do limite: bloquear novas entradas e registrar interrupÃ§Ã£o.
- Escopo: pesquisa em sombra, sem ordens reais.
- Esta aprovaÃ§Ã£o nÃ£o autoriza o inÃ­cio da janela de 30 dias.

## 2026-10-23 — Pré-registro da H11 (relative_volume vs retorno liquido em P5)

- **Registro:** H11 acrescentado a `memory/hypotheses_ledger.jsonl` (append byte-a-byte;
  16 -> 17 registros; IDs unicos preservados; nenhum registro anterior reescrito; prefixo
  original verificado por startswith). `record_type=hipotese`, `status=pendente`,
  `recorded_at=2026-10-23`.
- **Enunciado pré-registrado:** Na estratégia M15_original inalterada, entre operações
  elegíveis da futura janela prospectiva P5, valores maiores de `relative_volume` no
  instante do sinal de entrada estarão associados a menor probabilidade de retorno
  líquido positivo após os custos P4.
- **Base exploratoria (nao confirmatoria):** `research/out/trade_attribution_20261023T031936Z/report.md`
  com joins em `research/out/crossovers_dev_20261023T022656Z/trades.csv` e `signals.csv`
  (74 trades do dev: vencedoras mean 1,6706 / median 1,5085 vs perdedoras mean 2,6259 /
  median 1,8072; mesma direcao em treino e validacao; regime_zscore nao discrimina).
- **Teste pre-declarado:** Spearman entre `relative_volume` no timestamp do sinal de
  entrada (nao no candle de execucao) e indicador binario de retorno liquido > 0 pela
  contabilidade P4 real do motor; direcao prevista rho < 0; avaliacao unica no encerramento
  de P5 (durante a janela: apenas integridade e monitoramento de risco, conforme P5);
  sem limiares/cortes/subgrupos/parametros; sem alteracao de estrategia; relatorio
  obrigatoria de n, rho, operacoes sem feature e limitacoes; rho < 0 favoravel nao
  demonstra significancia estatistica nem rentabilidade; observacoes exploratorias
  permanecem exploratorias; bloco final historico exposto permanece queimado (P2).
- **Backups fora do repositorio:** `%LOCALAPPDATA%\Temp\opencode\fvt-memory-backup-20261023T033256Z\`
  (`hypotheses_ledger.jsonl.bak` e `journal.md.bak`; SHA256 conferidos contra os originais
  pre-append: ledger `D977FE82...`, journal `BED778E9...`).
- **Testes:** `pytest tests/test_memory_ledger.py` -> 7 passed (executados apos o append
  do ledger e reexecutados apos esta entrada no journal).
- **Escopo:** nenhum script, estrategia, motor, artefato exploratorio ou protocolo (P1-P5)
  alterado; nenhum `git add`/commit; sem rede, sem coleta, sem sessao sombra, sem janela
  de 30 dias iniciada; a declaracao de inicio de P5 segue bloqueada ate prontidao +
  confirmacao operacional.

## 2026-10-23 — Ciclos de busca: strategy_search (vencedor MOM_TF240_LB96) e candidatas GitHub (0 de 11)

- **Busca ampla `research/strategy_search.py`** → `research/out/strategy_search_20261023T035848Z/`
  (report.md, candidates.csv, best_config.json): 166 configs (9 familias, tf 1m–240m),
  16 aprovados nos criterios pre-declarados; vencedor `MOM_TF240_LB96` (momentum 240m,
  ROC 96 barras > +0,5%): treino +21,95% (PF 8,6 / 4 trades), val +6,47% (PF 9,1 / 3),
  dev +27,66% vs B&H 26,50%, maxDD ~-6%, stress 60bps +20,5% / +5,5%, causalidade por
  prefixo OK. Ressalvas registradas: 1 trade ≈ lucro total do treino, n=7, janela bull,
  validacao exploratoria (ja reusada na selecao).
- **Candidatas GitHub `research/github_strategies_search.py`** →
  `research/out/github_strategies_20261023T043330Z/` (report.md, candidates.csv,
  subperiods.csv, mom_baseline.csv, best_trades.csv, equity_best_dev.csv,
  best_config.json): 11 configs adaptadas de `trend_follow.py`/`hybrid_mm.py`
  (chencore/autoresearch-crypto) com simulador intrabarra 1m conservador (stop antes de
  sinal; gap de stop no pior caso; completion mask em map_to_1m; custo por lado
  consistente — dois bugs de implementacao encontrados e corrigidos antes da execucao
  final). Baseline do simulador validada no motor: MOM +22,01/+6,49 vs publicado
  +21,95/+6,47. Resultado: **0 de 11 passaram**; melhor candidata medida
  `GITHUB_SQUEEZE_BREAKOUT_A` (18/11 trades, -0,77%/-1,96% @30bps) = nao_passou; unica
  validacao positiva `GITHUB_SQUEEZE_BREAKOUT_B` (+3,54% val, 9/5 trades) com treino
  negativo = nao_passou. Adaptacao documentada unica: filtro de tendencia do
  `GITHUB_RSI_REENTRY` (regra original dispara 0/74 cruzas na janela; substituida pelo
  `is_uptrend` EMA20>EMA40 do proprio referenciado em 240m, 36/74) — sem busca
  de limiar.
- **Integridade**: suíte completa `pytest -q` → 171 passed; hashes protegidos inalterados
  (`backtest.py` 727F9A8D, `strategy.py` 1C438D27, `run_research.py` D4E8E3D7, CSV
  604835C5); bloco de teste [97200,129600) intocado (nunca lido); nada em `src/`
  alterado; nenhum `git add`/commit; pastas intermediarias com numeros de execucoes com
  bug removidas (só a execucao final 043330Z permanece); P5 nao iniciada (inicio segue
  bloqueado ate confirmacao operacional do usuario).
- **Decisao de pesquisa**: nenhuma candidata GitHub promovida; `MOM_TF240_LB96` permanece
  a melhor estrategia medida conhecida; validacao esgotada como evidencia independente;
  H11 segue pendente, avaliacao unica no encerramento de P5; proxima direcao
  (P5/abertura do bloco restante, refinamento ou encerramento) depende de decisao
  explicita do usuario.

## 2026-10-23/24 — Preparacao do protocolo prospectivo P6-MOM (MOM_TF240_LB96, 90 dias)

- **Escopo**: autorizacao do usuario para preparar (NAO iniciar) o teste prospectivo de
  90 dias da melhor estrategia da busca (`winner_id 722a0dd140`, momentum tf=240,
  lookback=96, thr=+0.5% ROC), com UMA chamada curta autorizada ao coletor (validacao
  de schema/timestamps/duplicatas/lacunas/integridade/leitura pelo runner; nenhuma
  metrica de desempenho; sem retry; sem endpoints de negociacao).
- **Chamada unica do coletor**: `download_klines.py` BTCUSDT 1m janela recente de ~2h
  para arquivo temporario em `%LOCALAPPDATA%\Temp\opencode\p6_collector_probe\`
  (120 candles; Qualidade PASS; 0 lacunas; 0 duplicatas; SHA256
  `8B190AA36CF54AFFCC5FC53DD9F0CDA2E097A29992DB2B110EFCCD3A74082893`); relatorio em
  `reports/data_quality_BTCUSDT_1m.json` (novo; nenhum relatorio pre-existente
  sobrescrito); validado tambem por `load_segment` do runner e `validate_ohlcv`.
- **Variante congelada**: novo `research/mom_tf240.py` (config igual ao vencedor;
  `build_events` delega sinais; `frozen_criteria` com veredicto
  APROVADO/REPROVADO/INCONCLUSIVO; <10 operacoes completas = INCONCLUSIVO sem
  flexibilizar); paridade de eventos contra `strategy_search.desired_and_events`
  travada por teste.
- **Separacao de protocolos** (P5 permanece inalterada; 198 testes passam, 27 novos em
  `tests/test_p6_mom_separation.py`): runner `run_shadow_prospectivo.py` aceita
  `--protocol P5|P6-MOM` (aprovacao, state, monitor e code_manifest exclusivos de cada
  protocolo; sessao de um protocolo nao resuma no outro); verificador
  `check_window_segments.py` aceita `--protocol` com janela de 90 dias e checagem de
  barras pai 240min para P6-MOM; avaliador `run_window_evaluation.py` aceita
  `--protocol` (90 dias, variante MOM, custos P4 + stress 60 bps, frozen_criteria no
  resultado final, recusa cruzada de fechamentos de outro protocolo).
- **Registro**: backup de `memory/hypotheses_ledger.jsonl` e `memory/journal.md` em
  `%LOCALAPPDATA%\Temp\opencode\p6_mom_backup_20261023T221745Z\` antes das alteracoes;
  ledger recebeu P6-MOM e P6-MOM-RISK por append (bytes anteriores preservados;
  schema validado por `tests/test_memory_ledger.py`); manifesto congelado em
  `research/out/p6_mom_freeze_20261024T011825Z/manifest.json` (config, hashes de
  codigo, custos, criterios de aceitacao, dados do probe).
- **Estado**: protocolo P6-MOM registrado como pre-registro ATIVO com
  `window_start_authorized=false`; a contagem dos 90 dias NAO foi iniciada; nenhuma
  metrica de desempenho do futuro foi calculada; nenhuma ordem real; nenhum commit.
  Proximo passo (requer decisao explicita do usuario): declaracao de inicio com data
  efetiva e prontidao operacional confirmada.

## 2026-10-23/24 — Declaracao formal de inicio da janela P6-MOM

- **Autorizacao do usuario**: inicio efetivo 2026-10-25T00:00:00Z (24/10 21:00 em
  Recife, UTC-3); encerramento exatamente 90 dias depois: 2027-01-23T00:00:00Z
  (22/01/2027 21:00 em Recife). Data verificada como futura no momento da
  declaracao; nenhuma retroacao.
- **Pre-condicoes verificadas antes de declarar**: registros P6-MOM e P6-MOM-RISK
  ativos no ledger; aprovacao de risco -10% valida (ref
  `memory/p6_mom_risk_approval_ref.json` resolvendo para P6-MOM-RISK; validada
  via `validate_approval` do runner); hashes de todos os arquivos do manifesto
  congelado (`research/out/p6_mom_freeze_20261024T011825Z/manifest.json`, sha256
  661EAA0326B7B4C201E7A897FF58CD45382FB10DDACFECF4F0A6F89DB0B76592) conferindo
  com os arquivos atuais; config e criterios inalterados.
- **Registro**: backup de `memory/hypotheses_ledger.jsonl` e `memory/journal.md`
  em `%LOCALAPPDATA%\Temp\opencode\p6_mom_start_backup_20261023T224333Z\`
  (inclui copia do relatorio do probe); ledger recebeu o registro `P6-MOM-START`
  por append (bytes anteriores preservados); `window_start_authorized=true`
  a partir desta declaracao; schema validado por `tests/test_memory_ledger.py`.
- **Sessao exclusiva**: `data/shadow/p6_mom_mom_tf240_lb96_20261025T000000Z/`
  (identificador `P6MOM-20261025T000000Z`); diretorio novo, nenhum arquivo da
  P5 ou de sessoes antigas reutilizado.
- **Coleta operacional**: passo manual `scripts/p6_mom_step.py` (sha256 registrado
  abaixo) encadeia o coletor publico ja validado (`download_klines.py`, somente
  GET publico, sem credenciais/ordens) e o runner sombra `--protocol P6-MOM`;
  comeca exatamente no minuto apos o ultimo timestamp do `state.json` (ou no
  inicio da janela na primeira execucao), nao preenche lacunas com dados
  historicos, para em `RISK_LIMIT_BREACHED` (rc 3) e nao retroage. Testado no
  modo pre-inicio: recusa com rc 5 sem nenhuma requisicao de rede.
- **Limite operacional honesto**: NAO ha agendador automatico configurado neste
  repositorio; a coleta continua depende de execucao manual do passo (ou de um
  agendador do sistema configurado pelo usuario). Nenhuma tarefa agendada foi
  declarada como existente. Nenhuma ordem real; nenhum endpoint de negociacao;
  nenhum commit.
  SHA256 de scripts/p6_mom_step.py: FB696A9802AB6AFC33F6CFF6C00262E6F96E066B85974C92F88C0C4268EFB071.
