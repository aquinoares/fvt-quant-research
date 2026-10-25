# RASCUNHO — EMENDA AO PROTOCOLO P6-MOM

> **RASCUNHO — SEM EFEITO ATÉ APROVAÇÃO HUMANA.** Este documento não altera a sessão, a janela, a tolerância, a regra de continuidade, a estratégia, seus parâmetros ou o manifesto congelado. Não reinicia nem autoriza coleta, preenchimento retroativo ou retomada automática. Nenhuma opção está selecionada.

## 1. Incidente e evidências observáveis

- **Sessão:** P6-MOM / MOM_TF240_LB96 / BTCUSDT, modo sombra.
- **Início original da janela registrada:** 2026-10-25 00:00:00 UTC (2026-10-24 21:00:00 em Brasília).
- **Evento persistido:** `PROTOCOL_STOP_INITIAL_SCHEDULER_GAP`.
- **Horário do evento:** 2026-10-25 00:48:13.150235 UTC; 2026-10-24 21:48:13.150235 em Brasília.
- **Evidência literal do feed:** “First cloud collection would begin 2893 seconds after window start; no retrospective backfill was attempted.”
- **Atraso registrado:** 2.893 s. **Tolerância aplicável registrada no protocolo:** 2.700 s (45 min). O atraso excedeu a tolerância em 193 s.
- **Run do coletor:** [GitHub Actions #40148089650](https://github.com/aquinoares/fvt-quant-research/actions/runs/40148089650). O run reportou conclusão de workflow `success`, mas o estado operacional persistido da sessão foi `protocol_stopped`; conclusão verde do workflow não valida a sessão.
- **Commit do coletor informado no run:** [`b692272f862dc63f3691376191e024d1f8d0938e`](https://github.com/aquinoares/fvt-quant-research/commit/b692272f862dc63f3691376191e024d1f8d0938e).
- **Run que produziu o snapshot de evidência do painel:** [FVT Dashboard #40148137316](https://github.com/aquinoares/fvt-quant-research/actions/runs/40148137316).
- **Snapshot:** 2026-10-25 00:48:42.964385 UTC; 2026-10-24 21:48:42.964385 em Brasília.
- **Commit do painel registrado na revisão:** `728554f917f0cffeb9db576b3be9af0804142813`.
- **SHA-256 do manifesto congelado registrado no ledger:** `661EAA0326B7B4C201E7A897FF58CD45382FB10DDACFECF4F0A6F89DB0B76592`.
- **Estado no snapshot:** `protocol_stopped`; evento de parada registrado; candle/último timestamp, candles e lacunas nas últimas 48 h, posição, entrada, drawdown prospectivo e demais métricas da sessão não estão disponíveis no feed (campos nulos/ausentes).

### Declaração limitada às evidências persistidas

No snapshot e no estado persistido consultados, **nenhum dado de estratégia da sessão consta observado antes da decisão humana**: o último candle, a contagem de candles, a posição, o preço/horário de entrada e o drawdown prospectivo não têm valor disponível. Esta declaração descreve exclusivamente os registros persistidos examinados; não é uma afirmação sobre dados externos que não estejam nesses registros. O incidente permanece sem decisão humana registrada.

## 2. Opções para decisão do responsável — nenhuma pré-selecionada

### OPÇÃO 1 — Manter a janela original como “falhou na partida” e registrar

Proposta a ser avaliada pelo responsável: preservar a janela original e seu histórico imutável, classificar a partida como falha operacional e registrar o incidente sem retomada nem preenchimento retroativo.

**Riscos/efeitos a considerar:**
- A janela não produzirá uma avaliação prospectiva válida se a coleta não foi iniciada dentro das condições autorizadas.
- Não haverá base para concluir desempenho prospectivo dessa janela; ausência de dados não é resultado positivo nem negativo da estratégia.
- É necessário evitar que a conclusão `success` do workflow seja confundida com validade da sessão.

**Seleção da opção 1:** ☐ Não selecionada / pendente de decisão humana.

### OPÇÃO 2 — Considerar uma nova data de início futura, mediante autorização separada

Esta opção exigiria uma decisão explícita e uma autorização formal separada antes de qualquer nova sessão. Os campos abaixo ficam intencionalmente em branco:

- **Nova data/hora de início (UTC):** __________________________________
- **Tolerância autorizada para início/continuidade:** _____________________
- **Regra para preenchimento de lacunas usando API pública:**  
  ____________________________________________________________________  
  ____________________________________________________________________
- **Data/hora UTC da assinatura da autorização:** _________________________

**Riscos/efeitos a considerar:**
- Uma nova data altera o período prospectivo e reduz a comparabilidade direta com a janela original.
- Alterar regras depois de observar o incidente pode introduzir viés de decisão retrospectiva e seleção de condições mais convenientes.
- Uma regra de preenchimento via API pública pode introduzir diferenças de revisão, timestamps, duplicatas ou continuidade artificial; qualquer uso precisaria ser especificado e aprovado antes, nunca aplicado retroativamente a esta sessão.
- Esta minuta, por si só, não autoriza nova coleta nem altera o protocolo existente.

**Seleção da opção 2:** ☐ Não selecionada / pendente de decisão humana.

## 3. Decisão humana e trilha de auditoria

- **Opção escolhida (1 ou 2):** _________________________________________
- **Justificativa do responsável:**  
  ____________________________________________________________________  
  ____________________________________________________________________
- **Data/hora UTC da decisão:** _________________________________________
- **Nome/identificação do responsável:** _________________________________
- **Assinatura ou commit de aprovação do responsável:** ___________________
- **Referência do registro de aprovação:** _______________________________

**Até que esses campos sejam preenchidos e a aprovação humana seja registrada, a decisão permanece pendente.** Este rascunho não escolhe a opção, não completa os campos em branco e não autoriza retomada automática.

## 4. Guardas que permanecem inalteradas nesta minuta

Não alterar a estratégia P6-MOM, parâmetros, manifesto congelado, janela original, limite de risco, tolerância existente ou workflow **P6-MOM Cloud Shadow Live**. Não reiniciar a sessão, não preencher a lacuna retroativamente e não editar o snapshot nem o histórico do incidente. Métrica sem dado permanece “—” com o motivo. GitHub Pages permanece desligado por padrão.
