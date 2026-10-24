"""Testes sinteticos do verificador de janela (F2).

Somente dados sinteticos em diretorios temporarios, rede bloqueada,
nenhum artefato real alterado e nenhuma metrica de desempenho envolvida.
"""
from __future__ import annotations

import json
import shutil
import socket
import sys
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research"))

import check_window_segments as cws  # noqa: E402

WINDOW_START = pd.Timestamp("2026-11-01T00:00:00Z")
WINDOW_END = WINDOW_START + pd.Timedelta(days=30)
AFTER_END = WINDOW_END + pd.Timedelta(minutes=5)
FORBIDDEN_WORDS = (
    "sharpe", "profit_factor", "profit factor", "pnl", "equity",
    "retorno", "drawdown", "rentabilidade", "lucro", "buy_and_hold",
)


@pytest.fixture(autouse=True)
def _block_network(monkeypatch):
    def _deny(*_args, **_kwargs):
        raise AssertionError("REDE BLOQUEADA neste teste")

    monkeypatch.setattr(socket, "socket", _deny)
    monkeypatch.setattr(urllib.request, "urlopen", _deny)


def make_frame(start: pd.Timestamp, minutes: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    n = minutes
    ts = pd.date_range(start, periods=n, freq="1min")
    close = 100_000.0 * np.exp(np.cumsum(rng.normal(0.0, 0.0005, n)))
    open_ = np.empty(n)
    open_[0] = close[0]
    open_[1:] = close[:-1]
    high = np.maximum(open_, close) * (1.0 + rng.uniform(0.0, 0.0004, n))
    low = np.minimum(open_, close) * (1.0 - rng.uniform(0.0, 0.0004, n))
    volume = rng.uniform(1.0, 10.0, n)
    return pd.DataFrame(
        {
            "timestamp": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
            "quote_volume": close * volume,
        }
    )


def write_segment(path: Path, start: pd.Timestamp, minutes: int, seed: int) -> Path:
    frame = make_frame(start, minutes, seed)
    frame.to_csv(path, index=False)
    return path


def build_segments(tmp: Path, days: int, minutes_per_day: int = 1440) -> Path:
    manifest = tmp / "manifest.jsonl"
    for day in range(days):
        seg_start = WINDOW_START + pd.Timedelta(days=day)
        path = tmp / f"seg_{day:02d}.csv"
        write_segment(path, seg_start, minutes_per_day, seed=1000 + day)
        cws.register_segment(
            manifest, path, day, "win_test", "P5-start",
            WINDOW_START.isoformat(), WINDOW_END.isoformat(), root=tmp,
        )
    return manifest


def three_segment_base(tmp: Path) -> Path:
    manifest = tmp / "manifest.jsonl"
    for i in range(3):
        seg_start = WINDOW_START + pd.Timedelta(hours=i)
        path = tmp / f"seg_{i}.csv"
        write_segment(path, seg_start, 60, seed=42 + i)
        cws.register_segment(
            manifest, path, i, "win_test", "P5-start",
            WINDOW_START.isoformat(), WINDOW_END.isoformat(), root=tmp,
        )
    return manifest


@pytest.fixture(scope="module")
def full_window_closed(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("win30")
    mp = pytest.MonkeyPatch()
    mp.setattr(cws, "_utc_now", lambda: AFTER_END.to_pydatetime())
    try:
        manifest = build_segments(tmp, days=30)
        report_path = tmp / "integrity.json"
        report = cws.verify_manifest(manifest, root=tmp)
        assert report["verdict"] == "PASS", report["reasons"]
        assert report["complete_30d"] is True
        cws.write_report(report, report_path)
        consolidated = tmp / "consolidated_1m.csv"
        closure = cws.close_window(manifest, report_path, consolidated, root=tmp)
        yield {
            "tmp": tmp,
            "manifest": manifest,
            "report": report_path,
            "consolidated": consolidated,
            "closure": closure,
        }
    finally:
        mp.undo()


def read_lines(path: Path) -> list[str]:
    return [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_lines(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------- #
# Rede
# --------------------------------------------------------------------------- #
def test_network_is_blocked():
    with pytest.raises(AssertionError, match="REDE BLOQUEADA"):
        socket.socket()


# --------------------------------------------------------------------------- #
# Registro
# --------------------------------------------------------------------------- #
def test_happy_three_segments_pass(tmp_path):
    manifest = three_segment_base(tmp_path)
    report = cws.verify_manifest(manifest, root=tmp_path)
    assert report["verdict"] == "PASS", report["reasons"]
    assert report["complete_30d"] is False  # parcial ainda PASSa diariamente
    assert report["segments_checked"] == 3


def test_register_seq_mismatch_refused(tmp_path):
    manifest = three_segment_base(tmp_path)
    extra = tmp_path / "seg_extra.csv"
    write_segment(extra, WINDOW_START + pd.Timedelta(hours=3), 60, seed=7)
    with pytest.raises(cws.CheckError, match="seq esperado"):
        cws.register_segment(
            manifest, extra, 99, "win_test", "P5-start",
            WINDOW_START.isoformat(), WINDOW_END.isoformat(), root=tmp_path,
        )


def test_register_window_mix_refused(tmp_path):
    manifest = three_segment_base(tmp_path)
    extra = tmp_path / "seg_extra.csv"
    write_segment(extra, WINDOW_START + pd.Timedelta(hours=3), 60, seed=8)
    with pytest.raises(cws.CheckError, match="mistura de janelas"):
        cws.register_segment(
            manifest, extra, 3, "OUTRA_JANELA", "P5-start",
            WINDOW_START.isoformat(), WINDOW_END.isoformat(), root=tmp_path,
        )


def test_register_out_of_window_refused(tmp_path):
    manifest = three_segment_base(tmp_path)
    extra = tmp_path / "seg_extra.csv"
    write_segment(extra, WINDOW_END + pd.Timedelta(hours=1), 60, seed=9)
    with pytest.raises(cws.CheckError):
        cws.register_segment(
            manifest, extra, 3, "win_test", "P5-start",
            WINDOW_START.isoformat(), WINDOW_END.isoformat(), root=tmp_path,
        )


def test_register_discontinuous_refused(tmp_path):
    manifest = three_segment_base(tmp_path)
    extra = tmp_path / "seg_extra.csv"
    write_segment(extra, WINDOW_START + pd.Timedelta(hours=5), 60, seed=10)
    with pytest.raises(cws.CheckError, match="descontinuidade"):
        cws.register_segment(
            manifest, extra, 3, "win_test", "P5-start",
            WINDOW_START.isoformat(), WINDOW_END.isoformat(), root=tmp_path,
        )


def test_register_corrupt_content_refused(tmp_path):
    manifest = three_segment_base(tmp_path)
    bad = tmp_path / "seg_bad.csv"
    frame = make_frame(WINDOW_START + pd.Timedelta(hours=3), 60, seed=11)
    frame.loc[10, "high"] = 1.0  # faixa OHLC invalida
    frame.to_csv(bad, index=False)
    with pytest.raises(cws.CheckError, match="reprovado"):
        cws.register_segment(
            manifest, bad, 3, "win_test", "P5-start",
            WINDOW_START.isoformat(), WINDOW_END.isoformat(), root=tmp_path,
        )


# --------------------------------------------------------------------------- #
# Cadeia canonica
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("idx", "field", "value"),
    [
        (0, "rows", 999),
        (0, "sha256", "deadbeef"),
        (0, "registered_at_utc", "2026-01-01T00:00:00+00:00"),
        (0, "file", "inexistente.csv"),
        (1, "rows", 1),
        (1, "first_ts_utc", "2026-11-01T00:59:00+00:00"),
        (1, "prev_sha256", "00" * 32),
    ],
)
def test_chain_break_on_any_prior_field(tmp_path, idx, field, value):
    manifest = three_segment_base(tmp_path)
    lines = read_lines(manifest)
    entry = json.loads(lines[idx])
    entry[field] = value
    lines[idx] = json.dumps(entry, ensure_ascii=False)
    write_lines(manifest, lines)
    report = cws.verify_manifest(manifest, root=tmp_path)
    assert report["verdict"] == "FAIL"
    assert any("elo quebrado" in r or "prev_sha256" in r for r in report["reasons"])


def test_first_entry_prev_must_be_null(tmp_path):
    manifest = three_segment_base(tmp_path)
    lines = read_lines(manifest)
    entry = json.loads(lines[0])
    entry["prev_sha256"] = "ab" * 32
    lines[0] = json.dumps(entry, ensure_ascii=False)
    write_lines(manifest, lines)
    report = cws.verify_manifest(manifest, root=tmp_path)
    assert report["verdict"] == "FAIL"
    assert any("primeira entrada" in r for r in report["reasons"])


# --------------------------------------------------------------------------- #
# Regras de conteudo (unitarias no validador)
# --------------------------------------------------------------------------- #
def test_content_gap_invalid(tmp_path):
    frame = make_frame(WINDOW_START, 60, seed=21)
    frame = frame.drop(index=30).reset_index(drop=True)
    checks = cws.check_segment_frame(frame)
    assert checks["ok"] is False
    assert checks["rows_match_span"] is False
    assert checks["non_1min_steps"] > 0


def test_content_duplicate_invalid(tmp_path):
    frame = make_frame(WINDOW_START, 60, seed=22)
    frame = pd.concat([frame, frame.iloc[[10]]], ignore_index=True)
    checks = cws.check_segment_frame(frame)
    assert checks["ok"] is False
    assert checks["duplicate_timestamps"] == 1


def test_content_disorder_invalid(tmp_path):
    frame = make_frame(WINDOW_START, 60, seed=23)
    frame.loc[[10, 11], ["timestamp", "open", "close"]] = frame.loc[[11, 10], [
        "timestamp", "open", "close"
    ]].to_numpy()
    checks = cws.check_segment_frame(frame)
    assert checks["ok"] is False
    assert not checks["monotonic_increasing"] or checks["non_1min_steps"] > 0


def test_content_ohlc_range_invalid(tmp_path):
    frame = make_frame(WINDOW_START, 60, seed=24)
    frame.loc[5, "high"] = float(frame.loc[5, "close"]) - 1.0
    checks = cws.check_segment_frame(frame)
    assert checks["ok"] is False
    assert checks["ohlc_range_violations"] >= 1


def test_content_negative_volume_invalid(tmp_path):
    frame = make_frame(WINDOW_START, 60, seed=25)
    frame.loc[3, "volume"] = -1.0
    checks = cws.check_segment_frame(frame)
    assert checks["ok"] is False
    assert checks["negative_volume"] == 1


# --------------------------------------------------------------------------- #
# Falhas de arquivo/manifesto
# --------------------------------------------------------------------------- #
def test_byte_flip_invalidates(tmp_path):
    manifest = three_segment_base(tmp_path)
    target = tmp_path / "seg_1.csv"
    text = target.read_text(encoding="utf-8")
    target.write_text(text.replace("100", "101", 1), encoding="utf-8")
    report = cws.verify_manifest(manifest, root=tmp_path)
    assert report["verdict"] == "FAIL"
    assert any("sha256" in r for r in report["reasons"])


def test_missing_segment_file_invalidates(tmp_path):
    manifest = three_segment_base(tmp_path)
    (tmp_path / "seg_1.csv").unlink()
    report = cws.verify_manifest(manifest, root=tmp_path)
    assert report["verdict"] == "FAIL"
    assert any("inexistente" in r for r in report["reasons"])


# --------------------------------------------------------------------------- #
# Fechamento
# --------------------------------------------------------------------------- #
def test_close_happy_full_window(full_window_closed):
    closure = full_window_closed["closure"]
    assert closure["protocol"] == "P5"
    assert closure["days"] == 30
    assert len(closure["segments"]) == 30
    assert [s["seq"] for s in closure["segments"]] == list(range(30))
    consolidated = full_window_closed["consolidated"]
    assert cws.sha256_file(consolidated) == closure["consolidated_csv_sha256"]
    assert closure["consolidated_rows"] == 30 * 1440
    assert cws.sha256_file(full_window_closed["report"]) == closure["integrity_report_sha256"]
    assert pd.Timestamp(closure["closed_at_utc"]) >= WINDOW_END
    report = cws.verify_manifest(full_window_closed["manifest"], root=full_window_closed["tmp"])
    assert report["verdict"] == "PASS", report["reasons"]
    assert report["complete_30d"] is True
    assert cws.verify_closure(
        cws.load_manifest(full_window_closed["manifest"]), root=full_window_closed["tmp"]
    ) == []


@pytest.mark.parametrize(
    ("position", "mutate"),
    [
        ("window_end_utc", lambda e: e.__setitem__("window_end_utc", "2026-12-02T00:00:00+00:00")),
        ("protocol", lambda e: e.__setitem__("protocol", "P4")),
        ("csv_sha", lambda e: e.__setitem__("consolidated_csv_sha256", "00" * 32)),
        ("report_sha", lambda e: e.__setitem__("integrity_report_sha256", "11" * 32)),
        ("segment_sha", lambda e: e["segments"][3].__setitem__("sha256", "22" * 32)),
        ("segments_count", lambda e: e["segments"].pop()),
        ("closed_at", lambda e: e.__setitem__(
            "closed_at_utc", (WINDOW_END - pd.Timedelta(minutes=1)).isoformat()
        )),
    ],
)
def test_tampered_closure_detected(full_window_closed, tmp_path, position, mutate):
    src = full_window_closed["manifest"]
    copy = tmp_path / "manifest.jsonl"
    lines = read_lines(src)
    closure = json.loads(lines[-1])
    assert closure["record"] == "window_closed"
    mutate(closure)
    lines[-1] = json.dumps(closure, ensure_ascii=False)
    write_lines(copy, lines)
    reasons = cws.verify_closure(
        cws.load_manifest(copy), root=full_window_closed["tmp"]
    )
    assert reasons, f"alteracao do fechamento nao detectada: {position}"
    report = cws.verify_manifest(copy, root=full_window_closed["tmp"])
    assert report["verdict"] == "FAIL"


def test_tampered_segment_body_breaks_closed_manifest(full_window_closed, tmp_path):
    copy = tmp_path / "manifest.jsonl"
    lines = read_lines(full_window_closed["manifest"])
    entry = json.loads(lines[5])
    entry["rows"] = entry["rows"] + 1
    lines[5] = json.dumps(entry, ensure_ascii=False)
    write_lines(copy, lines)
    report = cws.verify_manifest(copy, root=full_window_closed["tmp"])
    assert report["verdict"] == "FAIL"
    assert cws.verify_closure(cws.load_manifest(copy), root=full_window_closed["tmp"])


def test_close_refuses_before_window_end(tmp_path, monkeypatch):
    manifest = build_segments(tmp_path, days=30)
    report_path = tmp_path / "integrity.json"
    cws.write_report(cws.verify_manifest(manifest, root=tmp_path), report_path)
    monkeypatch.setattr(
        cws, "_utc_now", lambda: (WINDOW_END - pd.Timedelta(hours=1)).to_pydatetime()
    )
    with pytest.raises(cws.CheckError, match="anterior ao fim real"):
        cws.close_window(manifest, report_path, tmp_path / "out.csv", root=tmp_path)


def test_close_requires_30_segments(tmp_path, monkeypatch):
    monkeypatch.setattr(cws, "_utc_now", lambda: AFTER_END.to_pydatetime())
    manifest = build_segments(tmp_path, days=29)
    report_path = tmp_path / "integrity.json"
    cws.write_report(cws.verify_manifest(manifest, root=tmp_path), report_path)
    with pytest.raises(cws.CheckError, match="sessao incompleta"):
        cws.close_window(manifest, report_path, tmp_path / "out.csv", root=tmp_path)


# --------------------------------------------------------------------------- #
# Destinos e ausencia de metricas
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("name", ["csv_integrity.json", "research_results.json"])
def test_report_forbidden_output_refused(name):
    report = {"report": "window_integrity", "verdict": "PASS"}
    forbidden = ROOT / "research" / "out" / name
    before = cws.sha256_file(forbidden)
    with pytest.raises(cws.CheckError, match="destino proibido"):
        cws.write_report(report, forbidden)
    assert cws.sha256_file(forbidden) == before


def test_report_and_closure_have_no_performance_fields(full_window_closed):
    report_text = full_window_closed["report"].read_text(encoding="utf-8").lower()
    closure_text = json.dumps(full_window_closed["closure"], ensure_ascii=False).lower()
    for word in FORBIDDEN_WORDS:
        assert word not in report_text, f"relatorio contem {word}"
        assert word not in closure_text, f"fechamento contem {word}"
