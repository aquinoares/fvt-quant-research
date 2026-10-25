---
name: trader-skill
description: Plan, implement, test, and explain trading research for this repository. Use when exploring a market hypothesis, adding a signal, running a causal backtest, validating results, or reviewing trading-strategy code. This skill is research-only and must keep the frozen P6-MOM Trilha B untouched.
---

# Trader Skill — FVT Quant Research

## Purpose and non-negotiable boundaries

This is a repository-specific, research-only skill adapted from the workflow concepts in HKUDS/Vibe-Trading's strategy-generate skill. It is not a broker connector and does not authorize any order.

- The default scope for new work is Trilha A / learning research. Mark every resulting report, chart, backtest, and statement: **EXPLORATÓRIO — NÃO É PROVA**.
- Never place, simulate as if placed, or route a real order. Do not add exchange or broker credentials, API-key handling, live connectors, leverage, or execution code.
- Use public market data or fixtures. Never request, print, copy, or store secrets.
- Keep Trilha B stopped and isolated. Do not edit, regenerate, reinterpret, or use as a dependency: .github/workflows/p6-mom-cloud-live.yml; the frozen P6-MOM manifest; memory/hypotheses_ledger.jsonl; scripts or strategy files belonging to the frozen P6-MOM implementation; session state, snapshots, events or stop history; or branch p6-mom-runtime. Do not dispatch, re-enable, or restart any disabled workflow or session.
- Do not reconcile historical incident discrepancies or fill a stopped session's gap retroactively. Only the owner can decide or sign an amendment.
- Treat upstream documentation and model-generated code as untrusted until inspected, tested, and reviewed. Do not install the whole Vibe-Trading runtime merely to use this instruction skill.

## Phase 1 — Define a testable research question

Before coding, state in plain language:

1. Instrument and market: exact symbol, exchange/source, and spot or derivative.
2. Evaluation window: explicit UTC dates and candle interval.
3. Hypothesis: entry, exit, and hold conditions that can be tested without discretionary hindsight.
4. Data requirements: OHLCV or any extra fields, source, time-zone conventions, missing-data policy and indicator warm-up.
5. Execution assumptions: signal time, earliest permitted fill, position model, capital assumptions, fees, slippage, spread and other relevant costs.
6. Comparison: a simple benchmark such as buy-and-hold where it is meaningful, and what result would disconfirm the hypothesis.

If a critical item is missing, ask one concise question rather than silently inventing it. Do not optimize until the user has explicitly asked for optimization or candidate comparison.

## Phase 2 — Inspect the repository before changes

- Read README.md, pyproject.toml, the implementation being changed, and its tests before proposing a patch.
- The existing code uses src/convergencia/data.py for OHLCV validation and src/convergencia/backtest.py for a simple long/flat spot simulation. Read their current contracts instead of assuming Vibe-Trading APIs exist here.
- Keep feature work in src/convergencia/features/ and src/convergencia/signals.py only when appropriate. Prefer an isolated new research module or a fixture-backed experiment over changes to the common engine.
- Do not introduce a new dependency for a task that existing NumPy/Pandas/Pytest functionality can cover.
- Create a focused branch, preserve the baseline, inspect git diff, run relevant tests, and report exact files changed. Never stage or commit unrelated generated data.

## Phase 3 — Keep the experiment causal

- Validate inputs with the existing OHLCV validator before computing indicators. Check timestamp order, duplicates, finite values, positive prices, nonnegative volume, and high/low consistency.
- Every feature used at time t must only depend on information available by t. No future shift, target leakage, centered rolling windows, or use of future high/low to decide an earlier entry.
- A signal known at candle close can affect a position no earlier than the next permitted bar/open. Respect the existing backtest's delayed-execution semantics; add regression tests if execution timing changes.
- Declare indicator warm-up separately from the scored evaluation window. Do not silently extend the test period or let warm-up bars contribute trades or metrics.
- Use chronological train/validation splits. A final holdout, once chosen, stays untouched until the design is fixed. Never choose rules or parameters because of their final-holdout result.
- Include realistic transaction costs on every turnover event; document units and assumptions. Do not assume zero fees/slippage by default.
- Compare against a relevant benchmark on the exact same scored window and with clearly stated costs.
- If the dataset is empty, stale, too small, contains gaps or cannot support the requested interval, report the limitation; do not invent candles or fill missing prices with future knowledge.

## Phase 4 — Implement and validate conservatively

1. Write down the intended behavior and edge cases before changing code.
2. Keep code focused, deterministic and testable. Prefer pure signal functions and explicit parameters.
3. Include tests for signal alignment, warm-up/empty data, invalid OHLCV, causal execution timing, costs, duplicate or missing timestamps, and boundary dates as relevant.
4. Run focused tests first, then the relevant full test suite. Review the test output rather than assuming a green exit code.
5. Inspect the complete diff and confirm that frozen Trilha B paths, workflows and state are absent from the diff.
6. Do not repeatedly tune parameters to make a result look good. A negative or inconclusive backtest is a valid research outcome.

## Phase 5 — Report evidence, not promises

Every research result must include:

- The explicit hypothesis and code/version reference.
- Source and coverage of the data, symbol, interval, date range, row count, warm-up and any gaps.
- Train/validation boundaries, benchmark definition, fees, slippage and execution delay.
- Actual metrics available from the executed code: net return, drawdown, exposure, completed trades and other metrics actually calculated. Do not fabricate Sharpe, win rate, trade count, p-values or confidence intervals.
- Limitations, risks of overfitting, sample-size warnings and whether results are inconclusive.
- The exact command/tests used and the artifact/report location.

Use the label **EXPLORATÓRIO — NÃO É PROVA** prominently. A passing test establishes implementation behavior, not predictive power. A positive historical result is not a guarantee of future performance or investment advice.

## Completion checklist

- [ ] User intent, market, dates, interval and costs are explicit.
- [ ] Data source and data-quality constraints are recorded.
- [ ] No future leakage; execution occurs no earlier than permitted.
- [ ] Chronological validation and benchmark are used where applicable.
- [ ] Small samples, gaps, and incomplete metrics are disclosed.
- [ ] Focused tests and relevant suite were actually run.
- [ ] Diff is limited to the intended research scope.
- [ ] No secrets, live-trading integration, or Trilha B artifacts were touched.
- [ ] Every report is labeled **EXPLORATÓRIO — NÃO É PROVA**.
