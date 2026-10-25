"""Testes sinteticos do avaliador da janela (F1).

Dados 100% sinteticos em diretorios temporarios, relogio simulado por
monkeypatch (nenhuma excecao de relogio no CLI de producao), rede bloqueada,
espioes de leitura provando o conjunto fechado de dados e nenhum artefato
auditado alterado.
"""
from __future__ import annotations

import json
import socket
import sys
import urllib.request
from contextlib import contextmanager
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research"))
sys.path.insert(0, str(ROOT / "tests"))

import check_window_segments as cws  # noqa: E402
import run_window_evaluation as rwe  # noqa: E402

WINDOW_START = pd.Timestamp("2026-11-01T00:00:00Z")
WINDOW_END = WINDOW_START + pd.Timedelta(days=30)
AFTER_END = WINDOW_END + pd.Timedelta(minutes=5)


@pytest.fixture(autouse=True)
def _block_network(monkeypatch):
    def _deny(*_args, **_kwargs):
        raise AssertionError("REDE BLOQUEADA neste teste")

    monkeypatch.setattr(socket, "socket", _deny)
    monkeypatch.setattr(urllib.request, "urlopen", _deny)


def set_clock(monkeypatch, when: pd.Timestamp) -> None:
    monkeypatch.setattr(rwe, "_utc_now", lambda: when.to_pydatetime())


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


@contextmanager
def read_spy(monkeypatch):
    reads: list[tuple[str, str]] = []
    real_read_csv = pd.read_csv
    real_read_text = Path.read_text
    real_read_bytes = Path.read_bytes
    real_open = Path.open

    def spy_read_csv(path, *args, **kwargs):
        reads.append(("read_csv", str(path)))
        return real_read_csv(path, *args, **kwargs)

    def spy_read_text(self, *args, **kwargs):
        reads.append(("read_text", str(self.resolve())))
        return real_read_text(self, *args, **kwargs)

    def spy_read_bytes(self, *args, **kwargs):
        reads.append(("read_bytes", str(self.resolve())))
        return real_read_bytes(self, *args, **kwargs)

    def spy_open(self, mode="r", *args, **kwargs):
        if "r" in str(mode) and "+" not in str(mode):
            reads.append(("open", str(self.resolve())))
        return real_open(self, mode, *args, **kwargs)

    monkeypatch.setattr(pd, "read_csv", spy_read_csv)
    monkeypatch.setattr(Path, "read_text", spy_read_text)
    monkeypatch.setattr(Path, "read_bytes", spy_read_bytes)
    monkeypatch.setattr(Path, "open", spy_open)
    try:
        yield reads
    finally:
        pass


def allowed_paths(csv: Path, manifest: Path, report: Path) -> set[str]:
    allowed = {str(csv.resolve()), str(manifest.resolve()), str(report.resolve())}
    allowed |= {str((ROOT / rel).resolve()) for rel in rwe.CODE_DEPENDENCIES}
    return allowed


@pytest.fixture(scope="module")
def full_closed(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("win30eval")
    mp = pytest.MonkeyPatch()
    mp.setattr(cws, "_utc_now", lambda: AFTER_END.to_pydatetime())
    try:
        manifest = tmp / "manifest.jsonl"
        for day in range(30):
            seg_start = WINDOW_START + pd.Timedelta(days=day)
            path = tmp / f"seg_{day:02d}.csv"
            make_frame(seg_start, 1440, seed=5000 + day).to_csv(path, index=False)
            cws.register_segment(
                manifest, path, day, "win_eval", "P5-start",
                WINDOW_START.isoformat(), WINDOW_END.isoformat(), root=tmp,
            )
        report_path = tmp / "integrity.json"
        report = cws.verify_manifest(manifest, root=tmp)
        assert report["verdict"] == "PASS", report["reasons"]
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


def base_argv(fixture, out_dir: Path) -> list[str]:
    return [
        "--csv", str(fixture["consolidated"]),
        "--manifest", str(fixture["manifest"]),
        "--integrity-report", str(fixture["report"]),
        "--out", str(out_dir),
    ]


def read_manifest_lines(path: Path) -> list[str]:
    return [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_manifest(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------- #
# Caminho feliz
# --------------------------------------------------------------------------- #
def test_happy_path_full_evaluation(full_closed, tmp_path, monkeypatch):
    set_clock(monkeypatch, AFTER_END)
    out_dir = tmp_path / "window_evaluation"
    audit = {
        name: cws.sha256_file(ROOT / "research" / "out" / name)
        for name in ("research_results.json", "csv_integrity.json")
    }
    before_files = sorted(p.name for p in (ROOT / "research" / "out").iterdir())
    argv = base_argv(full_closed, out_dir)
    with read_spy(monkeypatch) as reads:
        rc = rwe.main(argv)
    assert rc == 0
    data_reads = {path for kind, path in reads if kind in ("read_csv", "read_text", "read_bytes", "open")}
    allowed = allowed_paths(full_closed["consolidated"], full_closed["manifest"], full_closed["report"])
    unexpected = data_reads - allowed
    assert not unexpected, f"leituras fora do conjunto fechado: {unexpected}"
    forbidden_fragments = ("data/raw", "data\\raw", "data/shadow", "data\\shadow", "reports", "research/out")
    for path in data_reads:
        assert not any(frag in path for frag in forbidden_fragments), f"leitura proibida: {path}"
    # exatamente os tres dados externos foram lidos
    data_file_reads = {
        path for kind, path in reads
        if kind in ("read_csv", "read_text", "read_bytes")
    } | {path for kind, path in reads if kind == "open"}
    for required in (str(full_closed["consolidated"].resolve()),
                     str(full_closed["manifest"].resolve()),
                     str(full_closed["report"].resolve())):
        assert required in data_file_reads, f"dado obrigatorio nao lido: {required}"

    outputs = sorted(out_dir.glob("window_evaluation_*.json"))
    assert len(outputs) == 1
    result = json.loads(outputs[0].read_text(encoding="utf-8"))
    assert result["report"] == "window_evaluation"
    assert result["protocol"] == "P5"
    assert result["window_id"] == "win_eval"
    assert result["start_record_id"] == "P5-start"
    assert result["window"]["days"] == 30
    assert result["window"]["start_utc"] == WINDOW_START.isoformat()
    assert result["variant"] == "M15_original"
    assert result["costs"]["fee_bps_per_side"] == 10.0
    assert result["costs"]["slippage_bps_per_side"] == 5.0
    assert result["costs"]["round_trip_bps"] == 30.0
    assert result["data"]["csv_path_resolved"] == str(full_closed["consolidated"].resolve())
    assert result["data"]["csv_sha256"] == cws.sha256_file(full_closed["consolidated"])
    assert result["data"]["integrity_report_sha256"] == cws.sha256_file(full_closed["report"])
    assert result["data"]["csv_rows"] == 30 * 1440
    for rel in ("research/run_window_evaluation.py", "research/run_research.py",
                "src/convergencia/strategy.py", "src/convergencia/backtest.py"):
        assert rel in result["code_hashes"]
    metrics = result["metrics"]
    for key in ("net_total_return", "max_drawdown_net", "profit_factor_net",
                "sharpe_ratio_annualized", "trades"):
        assert key in metrics
    # nenhum artefato auditado alterado
    for name, digest in audit.items():
        assert cws.sha256_file(ROOT / "research" / "out" / name) == digest
    after_files = sorted(p.name for p in (ROOT / "research" / "out").iterdir())
    assert after_files == before_files


# --------------------------------------------------------------------------- #
# Bloqueios
# --------------------------------------------------------------------------- #
def test_refuses_historical_csv_without_any_read(tmp_path, monkeypatch):
    set_clock(monkeypatch, AFTER_END)
    out_dir = tmp_path / "window_evaluation"
    argv = [
        "--csv", str(ROOT / "data" / "raw" / "BTCUSDT_1m.csv"),
        "--manifest", str(tmp_path / "manifest.jsonl"),
        "--integrity-report", str(tmp_path / "integrity.json"),
        "--out", str(out_dir),
    ]
    with read_spy(monkeypatch) as reads:
        rc = rwe.main(argv)
    assert rc == 2
    assert reads == [], f"CSV historico (ou outra entrada) foi aberto: {reads}"
    assert not out_dir.exists()


def test_refuses_missing_closure(full_closed, tmp_path, monkeypatch):
    set_clock(monkeypatch, AFTER_END)
    small = tmp_path / "small"
    small.mkdir()
    manifest = small / "manifest.jsonl"
    for i in range(3):
        path = small / f"seg_{i}.csv"
        make_frame(WINDOW_START + pd.Timedelta(hours=i), 60, seed=60 + i).to_csv(path, index=False)
        cws.register_segment(
            manifest, path, i, "win_eval", "P5-start",
            WINDOW_START.isoformat(), WINDOW_END.isoformat(), root=small,
        )
    argv = [
        "--csv", str(full_closed["consolidated"]),
        "--manifest", str(manifest),
        "--integrity-report", str(full_closed["report"]),
        "--out", str(tmp_path / "window_evaluation"),
    ]
    rc = rwe.main(argv)
    assert rc == 2


def test_refuses_span_not_30_days(full_closed, tmp_path):
    lines = read_manifest_lines(full_closed["manifest"])
    closure = json.loads(lines[-1])
    closure["window_end_utc"] = (WINDOW_END - pd.Timedelta(days=1)).isoformat()
    lines[-1] = json.dumps(closure, ensure_ascii=False)
    with pytest.raises(rwe.EvaluationRefused, match="30 dias"):
        rwe.validate_closure([json.loads(line) for line in lines])


def test_refuses_closed_before_window_end(full_closed):
    lines = read_manifest_lines(full_closed["manifest"])
    closure = json.loads(lines[-1])
    closure["closed_at_utc"] = (WINDOW_END - pd.Timedelta(minutes=1)).isoformat()
    lines[-1] = json.dumps(closure, ensure_ascii=False)
    with pytest.raises(rwe.EvaluationRefused, match="fim real da janela"):
        rwe.validate_closure([json.loads(line) for line in lines])


def test_refuses_clock_before_window_end(full_closed, tmp_path, monkeypatch):
    set_clock(monkeypatch, WINDOW_END - pd.Timedelta(hours=1))
    rc = rwe.main(base_argv(full_closed, tmp_path / "window_evaluation"))
    assert rc == 2
    assert not (tmp_path / "window_evaluation").exists()


def test_refuses_expected_sha_mismatch(full_closed, tmp_path, monkeypatch):
    set_clock(monkeypatch, AFTER_END)
    argv = base_argv(full_closed, tmp_path / "window_evaluation") + [
        "--expected-sha256", "ab" * 32
    ]
    rc = rwe.main(argv)
    assert rc == 2


def test_refuses_csv_path_not_linked_to_closure(full_closed, tmp_path, monkeypatch):
    set_clock(monkeypatch, AFTER_END)
    impostor = tmp_path / "impostor.csv"
    impostor.write_bytes(full_closed["consolidated"].read_bytes())
    argv = [
        "--csv", str(impostor),
        "--manifest", str(full_closed["manifest"]),
        "--integrity-report", str(full_closed["report"]),
        "--out", str(tmp_path / "window_evaluation"),
    ]
    with read_spy(monkeypatch) as reads:
        rc = rwe.main(argv)
    assert rc == 2
    assert not any(str(impostor.resolve()) in path for _, path in reads), (
        "CSV nao vinculado ao fechamento foi aberto"
    )


def test_refuses_report_sha_mismatch(full_closed, tmp_path, monkeypatch):
    set_clock(monkeypatch, AFTER_END)
    tampered = tmp_path / "manifest.jsonl"
    lines = read_manifest_lines(full_closed["manifest"])
    closure = json.loads(lines[-1])
    closure["integrity_report_sha256"] = "cd" * 32
    lines[-1] = json.dumps(closure, ensure_ascii=False)
    write_manifest(tampered, lines)
    argv = [
        "--csv", str(full_closed["consolidated"]),
        "--manifest", str(tampered),
        "--integrity-report", str(full_closed["report"]),
        "--out", str(tmp_path / "window_evaluation"),
    ]
    rc = rwe.main(argv)
    assert rc == 2


def test_refuses_tampered_closure_segment(full_closed, tmp_path, monkeypatch):
    set_clock(monkeypatch, AFTER_END)
    tampered = tmp_path / "manifest.jsonl"
    lines = read_manifest_lines(full_closed["manifest"])
    closure = json.loads(lines[-1])
    closure["segments"][7]["sha256"] = "ef" * 32
    lines[-1] = json.dumps(closure, ensure_ascii=False)
    write_manifest(tampered, lines)
    argv = [
        "--csv", str(full_closed["consolidated"]),
        "--manifest", str(tampered),
        "--integrity-report", str(full_closed["report"]),
        "--out", str(tmp_path / "window_evaluation"),
    ]
    rc = rwe.main(argv)
    assert rc == 2


def test_refuses_bad_out_dir_name(full_closed, tmp_path, monkeypatch):
    set_clock(monkeypatch, AFTER_END)
    rc = rwe.main(base_argv(full_closed, tmp_path / "saida"))
    assert rc == 2
    rc = rwe.main(base_argv(full_closed, ROOT / "research" / "out"))
    assert rc == 2
    assert not list((ROOT / "research" / "out").glob("window_evaluation_*.json"))


def test_missing_cli_inputs_are_usage_errors(full_closed, tmp_path, monkeypatch):
    with pytest.raises(SystemExit):
        rwe.main(["--csv", str(full_closed["consolidated"])])
