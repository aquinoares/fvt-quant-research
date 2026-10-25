"""Testes de regressão para a execução do backtest (caminho de sinais e liquidação).

Motivação: o script ``scripts/run_backtest.py`` já converteu eventos em estado-alvo
antes de chamar ``run_backtest`` (dupla conversão). Como o motor espera EVENTOS crus
(1/-1/0) e converte internamente, a saída ``-1`` virava ``0`` e o motor, lendo ``0``
como "manter estado", nunca encerrava a posição — artefato de +29% com 97% de
exposição (ver ``research/RESEARCH_REPORT.md``, Seção 6.1).

Estes testes travam o contrato correto para que o bug não volte.
"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pandas as pd
import pytest

from convergencia.backtest import run_backtest

ROOT = Path(__file__).resolve().parents[1]


def _candles(n: int = 7) -> pd.DataFrame:
    return pd.DataFrame({"open": [100.0, 100.0, 110.0, 110.0, 105.0, 105.0, 105.0][:n]})


def test_engine_exit_event_closes_position_midseries():
    """Uma sequência compra→saída DEVE encerrar a posição no meio da série.

    Regressão do contrato: ``run_backtest`` recebe EVENTOS crus e o ``-1`` fecha
    a posição. Se alguém reintroduzir pre-conversão em alvo (0/1), o ``-1``
    desaparece e a posição fica presa comprada — este teste falharia em espírito
    (aqui testamos o motor; o teste de integridade do script cobre o ponto de
    chamada).
    """
    events = [1, 0, -1, 0, 0, 0, 0]  # compra no 0, saída no 2, plano depois
    bt = run_backtest(_candles(), events, fee_bps=0.0, slippage_bps=0.0)
    pos = bt["position"].tolist()
    # Após a saída (linha 2), a posição deve voltar a 0 e permanecer 0.
    assert 0.0 in pos[2:], f"posicao nunca encerrou apos a saida: {pos}"
    assert all(p == 0.0 for p in pos[3:]), f"posicao reabriu indevidamente apos saida: {pos}"
    # Long-only: nunca negativa.
    assert set(bt["position"].unique()).issubset({0.0, 1.0})


def test_engine_double_conversion_exhibits_stuck_long_signature():
    """Caracteriza a assinatura do BUG para documentá-lo (não é o comportamento desejado).

    Passar um estado-alvo pré-convertido (o antigo ``events_to_position_targets``)
    como se fosse evento faz o motor ler ``0`` como "manter estado" e nunca encerrar.
    Este teste preserva a evidência do bug e falharia se o motor mudasse de contrato.
    """
    events = [1, 0, -1, 0, 0, 0, 0]
    targets = [1, 1, 0, 0, 0, 0, 0]  # estado-alvo pré-convertido (o que o script fazia)
    bt_events = run_backtest(_candles(), events, fee_bps=0.0, slippage_bps=0.0)
    bt_targets = run_backtest(_candles(), targets, fee_bps=0.0, slippage_bps=0.0)
    # Com eventos crus, a posição encerra (volta a 0) no meio.
    assert 0.0 in bt_events["position"].tolist()[2:]
    # Com alvo pré-convertido, a posição fica presa comprada até a última barra.
    assert all(p == 1.0 for p in bt_targets["position"].tolist()[1:-1])


def test_script_run_backtest_closes_every_trade(monkeypatch):
    """Guarda de regressão ponta a ponta do SCRIPT: toda compra tem saída e a
    exposição é baixa. Falha sob o bug de dupla conversão (entries=1, exits=0,
    exposição≈97%); passa com o caminho corrigido (entries=exits=88, ≈0,78%).
    """
    csv_path = ROOT / "data" / "raw" / "BTCUSDT_1m.csv"
    if not csv_path.is_file():
        pytest.skip("CSV histórico ausente")
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "run_backtest.py"),
         "--input", str(csv_path), "--symbol", "REGRESSION"],
        capture_output=True, text=True, cwd=str(ROOT), timeout=600,
    )
    assert proc.returncode == 0, f"script falhou:\n{proc.stdout}\n{proc.stderr}"
    # Localizar o summary JSON gerado (último com o símbolo REGRESSION).
    summaries = sorted((ROOT / "reports").glob("backtest_summary_REGRESSION_1m_*.json"))
    assert summaries, "summary JSON do script não encontrado"
    summary = json.loads(summaries[-1].read_text(encoding="utf-8"))
    # Invariantes estruturais do caminho corrigido.
    assert summary["buy_signal_bars"] > 1
    assert summary["executed_entries"] == summary["buy_signal_bars"], (
        "entries != buys: sinal de dupla conversão (saídas engolidas)"
    )
    assert summary["executed_exits_in_return_series"] == summary["exit_signal_bars"], (
        "exits != exit signals: saídas não executadas"
    )
    assert summary["exposure_fraction"] < 0.05, (
        f"exposição anormalmente alta ({summary['exposure_fraction']:.2%}): posição presa"
    )
    # Limpeza dos artefatos gerados pelo teste (reports/ é scratch, mas evitamos lixo).
    for pattern in ("backtest_summary_REGRESSION_1m_*.json",
                    "backtest_REGRESSION_1m_*.csv",
                    "signals_REGRESSION_1m_*.csv"):
        for f in (ROOT / "reports").glob(pattern):
            try:
                f.unlink()
            except OSError:
                pass


def test_final_forced_liquidation_cost_is_charged():
    """Trava o comportamento CORRETO do motor: a liquidação final obrigatória é COBRADA.

    O turnover da última linha (forçado por ``position.iloc[-1] = 0``) é puxado por
    ``costs = turnover.shift(-1)`` para a penúltima linha, que é RETIDA no resultado
    (só a última linha original é descartada por ``next_open_return.notna()``).
    Portanto o custo da liquidação NÃO se perde.

    Nota: um relatório anterior (research/RESEARCH_REPORT.md, Seção 6.2, agora
    corrigida) alegava erroneamente que essa liquidação era "grátis". Este teste
    documenta o comportamento real e impede regressões futuras.
    """
    # 4 candles; posição ABERTA no fim (último evento é compra, sem saída).
    candles = pd.DataFrame({"open": [100.0, 100.0, 110.0, 110.0]})
    events = [1, 0, 0, 0]  # compra no candle 0 e nunca sai
    fee_bps, slip_bps = 10.0, 5.0
    cost_rate = (fee_bps + slip_bps) / 10_000.0  # 0.0015 = 15 bps por lado
    bt = run_backtest(candles, events, fee_bps=fee_bps, slippage_bps=slip_bps)
    # A entrada é cobrada (turnover da linha 1 deslocado para a linha 0).
    assert bt["costs"].iloc[0] == pytest.approx(cost_rate)
    # A LIQUIDAÇÃO FINAL também é cobrada (turnover da última linha deslocado
    # para a penúltima linha RETIDA). Total = entrada + liquidação = 2 lados.
    total_costs = float(bt["costs"].sum())
    assert total_costs == pytest.approx(2.0 * cost_rate), (
        f"liquidação final não cobrada (total={total_costs}, esperado={2.0 * cost_rate}): "
        "o custo da posição aberta no fim deve ser debitado"
    )


def test_final_flat_position_charges_no_liquidation():
    """Quando a posição já termina FECHADA (sai antes do fim), não há liquidação a cobrar.

    Cobre o caso do dataset real (entries==exits): ``position.iloc[-1] = 0`` é no-op
    e nenhum custo extra de liquidação é incorrido.
    """
    # 7 candles; SAÍDA no candle 2 e depois plano até o fim (plano visível nas linhas retidas).
    candles = _candles(7)
    events = [1, 0, -1, 0, 0, 0, 0]  # compra no 0, saída no 2, plano depois
    fee_bps, slip_bps = 10.0, 5.0
    cost_rate = (fee_bps + slip_bps) / 10_000.0
    bt = run_backtest(candles, events, fee_bps=fee_bps, slippage_bps=slip_bps)
    assert bt["position"].iloc[-1] == 0.0  # termina plano (nada a liquidar)
    # Entrada (linha 0) + saída (linha 2) = 2 lados; NÃO há liquidação extra no fim.
    assert float(bt["costs"].sum()) == pytest.approx(2.0 * cost_rate)
