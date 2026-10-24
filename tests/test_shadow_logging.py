"""Testes sinteticos do gravador sombra prospectivo (F3).

Ledger e aprovacao fabricados em tmp_path (nunca o ledger real), relogio
livre, rede bloqueada. Verifica: referencia JSON isolada nao autoriza;
esquema protocolo/ativo/P5/risk_limit_approved; state.json SEM campos de
desempenho; risk_monitor.json como unico arquivo de desempenho; eventos de
interrupcao com codigos de saida; replay por igualdade numerica direta.
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
sys.path.insert(0, str(ROOT / "scripts"))

import run_shadow_prospectivo as rsp  # noqa: E402

BASE = pd.Timestamp("2026-06-01T00:00:00Z")

FORBIDDEN_STATE_KEYS = (
    "equity", "peak", "drawdown", "pnl", "sharpe", "profit", "return",
    "win_rate", "metrics", "cumulative", "drawdown_net",
)
MONITOR_KEYS = {
    "max_drawdown_net", "limit_drawdown_net", "breached", "updated_at_utc", "protocol",
}


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
    close = 100_000.0 * np.exp(np.cumsum(rng.normal(0.0, 0.0004, n)))
    open_ = np.empty(n)
    open_[0] = close[0]
    open_[1:] = close[:-1]
    high = np.maximum(open_, close) * (1.0 + rng.uniform(0.0, 0.0003, n))
    low = np.minimum(open_, close) * (1.0 - rng.uniform(0.0, 0.0003, n))
    volume = rng.uniform(1.0, 9.0, n)
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


def p5_stub() -> dict:
    return {
        "record_type": "protocolo",
        "id": "P5",
        "statement": "pre-registro da janela de 30 dias",
        "source": "memory/journal.md",
        "status": "ativo",
        "recorded_at": "2026-10-22",
    }


def approval_record(**overrides) -> dict:
    record = {
        "record_type": "protocolo",
        "id": "P5-RISK",
        "statement": "aprovacao do limite de risco da janela",
        "source": "memory/journal.md",
        "status": "ativo",
        "recorded_at": "2026-10-22",
        "protocol_ref": "P5",
        "risk_limit_approved": True,
        "limit_drawdown_net": -0.10,
    }
    record.update(overrides)
    return record


def write_ledger(path: Path, records: list[dict]) -> None:
    path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n",
        encoding="utf-8",
    )


@pytest.fixture
def env(tmp_path, monkeypatch):
    shadow = tmp_path / "shadow"
    monkeypatch.setattr(rsp, "SHADOW_ROOT", shadow)
    out = shadow / "sessao_sintetica"
    ledger = tmp_path / "ledger.jsonl"
    write_ledger(ledger, [p5_stub(), approval_record()])
    ref = tmp_path / "aprovacao.json"
    ref.write_text(
        json.dumps({
            "ledger": str(ledger),
            "record_id": "P5-RISK",
            "protocol_ref": "P5",
            "limit_drawdown_net": -0.10,
        }),
        encoding="utf-8",
    )
    seg0 = tmp_path / "seg0.csv"
    make_frame(BASE, 600, seed=11).to_csv(seg0, index=False)
    seg1 = tmp_path / "seg1.csv"
    make_frame(BASE + pd.Timedelta(minutes=600), 600, seed=12).to_csv(seg1, index=False)
    gap = tmp_path / "gap.csv"
    make_frame(BASE + pd.Timedelta(minutes=1202), 300, seed=13).to_csv(gap, index=False)
    return {
        "tmp": tmp_path,
        "shadow": shadow,
        "out": out,
        "ledger": ledger,
        "ref": ref,
        "seg0": seg0,
        "seg1": seg1,
        "gap": gap,
    }


def base_argv(env, segment: Path, out: Path | None = None) -> list[str]:
    return [
        "--segment", str(segment),
        "--out", str(out if out is not None else env["out"]),
        "--risk-approval", str(env["ref"]),
        "--ledger", str(env["ledger"]),
    ]


def state_and_monitor(out: Path) -> tuple[dict, dict]:
    state = json.loads((out / "state.json").read_text(encoding="utf-8"))
    monitor = json.loads((out / "risk_monitor.json").read_text(encoding="utf-8"))
    return state, monitor


def all_keys(obj) -> list[str]:
    keys: list[str] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            keys.append(str(key))
            keys.extend(all_keys(value))
    return keys


def read_events(out: Path) -> list[dict]:
    path = out / "events.jsonl"
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


@contextmanager
def read_spy(monkeypatch):
    reads: list[str] = []
    real_read_csv = pd.read_csv
    real_read_text = Path.read_text
    real_read_bytes = Path.read_bytes
    real_open = Path.open

    def spy_read_csv(path, *args, **kwargs):
        reads.append(str(path))
        return real_read_csv(path, *args, **kwargs)

    def spy_read_text(self, *args, **kwargs):
        reads.append(str(self.resolve()))
        return real_read_text(self, *args, **kwargs)

    def spy_read_bytes(self, *args, **kwargs):
        reads.append(str(self.resolve()))
        return real_read_bytes(self, *args, **kwargs)

    def spy_open(self, mode="r", *args, **kwargs):
        if "r" in str(mode) and "+" not in str(mode):
            reads.append(str(self.resolve()))
        return real_open(self, mode, *args, **kwargs)

    monkeypatch.setattr(pd, "read_csv", spy_read_csv)
    monkeypatch.setattr(Path, "read_text", spy_read_text)
    monkeypatch.setattr(Path, "read_bytes", spy_read_bytes)
    monkeypatch.setattr(Path, "open", spy_open)
    try:
        yield reads
    finally:
        pass


def protected_hashes() -> dict[str, str]:
    return {
        str(path): rsp.sha256_file(path)
        for path in (
            ROOT / "memory" / "hypotheses_ledger.jsonl",
            ROOT / "memory" / "journal.md",
            ROOT / "research" / "out" / "research_results.json",
            ROOT / "research" / "out" / "csv_integrity.json",
        )
    }


# --------------------------------------------------------------------------- #
# Autorizacao: referencia isolada nunca basta
# --------------------------------------------------------------------------- #
def test_reference_alone_is_not_enough(env, tmp_path):
    bare_ledger = tmp_path / "so_p5.jsonl"
    write_ledger(bare_ledger, [p5_stub()])
    ref = tmp_path / "ref_solta.json"
    ref.write_text(
        json.dumps({
            "ledger": str(bare_ledger),
            "record_id": "P5-RISK",
            "protocol_ref": "P5",
            "limit_drawdown_net": -0.10,
        }),
        encoding="utf-8",
    )
    argv = [
        "--segment", str(env["seg0"]),
        "--out", str(env["out"]),
        "--risk-approval", str(ref),
        "--ledger", str(bare_ledger),
    ]
    rc = rsp.main(argv)
    assert rc == 2
    assert not env["out"].exists()


def test_approval_record_must_be_active_protocol(env, tmp_path):
    variants = [
        approval_record(status="arquivada"),
        approval_record(risk_limit_approved=False),
        approval_record(limit_drawdown_net=-0.11),
        approval_record(record_type="hipotese"),
        approval_record(protocol_ref="P4"),
    ]
    for i, record in enumerate(variants):
        ledger = tmp_path / f"ledger_{i}.jsonl"
        write_ledger(ledger, [p5_stub(), record])
        ref = tmp_path / f"ref_{i}.json"
        ref.write_text(
            json.dumps({
                "ledger": str(ledger),
                "record_id": "P5-RISK",
                "protocol_ref": "P5",
                "limit_drawdown_net": -0.10,
            }),
            encoding="utf-8",
        )
        argv = [
            "--segment", str(env["seg0"]),
            "--out", str(env["out"] / f"run_{i}"),
            "--risk-approval", str(ref),
            "--ledger", str(ledger),
        ]
        rc = rsp.main(argv)
        assert rc == 2, f"variante {i} nao recusada: {record}"
        assert not (env["out"] / f"run_{i}").exists()


def test_p5_record_itself_cannot_grant_risk_approval(env, tmp_path):
    ref = tmp_path / "ref_p5.json"
    ref.write_text(
        json.dumps({
            "ledger": str(env["ledger"]),
            "record_id": "P5",
            "protocol_ref": "P5",
            "limit_drawdown_net": -0.10,
        }),
        encoding="utf-8",
    )
    argv = [
        "--segment", str(env["seg0"]),
        "--out", str(env["out"]),
        "--risk-approval", str(ref),
        "--ledger", str(env["ledger"]),
    ]
    rc = rsp.main(argv)
    assert rc == 2
    assert not env["out"].exists()


def test_out_dir_outside_shadow_refused(env, tmp_path):
    elsewhere = tmp_path / "nao_e_shadow"
    rc = rsp.main(base_argv(env, env["seg0"], out=elsewhere))
    assert rc == 2
    assert not elsewhere.exists()


# --------------------------------------------------------------------------- #
# Caminho feliz e resume
# --------------------------------------------------------------------------- #
def test_happy_first_segment_state_and_monitor(env, monkeypatch, capsys):
    before = protected_hashes()
    with read_spy(monkeypatch) as reads:
        rc = rsp.main(base_argv(env, env["seg0"]))
    assert rc == 0
    assert env["out"].is_dir()
    allowed = {
        str(env["ref"].resolve()), str(env["ledger"].resolve()),
        str(env["seg0"].resolve()),
        str((env["out"] / "state.json").resolve()),
    } | {str((rsp.ROOT / rel).resolve()) for rel in rsp.CODE_DEPENDENCIES}
    unexpected = [path for path in reads if path not in allowed]
    assert not unexpected, f"leituras fora do conjunto fechado: {unexpected}"
    for path in reads:
        norm = path.replace("\\", "/")
        assert "/data/raw/" not in norm, f"CSV historico aberto: {path}"
        assert "/research/out/" not in norm, f"relatorio de pesquisa aberto: {path}"
        assert norm.endswith("journal.md") is False, f"journal aberto: {path}"

    state, monitor = state_and_monitor(env["out"])
    keys = [key.lower() for key in all_keys(state)]
    for banned in FORBIDDEN_STATE_KEYS:
        assert not any(banned in key for key in keys), f"state.json contem {banned}"
    assert set(state) >= {
        "protocol", "variant", "window_id", "segments", "last_timestamp",
        "position", "reanchor_open", "reanchor_ts", "code_manifest", "costs",
    }
    assert state["protocol"] == "P5"
    assert state["variant"] == "M15_original"
    assert state["costs"] == {"fee_bps_per_side": 10.0, "slippage_bps_per_side": 5.0}
    assert state["segments"] == [str(env["seg0"].resolve())]
    assert state["last_timestamp"] == (BASE + pd.Timedelta(minutes=599)).isoformat()
    assert isinstance(state["reanchor_open"], float)
    assert "research/run_research.py" in state["code_manifest"]
    assert "src/convergencia/strategy.py" in state["code_manifest"]

    assert set(monitor) == MONITOR_KEYS
    assert monitor["protocol"] == "P5"
    assert monitor["limit_drawdown_net"] == -0.10
    assert monitor["breached"] is False
    assert isinstance(monitor["max_drawdown_net"], float)
    assert monitor["max_drawdown_net"] <= 0.0

    out_lines = capsys.readouterr().out
    assert "sessao gravada" in out_lines
    for term in ("sharpe", "net_total", "%", "profit"):
        assert term not in out_lines.lower(), f"metrica divulgada no stdout: {term}"

    assert read_events(env["out"]) == []
    assert protected_hashes() == before


def test_resume_second_segment_replay_matches_direct(env, monkeypatch):
    rc = rsp.main(base_argv(env, env["seg0"]))
    assert rc == 0
    first_monitor = json.loads(
        (env["out"] / "risk_monitor.json").read_text(encoding="utf-8")
    )
    rc = rsp.main(base_argv(env, env["seg1"]))
    assert rc == 0
    state, monitor = state_and_monitor(env["out"])
    assert state["segments"] == [str(env["seg0"].resolve()), str(env["seg1"].resolve())]
    assert state["last_timestamp"] == (BASE + pd.Timedelta(minutes=1199)).isoformat()

    candles = pd.concat(
        [pd.read_csv(env["seg0"]), pd.read_csv(env["seg1"])],
        ignore_index=True,
    ).sort_values("timestamp", kind="mergesort").reset_index(drop=True)
    features = rsp.run_research.generate_features(
        candles, "15m", rsp.run_research.ORIGINAL_CONFIG
    )
    rsp.run_research.reconcile_full(features)
    _bt, metrics = rsp.run_research.run_one(
        features,
        features["signal"].to_numpy(),
        rsp.run_research.COST_SCENARIOS[1],
    )
    assert monitor["max_drawdown_net"] == pytest.approx(
        float(metrics["max_drawdown_net"]), abs=1e-12
    )
    assert monitor["breached"] is False
    assert first_monitor["max_drawdown_net"] == pytest.approx(
        float(first_monitor["max_drawdown_net"]), abs=0.0
    )


def test_resume_code_manifest_mismatch_is_fatal(env, capsys):
    rc = rsp.main(base_argv(env, env["seg0"]))
    assert rc == 0
    state_path = env["out"] / "state.json"
    monitor_path = env["out"] / "risk_monitor.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["code_manifest"]["research/run_research.py"] = "00" * 32
    state_path.write_text(json.dumps(state), encoding="utf-8")
    state_before = state_path.read_bytes()
    monitor_before = monitor_path.read_bytes()

    rc = rsp.main(base_argv(env, env["seg1"]))
    assert rc == 4
    assert state_path.read_bytes() == state_before
    assert monitor_path.read_bytes() == monitor_before
    events = read_events(env["out"])
    assert [e["event"] for e in events] == ["FATAL_SESSION_STOP"]
    assert "code_manifest" in events[0]["detail"]


def test_gap_segment_records_collection_failure(env):
    rc = rsp.main(base_argv(env, env["seg0"]))
    assert rc == 0
    state_before = (env["out"] / "state.json").read_bytes()
    monitor_before = (env["out"] / "risk_monitor.json").read_bytes()

    rc = rsp.main(base_argv(env, env["gap"]))
    assert rc == 2
    assert (env["out"] / "state.json").read_bytes() == state_before
    assert (env["out"] / "risk_monitor.json").read_bytes() == monitor_before
    events = read_events(env["out"])
    assert [e["event"] for e in events] == ["COLLECTION_FAILURE"]
    state, _ = state_and_monitor(env["out"])
    assert state["segments"] == [str(env["seg0"].resolve())]


def test_risk_breach_wires_monitor_event_and_exit(env, monkeypatch, capsys):
    monkeypatch.setattr(rsp, "_replay", lambda candles: (-0.55, 0.0))
    rc = rsp.main(base_argv(env, env["seg0"]))
    assert rc == 3
    _state, monitor = state_and_monitor(env["out"])
    assert set(monitor) == MONITOR_KEYS
    assert monitor["breached"] is True
    assert monitor["max_drawdown_net"] == pytest.approx(-0.55, abs=1e-12)
    assert monitor["limit_drawdown_net"] == -0.10
    events = read_events(env["out"])
    assert [e["event"] for e in events] == ["RISK_LIMIT_BREACHED"]
    assert "nao e resultado" in events[0]["detail"]
    out_lines = capsys.readouterr().out
    assert "INTERRUPCAO: RISK_LIMIT_BREACHED" in out_lines
    assert "0.55" not in out_lines
    state, _ = state_and_monitor(env["out"])
    assert state["segments"] == [str(env["seg0"].resolve())]


def test_boundary_max_dd_equal_to_limit_is_breached(env, monkeypatch):
    monkeypatch.setattr(rsp, "_replay", lambda candles: (-0.10, 0.0))
    rc = rsp.main(base_argv(env, env["seg0"]))
    assert rc == 3
    _state, monitor = state_and_monitor(env["out"])
    assert monitor["max_drawdown_net"] == pytest.approx(-0.10, abs=1e-12)
    assert monitor["limit_drawdown_net"] == -0.10
    assert monitor["breached"] is True
    events = read_events(env["out"])
    assert [e["event"] for e in events] == ["RISK_LIMIT_BREACHED"]


def test_max_dd_shallower_than_limit_is_not_breached(env, monkeypatch):
    monkeypatch.setattr(rsp, "_replay", lambda candles: (-0.05, 0.0))
    rc = rsp.main(base_argv(env, env["seg0"]))
    assert rc == 0
    _state, monitor = state_and_monitor(env["out"])
    assert monitor["max_drawdown_net"] == pytest.approx(-0.05, abs=1e-12)
    assert monitor["limit_drawdown_net"] == -0.10
    assert monitor["breached"] is False
    assert read_events(env["out"]) == []


def test_limit_outside_signed_range_refused(env, tmp_path):
    for i, bad_limit in enumerate((0.05, 0.0, -1.5)):
        record = approval_record(limit_drawdown_net=bad_limit)
        ledger = tmp_path / f"ledger_range_{i}.jsonl"
        write_ledger(ledger, [p5_stub(), record])
        ref = tmp_path / f"ref_range_{i}.json"
        ref.write_text(
            json.dumps({
                "ledger": str(ledger),
                "record_id": "P5-RISK",
                "protocol_ref": "P5",
                "limit_drawdown_net": bad_limit,
            }),
            encoding="utf-8",
        )
        out = tmp_path / "shadow" / f"fora_intervalo_{i}"
        rc = rsp.main([
            "--segment", str(env["seg0"]),
            "--out", str(out),
            "--risk-approval", str(ref),
            "--ledger", str(ledger),
        ])
        assert rc == 2, f"limite {bad_limit} nao recusado"
        assert not out.exists()


def test_duplicate_segment_refused(env):
    rc = rsp.main(base_argv(env, env["seg0"]))
    assert rc == 0
    state_before = (env["out"] / "state.json").read_bytes()
    rc = rsp.main(base_argv(env, env["seg0"]))
    assert rc == 2
    assert (env["out"] / "state.json").read_bytes() == state_before
    events = read_events(env["out"])
    assert [e["event"] for e in events] == ["COLLECTION_FAILURE"]
