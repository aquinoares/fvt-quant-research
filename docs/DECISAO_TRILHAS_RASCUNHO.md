# RASCUNHO — SEM EFEITO ATÉ ASSINATURA DO RESPONSÁVEL

**Status:** rascunho de registro. Não é emenda, autorização de retomada nem escolha assinada. Nenhuma caixa está marcada e nenhum campo de decisão foi preenchido por esta mudança.

## 1. Fatos registrados

- Incidente: PROTOCOL_STOP_INITIAL_SCHEDULER_GAP.
- Execução relacionada: [run #40148089650](https://github.com/aquinoares/fvt-quant-research/actions/runs/40148089650).
- Atraso registrado: 2.893 segundos.
- Tolerância registrada: 2.700 segundos.
- Diferença além da tolerância: 193 segundos.
- O workflow foi desabilitado em 2026-10-25T00:48:14Z.
- O evento permanece como registro histórico. Esta proposta não reinicia sessão, não reconstrói backfill retroativo e não edita o histórico do incidente.
- A análise anterior identificou divergência não reconciliada: window_start_authorized aparece como false em um registro e true no outro entre manifesto e ledger. A divergência continua pendente; este rascunho não decide qual prevalece.
- O workflow de coleta da Trilha B permanece parado. Não foi reabilitado, despachado ou alterado por esta proposta.

## 2. Diagnóstico — estimativas, não fatos observados

Uma projeção diagnóstica anterior estimou aproximadamente 9,33 operações em 90 dias e aproximadamente 46% de chance de alcançar 10 operações, usando uma simplificação de Poisson. É aproximação matemática, não métrica observada, garantia ou critério para mudar parâmetros.

A espera por um servidor por um mês, por si só, não justifica calibrar os parâmetros congelados da P6-MOM. A Trilha A abaixo é apenas coleta e estudo exploratório independente.

## 3. Declaração proposta — precisa ser confirmada pelo responsável

Texto proposto para leitura e confirmação, ainda sem efeito:

> “aceitar o incidente como falha de partida; manter a trilha B parada; estudar na trilha A; planejar nova janela da B em servidor, em data futura a definir”

Este texto não foi assinado, não significa que uma nova janela esteja autorizada e não substitui qualquer procedimento formal do responsável.

## 4. Campos em branco — preencher somente após decisão humana

- Data/hora UTC da decisão: ______________________________
- Nova data/hora UTC de início, se autorizada: ______________________________
- Tolerância de atraso, se autorizada: ______________________________
- Regra de backfill, se autorizada: ______________________________
- Duração da janela, se autorizada: ______________________________
- Método comparador buy-and-hold, se autorizado: ______________________________
- Decisão do responsável / exceções: ______________________________
- Nome e assinatura do responsável: ______________________________
- Hash/commit do registro final assinado: ______________________________

## 5. Separação entre as trilhas

- **Trilha A:** candles BTCUSDT públicos, qualidade de dados, backfill e experimentos didáticos. Todo resultado marcado “EXPLORATÓRIO — NÃO É PROVA”.
- **Trilha B:** parada, congelada e sem alterações. Parâmetros, manifesto, ledger, estratégia e estado da sessão não são importados nem modificados pela Trilha A.

## 6. Gate de segurança do repositório

A visibilidade do repositório foi definida pelo responsável como **pública**. Antes de qualquer decisão separada de publicação, o responsável executará Gitleaks localmente sobre todas as refs/histórico, resolverá eventual segredo encontrado por revogação e avaliará divulgação de pesquisa/IP. Este PR não muda visibilidade e não executa a Fase 4.
