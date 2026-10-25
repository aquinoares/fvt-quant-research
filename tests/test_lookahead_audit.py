"""Testes sinteticos do detector de look-ahead bias (sem dados reais).

Cobrem: pipeline real em dados sinteticos com indicadores causais (passa),
exemplos deliberados de uso do futuro (detectados), regras de classificacao
BORDA/REAL/INCONCLUSIVO, tolerancia numerica e igualdade exata de discretos.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import research.check_lookahead_bias as la  # noqa: E402


def _synthetic_candles(n: int = 3000, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    start = pd.Timestamp("2026-01-05T00:00:00Z")
    ts = pd.date_range(start, periods=n, freq="min")
    rets = rng.normal(0.0, 0.0007, n)
    close = 50_000.0 * np.exp(np.cumsum(rets))
    open_ = np.concatenate([[close[0]], close[:-1]])
    high = np.maximum(open_, close) * (1.0 + np.abs(rng.normal(0.0, 0.0003, n)))
    low = np.minimum(open_, close) * (1.0 - np.abs(rng.normal(0.0, 0.0003, n)))
    volume = rng.uniform(1.0, 10.0, n)
    return pd.DataFrame({
        "timestamp": [t.strftime("%Y-%m-%dT%H:%M:%S+0000") for t in ts],
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
        "quote_volume": close * volume,
    })


@pytest.fixture(scope="module")
def frames() -> dict:
    candles = _synthetic_candles(3000)
    cut25 = int(len(candles) * 0.25)
    cut50 = int(len(candles) * 0.50)
    reference = la.compute_features(candles)
    prefix25 = la.compute_features(candles.iloc[:cut25].reset_index(drop=True))
    prefix50 = la.compute_features(candles.iloc[:cut50].reset_index(drop=True))
    return {
        "candles": candles,
        "cut25": cut25,
        "cut50": cut50,
        "reference": reference,
        "prefix25": prefix25,
        "prefix50": prefix50,
    }


def test_pipeline_real_causal_passa_nos_prefixos(frames: dict) -> None:
    reference = frames["reference"]
    records: list[dict] = []
    for cut, prefix in (
        (frames["cut25"], frames["prefix25"]),
        (frames["cut50"], frames["prefix50"]),
    ):
        records.extend(
            la.compare_frames(reference, prefix, cut / len(frames["candles"]), cut)
        )
        ref_signal = reference["signal"].iloc[:cut].to_numpy()
        pref_signal = prefix["signal"].to_numpy()
        keep = cut - la.TAIL_WINDOW_ROWS
        assert (ref_signal[:keep] == pref_signal[:keep]).all(), (
            "sinal discreto divergiu fora da janela de borda"
        )
    real = [r for r in records if r["classification"] == "REAL"]
    assert real == [], f"pipeline causal produziu divergencias REAL: {real[:5]}"
    non_benign = [
        r for r in records
        if r["classification"] == "BORDA" and r["column"] not in la.BENIGN_TAIL_COLUMNS
    ]
    assert non_benign == [], f"divergencia de borda fora das colunas documentadas: {non_benign}"
    assert la.decide_verdict(records, None) == la.VERDICT_PASS


def test_estatistica_global_sobre_o_frame_e_detectada(frames: dict) -> None:
    reference = frames["reference"].copy()
    cut = frames["cut50"]
    prefix = frames["prefix50"].copy()
    reference["future_probe"] = reference["close"] / reference["close"].mean()
    prefix["future_probe"] = prefix["close"] / prefix["close"].mean()
    records = la.compare_frames(reference, prefix, 0.5, cut)
    leak = [
        r for r in records
        if r["column"] == "future_probe" and r["classification"] == "REAL"
    ]
    assert leak, "estatistica global (media do frame inteiro) nao foi detectada"
    assert any(r["region"] == "mid" for r in leak), (
        "esperavamos divergencias no meio do prefixo para media global"
    )
    assert la.decide_verdict(records, None) == la.VERDICT_LEAK


def test_janela_centralizada_futura_e_detectada(frames: dict) -> None:
    reference = frames["reference"].copy()
    cut = frames["cut50"]
    prefix = frames["prefix50"].copy()
    reference["future_probe"] = reference["close"].rolling(9, center=True).mean()
    prefix["future_probe"] = prefix["close"].rolling(9, center=True).mean()
    records = la.compare_frames(reference, prefix, 0.5, cut)
    leak = [
        r for r in records
        if r["column"] == "future_probe" and r["classification"] == "REAL"
    ]
    assert leak, "janela centralizada (center=True) nao foi detectada"
    assert any(r["region"] == "mid" for r in leak)
    assert la.decide_verdict(records, None) == la.VERDICT_LEAK


def _mini_frames(n: int = 6) -> tuple[pd.DataFrame, pd.DataFrame]:
    base = pd.DataFrame({
        "timestamp": pd.date_range("2026-02-01T00:00:00Z", periods=n, freq="min"),
        "close": np.linspace(100.0, 110.0, n),
        "parent_direction": np.ones(n, dtype="int8"),
        "signal": np.zeros(n, dtype="int8"),
    })
    return base, base.copy()


def test_classifica_borda_na_truncagem_do_contexto_pai() -> None:
    reference, prefix = _mini_frames()
    prefix.loc[prefix.index[-1], "parent_direction"] = 0
    records = la.compare_frames(reference, prefix, 1.0, len(reference))
    assert len(records) == 1
    record = records[0]
    assert record["column"] == "parent_direction"
    assert record["region"] == "tail"
    assert record["classification"] == "BORDA"
    assert la.decide_verdict(records, None) == la.VERDICT_PASS


def test_divergencia_mid_em_coluna_de_bordaindica_real() -> None:
    reference, prefix = _mini_frames()
    prefix.loc[prefix.index[1], "parent_direction"] = -1
    records = la.compare_frames(reference, prefix, 1.0, len(reference))
    assert len(records) == 1
    record = records[0]
    assert record["region"] == "mid"
    assert record["classification"] == "REAL"
    assert la.decide_verdict(records, None) == la.VERDICT_LEAK


def test_coluna_ausente_no_prefixo_e_inconclusiva() -> None:
    reference, prefix = _mini_frames()
    prefix = prefix.drop(columns=["parent_direction"])
    records = la.compare_frames(reference, prefix, 1.0, len(reference))
    assert len(records) == 1
    assert records[0]["classification"] == "INCONCLUSIVO"
    assert la.decide_verdict(records, None) == la.VERDICT_INCONCLUSIVE


def test_tolerancia_float_e_igualdade_exata_de_discretos() -> None:
    n = 6
    reference = pd.DataFrame({
        "timestamp": pd.date_range("2026-03-01T00:00:00Z", periods=n, freq="min"),
        "regime_zscore": np.linspace(0.0, 1.0, n),
        "signal": np.array([0.0, 1.0, 0.0, 1.0, 0.0, 1.0]),
    })
    dentro = reference.copy()
    dentro["regime_zscore"] = reference["regime_zscore"] * (1.0 + 1e-12)
    records = la.compare_frames(reference, dentro, 1.0, n)
    assert [r for r in records if r["column"] == "regime_zscore"] == []

    fora = reference.copy()
    fora["regime_zscore"] = reference["regime_zscore"] * 1.001
    records = la.compare_frames(reference, fora, 1.0, n)
    leak = [r for r in records if r["column"] == "regime_zscore"]
    assert leak and leak[0]["classification"] == "REAL"

    discreto = reference.copy()
    discreto.loc[2, "signal"] = reference.loc[2, "signal"] + 1e-15
    records = la.compare_frames(reference, discreto, 1.0, n)
    leak = [r for r in records if r["column"] == "signal"]
    assert leak, "coluna discreta com diferenca minima passou pela tolerancia"


def test_veredito_bloqueio_e_passos() -> None:
    assert la.decide_verdict([], None) == la.VERDICT_PASS
    assert la.decide_verdict([], "interface indisponivel") == la.VERDICT_INCONCLUSIVE
    borda = [{"classification": "BORDA"}]
    assert la.decide_verdict(borda, None) == la.VERDICT_PASS
    real = [{"classification": "BORDA"}, {"classification": "REAL"}]
    assert la.decide_verdict(real, None) == la.VERDICT_LEAK
