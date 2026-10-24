# Relatório de Pesquisa Quantitativa — Convergencia Pai/Filho/Trindade (FVT)

**Agente:** FVT Quant Research (Projeto 3 Pro)
**Worktree:** `C:\Users\Ewert\orca\workspaces\3 Pro\fvt-quant-research`
**Branch:** `fvt-quant-research` @ `39b4286` (working tree limpa no início)
**Data da execução:** 2026-10-22
**Status:** resultados exploratórios; **nenhuma** afirmação de lucratividade é feita.

> **Veredito em uma linha:** nenhuma das quatro variantes testadas sobrevive aos custos de 30 bps por operação completa, e a variante base sequer é lucrativa **bruta** no período de teste final. O `+29,2%` reportado pelo script original é um artefato de um bug de dupla conversão de sinais, não um resultado da estratégia.

---

## 1. Método

### 1.1 Escopo e restrições respeitadas
- Nenhum arquivo do motor (`src/convergencia/`), do painel HTML, do CSV original (`data/raw/BTCUSDT_1m.csv`) ou dos testes (`tests/`) foi alterado.
- Todo artefato novo ficou em `research/` (scripts) e `research/out/` (números). Os relatórios gerados pelo motor em `reports/` são somente cópias da reprodução.
- Ambiente virtual isolado `.venv` (Python 3.12.4) criado neste worktree; apenas as dependências declaradas em `requirements.txt` foram instaladas (nenhum pacote global).
- Todo número deste relatório tem origem reproduzível: `research/check_csv_integrity.py`, `research/run_research.py` e o JSON `research/out/research_results.json`.

### 1.2 Hipóteses a verificar (derivadas da auditoria; a branch `fvt-math-audit` aponta para o mesmo commit e ainda não tinha achados commitados neste worktree)
1. O CSV é contínuo (1 min sem gaps) e o motor exige isso.
2. A execução é no candle seguinte ao sinal (sem lookahead).
3. O contexto Pai de 15 min só entra após o fechamento da barra de 15 min.
4. A posição é long-only, sem sobreposição, com liquidação final.
5. (Suspeita nova da leitura do código) O `scripts/run_backtest.py` pode estar convertendo eventos duas vezes.

### 1.3 Metodologia corrigida
O contrato real de `convergencia.backtest.run_backtest` é receber **eventos crus** (`1`/`-1`/`0`) e convertê-los internamente em estado-alvo com atraso de um candle. O script original `scripts/run_backtest.py` envia, however, um **alvo de posição já convertido** (`events_to_position_targets`), causando **dupla conversão** (detalhado na Seção 6.1). Toda a pesquisa da Seção 5 usa o caminho **correto**: eventos crus → `run_backtest`.

### 1.4 Separação cronológica (sem otimizar no teste final)
Parâmetros fixados *a priori* (original do motor e uma variante "reduzida" declarada antes de qualquer resultado). Split por linhas, sem embaralhar:

| Período | Início (UTC) | Fim (UTC) | Linhas | Fração |
|---|---|---|---|---|
| Treino | 2026-07-23 01:52 | 2026-09-06 01:51 | 64.800 | 50% |
| Validação | 2026-09-06 01:52 | 2026-09-28 13:51 | 32.400 | 25% |
| Teste final | 2026-09-28 13:52 | 2026-10-21 01:51 | 32.400 | 25% |

As features causais são calculadas **uma única vez** sobre a série completa (warmup consistente) e a posição é zerada em cada fronteira de janela — mesma política dos scripts `ablation_convergencia.py` e `validacao_temporal_convergencia.py` do próprio repositório. O período de teste final **não** foi usado para ajustar parâmetros.

### 1.5 Variantes investigadas
| Variante | Contexto Pai | Config |
|---|---|---|
| `M15_original` | 15 min | motor original (baseline) |
| `M5_original` | 5 min | motor original, só o timeframe do Pai trocado |
| `M15_reduced` | 15 min | janelas ~metade (declarada *a priori*, sem otimização) |
| `M5_reduced` | 5 min | idem |

A config "reduzida" (*a priori*): `parent_fast=10, parent_slow=25, child_fast=5, child_slow=12, fib_lookback=30, atr_window=7, volume_lookback=10, momentum_window=5, regime_window=30`. Limiares de regime e volume iguais aos do original.

A replicação do contexto Pai para qualquer timeframe (`parent_bars` em `research/run_research.py`) foi validada como **byte-a-byte idêntica** ao motor em 15 min (`parent_direction`, `parent_close` e `signal` idênticos), tornando a comparação M5 vs M15 justa (só o timeframe muda).

### 1.6 Cenários de custos
| Rótulo | Taxa/lado | Slippage/lado | Custo por operação completa (ida+volta) |
|---|---|---|---|
| `ZERO` | 0 bps | 0 bps | 0 bps |
| `DEFAULT_30BPS_RT` | 10 bps | 5 bps | **30 bps** (mandato do projeto) |
| `HIGH_50BPS_RT` | 20 bps | 5 bps | 50 bps |
| `EXTREME_100BPS_RT` | 45 bps | 5 bps | 100 bps |

### 1.7 Benchmarks
- **Buy-and-hold** na mesma janela (abertura→abertura), com e sem custo de 2 lados.
- **Sem sinal** (caixa parada) = retorno 0%.

---

## 2. Comandos executados (reprodutíveis)

```powershell
# Estado inicial
git status; git branch --show-current; git log --oneline -5

# Ambiente isolado
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# Verificação de integridade do CSV (somente leitura)
.\.venv\Scripts\python.exe research\check_csv_integrity.py

# Testes existentes (19/19 passam)
.\.venv\Scripts\python.exe -m pytest -v

# Reprodução do backtest original (motor intacto)
.\.venv\Scripts\python.exe scripts\run_backtest.py

# Pesquisa completa (ETAPA 2)
.\.venv\Scripts\python.exe research\run_research.py
```

Versões do ambiente: Python 3.12.4, numpy 2.5.4, pandas 3.1.0, pytest 9.1.1.

---

## 3. Integridade do dataset (ETAPA 1)

`research/out/csv_integrity.json`:

| Verificação | Resultado |
|---|---|
| SHA256 | `604835c55d98319cf6f26516040f6f285e02152b6ee984238c0d3359c2dbde41` (**confere** com a constante auditada nos scripts) |
| Linhas | 129.600 (bate com o intervalo temporal) |
| Período | 2026-07-23 01:52Z → 2026-10-21 01:51Z (~90 dias) |
| Falhas de parse de timestamp | 0 |
| Timestamps duplicados | 0 |
| Saltos/lacunas ≠ 1 min | 0 (série contínua) |
| Monotonia crescente | sim |
| Células OHLCV não finitas / preço ≤ 0 / volume < 0 | 0 / 0 / 0 |
| Violações de faixa OHLC (high < max, low > min) | 0 |
| Barras Pai 15 min incompletas | 2 (bordas parciais; o motor as descarta via `bar_count==15`) |
| **Veredito** | **PASS** |

---

## 4. Reprodução do backtest original (ETAPA 1)

`scripts/run_backtest.py` executa sem erro e emite:

```
Buy signal bars: 88 | exit signal bars: 88
Executed entries: 1 | executed exits: 0
Exposure: 97.19%
Net total return: 29.20%
Max drawdown: -8.55%
Buy-and-hold net estimate: 25.99%
```

**Esses números são internamente contraditórios** (88 compras/saídas no sinal, mas 1 entrada e 0 saídas executadas, com exposição de 97%) e foram rastreados até o bug da Seção 6.1. A reprodução "roda", mas o resultado é inválido como medida da estratégia.

---

## 5. Resultados da pesquisa (ETAPA 2, caminho corrigido)

Todos os valores abaixo vêm de `research/out/research_results.json` (caminho correto: eventos crus → `run_backtest`).

### 5.1 Variante base `M15_original` — período completo (90 dias)

| Métrica | `ZERO` custos | `DEFAULT_30BPS_RT` |
|---|---|---|
| Operações (trades) | 88 | 88 |
| Exposição | 0,781% | 0,781% |
| Retorno **bruto** | **+2,724%** | +2,724% |
| Soma dos custos | 0% | **26,400%** |
| Retorno **líquido** | +2,724% | **−21,130%** |
| Drawdown máximo (líq.) | −2,037% | −21,130% |
| Fator de lucro bruto | 1,515 | 1,515 |
| Fator de lucro líquido | 1,515 | **0,129** |
| Taxa de acerto bruta | 37,5% | 37,5% |
| Taxa de acerto líquida | 37,5% | **8,0%** |
| Duração média / mediana | 11,5 / 9 candles | 11,5 / 9 |
| Retorno médio por trade (bruto / líq.) | +0,031% / +0,031% | +0,031% / **−0,269%** |

**Custo de breakeven (aproximação linear):** ~**3,1 bps por operação completa**. Qualquer custo realista (>3 bps RT, e o mandato pede 30) destrói a pequena vantagem bruta.

### 5.2 Benchmarks — período completo

| | Retorno (líquido @30 bps RT) |
|---|---|
| `M15_original` | **−21,13%** |
| Buy-and-hold (mesma janela, líq.) | **+25,99%** |
| Sem sinal (caixa) | 0,00% |
| Estratégia − Buy-and-hold | **−47,12 p.p.** |

A estratégia perde para buy-and-hold por ~47 pontos percentuais e para a caixa por ~21 p.p.

### 5.3 Resultados por período cronológico — `M15_original`

| Período | Trades | Bruto | Líquido @30bps | PF bruto | PF líq. | Acerto líq. | B&H líq. |
|---|---|---|---|---|---|---|---|
| Treino | 53 | +1,872% | −13,117% | 1,49 | 0,15 | 11% | +21,05% |
| Validação | 21 | +1,057% | −5,118% | 1,96 | 0,17 | 5% | +4,14% |
| **Teste final** | 14 | **−0,219%** | **−4,326%** | **0,32** | **0,00** | **0%** | −0,66% |

A vantagem bruta **some e inverte no teste final** (−0,22% bruto, PF 0,32), antes mesmo dos custos. Em nenhum período o retorno líquido @30 bps é positivo.

### 5.4 M5 vs M15 e Original vs Reduzido (período completo, @30 bps RT)

| Variante | Trades | Exposição | Bruto | Líquido @30bps | PF líq. | Acerto líq. |
|---|---|---|---|---|---|---|
| `M15_original` | 88 | 0,78% | +2,72% | **−21,13%** | 0,13 | 8,0% |
| `M5_original` | 56 | 0,42% | +0,05% | −15,44% | 0,08 | 5,4% |
| `M15_reduced` | 244 | 1,00% | +0,88% | −51,52% | 0,01 | 2,5% |
| `M5_reduced` | 145 | 0,57% | −0,73% | −35,77% | 0,00 | 2,1% |

**Leitura:**
- **M5 vs M15:** trocar o Pai para 5 min **reduz** a vantagem bruta praticamente a zero (+0,05%) e não melhora o líquido. Nenhum timeframe sobrevive.
- **Reduzido vs original:** a config reduzida **aumenta a frequência** de trades (244 vs 88), o que **multiplica o arrasto de custos** e piora o resultado líquido (−51,5% vs −21,1%). Mais sinais não ajudam quando a vantagem por trade é minúscula.
- Nenhuma combinação (timeframe × config) apresenta retorno líquido positivo no período completo.

### 5.5 Sensibilidade a custos maiores — `M15_original` (completo)

| Custo RT | Líquido | PF líq. | Acerto líq. |
|---|---|---|---|
| 0 bps | +2,72% | 1,52 | 37,5% |
| 30 bps | −21,13% | 0,13 | 8,0% |
| 50 bps | −33,88% | 0,06 | 3,4% |
| 100 bps | −57,49% | 0,02 | 2,3% |

O declínio é monótono e rápido: cada +10 bps RT custam ~6–7 p.p. de retorno líquido no período.

### 5.6 Métricas de risco — Sharpe diário (adicionado em 2026-10-22, etapa P1)

Definição (decisão 2 do ciclo, `memory/journal.md`): retornos **diários** do equity com dias em caixa contados como **zero** (calendário completo da janela; dias sem barras herdam o equity anterior), anualização **√365** (BTC negocia 24/7). Origem: chaves `daily_observations`, `sharpe_ratio_daily_mean`, `sharpe_ratio_daily_std` e `sharpe_ratio_annualized` de `research/out/research_results.json`, regenerado em 2026-10-22 **somente com adição dessas chaves** — todas as métricas das seções anteriores permanecem idênticas. **DSR não foi calculado nesta etapa** (P1c adiado: `n_trials` ainda não definido).

| Variante / bloco | Dias (obs.) | Sharpe anual. |
|---|---:|---:|
| `M15_original` ZERO — completo | 90 | **+1,71** |
| `M15_original` ZERO — treino / validação / teste | 45 / 22 / 23 | +1,86 / +3,06 / **−8,76** |
| `M15_original` @30 bps — completo | 90 | **−12,98** |
| `M15_original` @30 bps — treino / validação / teste | 45 / 22 / 23 | −15,19 / −10,37 / −10,59 |
| `M5_original` @30 bps — completo | 90 | −12,03 |
| `M15_reduced` @30 bps — completo | 90 | −27,64 |
| `M5_reduced` @30 bps — completo | 90 | −23,52 |

**Leitura:** mesmo **sem custos**, o Sharpe anualizado da variante base é modesto no período completo (+1,71) e **inverte fortemente no teste final** (−8,76 — pouca dispersão porque o equity fica quase plano e negativo). Com os custos mandatados de 30 bps, todos os blocos ficam entre −10 e −28, reforçando a conclusão da Seção 7 sem qualquer otimização e sem uso do teste final para escolha.

---

## 6. Problemas encontrados

### 6.1 BUG CRÍTICO — Dupla conversão de sinais em `scripts/run_backtest.py` (linhas 22–43 e 70)
O contrato de `run_backtest` é **eventos** (`1`=comprar, `-1`=sair, `0`=manter); a função converte eventos em estado-alvo internamente (laço `estado`, linhas 33–41 de `backtest.py`). Porém, `scripts/run_backtest.py` chama **antes** `events_to_position_targets()` (que já transforma a sequência em estado-alvo 0/1) e passa esse **alvo** como se fosse evento.

Consequência: a saída `-1` é gravada como `0` no array entregue; o laço interno de `run_backtest` lê `0` como "manter estado" e **nunca sai**. O comentário no wrapper ("run_backtest recebe posição-alvo, não eventos") está factualmente errado.

Efeito medido (mesmos dados, mesmos custos 30 bps RT):

| Caminho | Entradas | Saídas | Exposição | Retorno líquido | Max DD |
|---|---|---|---|---|---|
| **Bugado** (script original) | 1 | 0 | 97,19% | **+29,20%** | −8,55% |
| **Correto** (eventos crus) | 88 | 88 | 0,78% | **−21,13%** | −21,13% |

O `+29,2%` nada tem a ver com a Trindade: é essencialmente buy-and-hold com atraso de ~2 dias (entrou na 1ª compra em 2026-07-25 14:36Z e nunca mais saiu), o que explica a proximidade com o buy-and-hold de +26%. **Qualquer conclusão anterior baseada nesse script está contaminada.**

**Recomendação (fora do escopo de edição desta etapa):** remover `events_to_position_targets` do script e passar `enriched["signal"]` diretamente a `run_backtest`; ou, se o wrapper for mantido, `run_backtest` precisaria de um modo que aceite estado-alvo — mas o motor não deve ser alterado sem revisão.

### 6.2 Liquidação final — CORRIGIDO: o motor JÁ cobra o custo (errata)
> **ERRATA (etapa de correção).** A versão inicial deste relatório alegava, nesta seção, que a liquidação final obrigatória era "grátis" (viés de 15 bps a favor da estratégia). **Isso está errado.** Verificação direta (e teste `test_final_forced_liquidation_cost_is_charged`) mostra que o motor **cobra** corretamente esse custo.

Mecanismo real: `run_backtest` força `position.iloc[-1] = 0` para liquidar a posição aberta. O `turnover` dessa última linha é puxado por `costs = turnover.shift(-1)` para a **penúltima linha**, que é **retida** no resultado (só a última linha original é descartada por `next_open_return.notna()`). Logo, o custo da liquidação **não se perde**.

Evidência (custos 10 bps taxa + 5 bps slippage = 15 bps/lado):
- Posição **aberta** no fim (eventos `[1,0,0,0]`): `total costs = 0,003 = entrada (0,0015) + liquidação (0,0015)`. Liquidação **cobrada**.
- Posição já **fechada** no fim (evento de saída antes do fim; caso do dataset real com `entries==exits==88`): `position.iloc[-1]=0` é no-op e não há custo extra — corretamente.

O check `final_forced_liquidation_cost_charged = False` da versão inicial media, na verdade, uma posição **já flat** no dataset real (o último trade fecha antes do fim), não uma liquidação não cobrada. **Nenhuma alteração em `src/` é necessária; o motor está correto.**

> **Sincronização (etapa de auditoria):** o `research/run_research.py` foi corrigido para separar os casos e o `research/out/research_results.json` foi regenerado. As chaves antigas `final_forced_liquidation_cost_charged` / `final_liquidation_cost_is_free_bias_bps` foram substituídas por `final_position_signal_open_at_end = false` (dataset real termina plano), `final_forced_liquidation_cost_charged_when_open = true` (motor cobra quando há posição aberta) e `final_liquidation_cost_free_bias_bps = 0.0` (sem viés). Nenhuma métrica de pesquisa foi alterada — apenas os rótulos do check.

### 6.3 Achados de causalidade — todos PASSAM
| Verificação | Resultado |
|---|---|
| Posição = 0 na mesma barra do sinal de compra (execução adiada) | ✅ |
| Posição = 1 na barra seguinte à compra | ✅ |
| Posição restrita a {0,1} (long-only, sem short) | ✅ |
| Eventos alternam (compra/saída), sem sobreposição | ✅ |
| Perturbar os 5 candles finais não muda features/sinais passados (anti-lookahead) | ✅ |
| Liquidação final cobrada (pos. aberta no fim) | ✅ (já correta; ver errata 6.2) |

A semântica de execução no candle seguinte, a unicidade da posição e a ausência de lookahead estão confirmadas. O motor `src/convergencia/backtest.py` e `strategy.py` estão causalmente corretos; o defeito está no **script** de execução, não no motor.

### 6.4 Testes existentes
19/19 testes passam no ambiente isolado. Note-se que nenhum teste cobre `scripts/run_backtest.py` (o teste `test_backtest_delays_signal...` chama `run_backtest` corretamente com eventos crus, por isso o bug do wrapper passou despercebido).

---

## 7. Conclusão — alguma estratégia sobrevive aos custos e ao teste temporal?

**Não. Nenhuma.**

1. **Não sobrevive aos custos de 30 bps/operacao completa:** a melhor variante (`M15_original`) perde **−21,13%** no período completo e **−4,33%** no teste final; as demais perdem ainda mais (−15,4% a −51,5%).
2. **Não sobrevive ao teste temporal:** a vantagem bruta da variante base é **negativa no teste final** (−0,22%, PF 0,32), antes de qualquer custo. A "lucratividade" do treino não se mantém fora do treino.
3. **Não supera benchmarks:** perde para buy-and-hold (+25,99% líq.) por ~47 p.p. e para a caixa (0%) por ~21 p.p. no período completo.
4. **O resultado positivo original é um bug** (Seção 6.1), não evidência de edge.

O único número positivo em toda a matriz é o retorno **bruto** da variante base no período completo (+2,72%, PF 1,52) — mas ele exige custos abaixo de ~3 bps RT para virar líquido (inviable com o mandato de 30 bps) e já é negativo no holdout. **Isso não constitui lucratividade verificável.**

---

## 8. Próximos experimentos (sugestões, ainda não executados)

1. **Corrigir o wrapper de sinais** em `scripts/run_backtest.py` (remover `events_to_position_targets`) e propagar a correção aos scripts derivados (`ablation_convergencia.py`, `validacao_temporal_convergencia.py` já usam o caminho correto).
2. **Cobrir o caminho de execução com teste de regressão** (nº de entradas == nº de compras; exposição baixa) para impedir que o bug de dupla conversão volte.
3. ~~Cobrar o custo da liquidação final~~ — **removido**: verificado que o motor já cobra corretamente (errata 6.2); nenhuma ação necessária.
4. **Walk-forward genuíno** com dados de 2025/2026 anteriores ou de outro ativo, para testar se o pequeno edge bruto (+2,7%) é estável fora desta única amostra de 90 dias — hoje ele já é negativo no holdout interno.
5. Se perseguir sinal, atacar a **relação vantagem/custo**: a vantagem média por trade é +0,031% (3,1 bps), enquanto o custo mandatado é 30 bps RT. Só faz sentido se o custo efetivo cair ~10× ou a vantagem por trade subir ~10×; nada nas variantes testadas alcançou isso.
6. Manter o protocolo de **não tocar no teste final** para ajustes; qualquer nova hipótese deve ser declarada *a priori* e avaliada nos splits existentes.

---

## 9. Artefatos

| Arquivo | Conteúdo |
|---|---|
| `research/check_csv_integrity.py` | Verificação de integridade/continuidade do CSV |
| `research/out/csv_integrity.json` | Resultado da integridade (PASS) |
| `research/run_research.py` | Script completo da ETAPA 2 (reprodutível) |
| `research/out/research_results.json` | Todas as métricas, benchmarks, splits, variantes e cenários |
| `reports/backtest_*_20261022T125117Z.*` | Reprodução do backtest original (motor intacto; resultado contaminado pelo bug 6.1) |
| `research/RESEARCH_REPORT.md` | Este relatório |

Nenhuma ordem real foi enviada; nenhum arquivo do motor, painel, CSV original ou testes foi modificado.

---

## 10. Addendum — etapa de correção (pós-pesquisa)

Após esta pesquisa, o bug de dupla conversão da Seção 6.1 foi **corrigido** em `scripts/run_backtest.py` (removido o wrapper `events_to_position_targets`; os eventos crus são passados diretamente a `run_backtest`, conforme o contrato do motor). Efeito:

| Métrica (script `run_backtest.py`, custos 30 bps RT) | Antes (bugado) | Depois (corrigido) |
|---|---|---|
| Executed entries / exits | 1 / 0 | **88 / 88** |
| Exposição | 97,19% | **0,78%** |
| Retorno líquido | +29,20% | **−21,13%** |
| Max drawdown | −8,55% | **−21,13%** |

O resultado corrigido (`−21,13%`) **bate exatamente** com o caminho correto da Seção 5.1, confirmando que a pesquisa já usava o comportamento correto.

Adicionado `tests/test_run_backtest_regression.py` (5 testes) que travam: o contrato de eventos do motor, o fechamento de posição no meio da série, a assinatura do bug (para não voltar), o fechamento de toda trade ponta a ponta no script, e o custo de liquidação final. **Errata:** a Seção 6.2 original (liquidação "grátis") estava **errada** — o motor já cobra esse custo (corrigido acima; ver `test_final_forced_liquidation_cost_is_charged`). Nenhuma alteração em `src/` foi necessária. Suite final: **24/24 testes passam**.
