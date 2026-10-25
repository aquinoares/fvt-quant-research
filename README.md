# Convergencia Pai / Filho / Trindade

Robô experimental de geração de sinais para criptomoedas, inicialmente restrito a simulação e testes históricos. Não há execução de ordens reais.

## Conceitos

- **Pai (15 min):** contexto e direção macro.
- **Filho (1 min):** estrutura micro e retração potencial.
- **Energia:** atividade de volume e momentum observados.
- **Trindade:** combinação explícita dos componentes para produzir sinal ou ausência de sinal.

Os cinco modelos são hipóteses testáveis, não garantias de previsão. Bandas estatísticas não são automaticamente atratores de Lorenz; área de volume não demonstra direção; ângulo geométrico não é uma medida invariante de aceleração.

## Skill local de pesquisa

O skill de projeto para Codex e agentes compatíveis fica em `.agents/skills/trader-skill/SKILL.md`. Ele orienta a formular hipóteses, testar sinais de forma causal, declarar custos, validar temporalmente e relatar evidência sem inventar métricas. É adaptado do workflow conceitual `strategy-generate` do [HKUDS/Vibe-Trading](https://github.com/HKUDS/Vibe-Trading/blob/main/agent/src/skills/strategy-generate/SKILL.md), com atribuição em `.agents/skills/trader-skill/UPSTREAM.md`.

A skill é apenas instrução de agente: não instala Vibe-Trading, não conecta corretoras, não envia ordens reais e não autoriza alterar a Trilha B congelada.

## Persistência da Trilha A

O workflow agendado executa o código da branch padrão, mas persiste candles públicos e relatórios gerados na branch dedicada [`learning-state`](https://github.com/aquinoares/fvt-quant-research/tree/learning-state), não em `main`. O painel lê os dados e relatórios dessa branch. O processo não toca na `p6-mom-runtime`. Consulte [docs/LEARNING_STATE_BRANCH.md](docs/LEARNING_STATE_BRANCH.md) para o fluxo e os caminhos exatos.

## Ambiente

Requer Python 3.11 ou superior.

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e .[dev]
.\.venv\Scripts\python.exe -m pytest
```

Se `py -3` não funcionar, use o executável Python instalado no sistema.

## Estrutura

- `Matematica trindade.txt`: arquivo-fonte original do usuário, preservado.
- `docs/referencia/Matematica trindade.txt`: cópia de referência para documentação.
- `src/convergencia/features/`: cinco módulos matemáticos.
- `src/convergencia/signals.py`: regra inicial de convergência.
- `src/convergencia/data.py`: validação de candles OHLCV.
- `src/convergencia/backtest.py`: simulação simplificada com atraso de execução e custos.
- `tests/`: testes matemáticos e temporais.
- `data/raw/`: dados brutos locais.
- `data/processed/`: dados validados ou preparados.
- `reports/`: relatórios de resultados.

## Princípios do backtest

1. Um sinal calculado no fechamento só pode afetar posições a partir da abertura seguinte.
2. Taxas e slippage são parâmetros explícitos.
3. Não ajustar parâmetros usando o período de teste final.
4. Comparar a estratégia completa com referências e ablações dos módulos.
5. Resultados históricos não garantem resultados futuros.