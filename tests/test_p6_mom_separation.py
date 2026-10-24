"""Testes de separacao P5 vs P6-MOM (protocolo prospectivo MOM_TF240_LB96).

Cobre: (1) config congelada igual ao vencedor da busca historica;
(2) paridade de eventos mom_tf240 vs strategy_search; (3) criterios
congelados (APROVADO/REPROVADO/INCONCLUSIVO); (4) verificador de janela
com 90 dias e protocolo proprio; (5) runner sombra com aprovacao, state,
monitor e replay exclusivos de P6-MOM; (6) avaliador final com 90 dias,
frozen_criteria e recusa cruzada entre protocolos. Dados 100% sinteticos,
rede bloqueada, nenhum artefato real alterado.
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
sys.path.insert(0, str(ROOT / "scripts"))

import check_window_segments as cws  # noqa: E402
import mom_tf240  # noqa: E402
import run_shadow_prospectivo as rsp  # noqa: E402
import run_window_evaluation as rwe  # noqa: E402
import strategy_search as ss  # noqa: E402

MOM_BASE = pd.Timestamp("2026-06-01T00:00:00Z")
WIN90_START = pd.Timestamp("2026-12-01T00:00:00Z")
WIN90_END = WIN90_START + pd.Timedelta(days=90)
WIN90_AFTER = WIN90_END + pd.Timedelta(minutes=5)
BEST_CONFIG = ROOT / "research" / "out" / "strategy_search_20261023T035848Z" / "best_config.json"


@pytest.fixture(autouse=True)
def _block_network(monkeypatch):
    def _deny(*_args, **_kwargs):
        raise AssertionError("REDE BLOQUEADA neste teste")

    monkeypatch.setattr(socket, "socket", _deny)
    monkeypatch.setattr(urllib.request, "urlopen", _deny)


def make_frame(start: pd.Timestamp, minutes: int, seed: int,
               drift_after: int | None = None, drift: float = 0.0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    n = minutes
    ts = pd.date_range(start, periods=n, freq="1min")
    shocks = rng.normal(0.0, 0.0004, n)
    if drift_after is not None:
        shocks = shocks.copy()
        shocks[drift_after:] += drift
    close = 100_000.0 * np.exp(np.cumsum(shocks))
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


# --------------------------------------------------------------------------- #
# 1. Config congelada
# --------------------------------------------------------------------------- #
def test_frozen_config_matches_historical_winner():
    best = json.loads(BEST_CONFIG.read_text(encoding="utf-8"))
    assert best["winner_id"] == "722a0dd140"
    assert best["winner_pass"] is True
    assert mom_tf240.CONFIG == best["winner_cfg"]
    assert mom_tf240.CONFIG == {"family": "momentum", "tf": 240, "lookback": 96, "thr": 0.005}
    assert mom_tf240.VARIANT == "MOM_TF240_LB96"
    assert mom_tf240.PROTOCOL == "P6-MOM"
    assert mom_tf240.WINDOW_DAYS == 90
    assert mom_tf240.RISK_LIMIT_DD == -0.10
    assert mom_tf240.FEE_BPS_P4 == 10.0 and mom_tf240.SLIP_BPS_P4 == 5.0
    assert mom_tf240.FEE_BPS_STRESS == 20.0 and mom_tf240.SLIP_BPS_STRESS == 10.0
    assert mom_tf240.STRESS_ROUND_TRIP_BPS == 60.0


def test_protocols_agree_across_modules():
    assert rsp.PROTOCOLS["P6-MOM"] == {"variant": "MOM_TF240_LB96", "days": 90}
    assert rwe.PROTOCOLS["P6-MOM"] == {"variant": "MOM_TF240_LB96", "days": 90}
    assert rsp.PROTOCOLS["P5"] == rwe.PROTOCOLS["P5"] == {"variant": "M15_original", "days": 30}
    assert cws.PROTOCOL_DAYS["P6-MOM"] == 90
    assert cws.PROTOCOL_DAYS["P5"] == 30
    assert rwe.code_dependencies("P6-MOM") == rwe.P6MOM_CODE_DEPENDENCIES
    assert "research/mom_tf240.py" in rwe.code_dependencies("P6-MOM")
    assert "research/mom_tf240.py" not in rwe.code_dependencies("P5")
    assert "research/mom_tf240.py" in rsp.P6MOM_CODE_DEPENDENCIES
    assert "research/mom_tf240.py" not in rsp.CODE_DEPENDENCIES


# --------------------------------------------------------------------------- #
# 2. Paridade de eventos com a busca historica
# --------------------------------------------------------------------------- #
def test_mom_events_parity_with_strategy_search():
    frame = make_frame(MOM_BASE, 240 * 150, seed=77, drift_after=240 * 60, drift=0.0002)
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], format="ISO8601", utc=True)
    ref_events, info = ss.desired_and_events(frame, dict(mom_tf240.CONFIG))
    mom_events = mom_tf240.build_events(frame)
    assert info["bars"] == 150
    assert mom_events.dtype == np.int8
    assert np.array_equal(ref_events, mom_events)
    assert set(np.unique(mom_events)).issubset({-1, 0, 1})
    assert mom_events.any(), "fixture sem nenhum evento; paridade trivial"


# --------------------------------------------------------------------------- #
# 3. Criterios congelados
# --------------------------------------------------------------------------- #
def passing_metrics(**over) -> dict:
    metrics = {
        "trades": 12,
        "net_total_return": 0.08,
        "buy_and_hold_net": 0.05,
        "max_drawdown_net": -0.06,
        "profit_factor_net": 1.6,
    }
    metrics.update(over)
    return metrics


def test_frozen_criteria_approved_when_all_pass():
    out = mom_tf240.frozen_criteria(passing_metrics(), 0.02)
    assert out["verdict"] == "APROVADO"
    assert all(out["checks"].values())
    assert out["risk_limit_drawdown_net"] == -0.10
    assert out["min_complete_trades_required"] == 10


def test_frozen_criteria_inconclusive_below_min_trades():
    out = mom_tf240.frozen_criteria(passing_metrics(trades=9), 0.02)
    assert out["verdict"] == "INCONCLUSIVO"
    assert out["checks"]["min_complete_trades"] is False


def test_frozen_criteria_reprova_drawdown_below_limit():
    out = mom_tf240.frozen_criteria(passing_metrics(max_drawdown_net=-0.11), 0.02)
    assert out["verdict"] == "REPROVADO"
    assert out["checks"]["max_drawdown_not_below_limit"] is False


def test_frozen_criteria_reprova_stress_nonpositive():
    out = mom_tf240.frozen_criteria(passing_metrics(), -0.001)
    assert out["verdict"] == "REPROVADO"
    assert out["checks"]["stress_60bps_positive"] is False


def test_frozen_criteria_reprova_net_not_above_buyhold():
    out = mom_tf240.frozen_criteria(
        passing_metrics(net_total_return=0.03, buy_and_hold_net=0.05), 0.02
    )
    assert out["verdict"] == "REPROVADO"
    assert out["checks"]["net_above_buy_and_hold"] is False


def test_frozen_criteria_reprova_net_nonpositive():
    out = mom_tf240.frozen_criteria(passing_metrics(net_total_return=0.0), 0.02)
    assert out["verdict"] == "REPROVADO"
    assert out["checks"]["net_positive_after_p4"] is False


def test_frozen_criteria_reprova_pf_below_1_or_missing():
    out = mom_tf240.frozen_criteria(passing_metrics(profit_factor_net=0.9), 0.02)
    assert out["verdict"] == "REPROVADO"
    assert out["checks"]["profit_factor_above_1"] is False
    out_none = mom_tf240.frozen_criteria(passing_metrics(profit_factor_net=None), 0.02)
    assert out_none["verdict"] == "REPROVADO"
    assert out_none["profit_factor_net"] is None


# --------------------------------------------------------------------------- #
# Helpers de manifestos
# --------------------------------------------------------------------------- #
def write_manifest(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def register_p6mom_segment(tmp: Path, day: int) -> Path:
    manifest = tmp / "manifest.jsonl"
    seg_start = WIN90_START + pd.Timedelta(days=day)
    seg_end = seg_start + pd.Timedelta(days=1)
    path = tmp / f"seg_{day:03d}.csv"
    make_frame(seg_start, 1440, seed=9000 + day).to_csv(path, index=False)
    cws.register_segment(
        manifest, path, day, "win_p6mom", "P6-MOM-start",
        WIN90_START.isoformat(), WIN90_END.isoformat(),
        root=tmp, protocol="P6-MOM",
    )
    return manifest


# --------------------------------------------------------------------------- #
# 4. Verificador de janela (F2)
# --------------------------------------------------------------------------- #
def test_register_segment_separates_protocol_spans(tmp_path):
    seg = tmp_path / "day.csv"
    make_frame(WIN90_START, 1440, seed=1).to_csv(seg, index=False)
    manifest = tmp_path / "m.jsonl"
    with pytest.raises(cws.CheckError, match="90 dias"):
        cws.register_segment(
            manifest, seg, 0, "w", "P6-MOM-start",
            WIN90_START.isoformat(), (WIN90_START + pd.Timedelta(days=30)).isoformat(),
            root=tmp_path, protocol="P6-MOM",
        )
    with pytest.raises(cws.CheckError, match="30 dias"):
        cws.register_segment(
            manifest, seg, 0, "w", "P5-start",
            WIN90_START.isoformat(), WIN90_END.isoformat(),
            root=tmp_path, protocol="P5",
        )


def test_verify_manifest_separates_protocols(tmp_path):
    manifest = register_p6mom_segment(tmp_path, 0)
    rep_p6 = cws.verify_manifest(manifest, root=tmp_path, protocol="P6-MOM")
    assert rep_p6["verdict"] == "PASS", rep_p6["reasons"]
    assert rep_p6["protocol"] == "P6-MOM"
    assert rep_p6["expected_days"] == 90
    assert rep_p6["complete_30d"] is False
    assert rep_p6["per_segment"][0]["incomplete_240m_parent_bars"] == 0
    rep_p5 = cws.verify_manifest(manifest, root=tmp_path)
    assert rep_p5["verdict"] == "FAIL"
    assert any("30 dias" in reason for reason in rep_p5["reasons"])


def test_close_window_refuses_report_from_other_protocol(tmp_path):
    manifest = tmp_path / "m.jsonl"
    manifest.write_text('{"record":"segment","prev_sha256":null}\n', encoding="utf-8")
    report = tmp_path / "r.json"
    report.write_text(
        json.dumps({"verdict": "PASS", "protocol": "P6-MOM", "window_id": "w"}),
        encoding="utf-8",
    )
    with pytest.raises(cws.CheckError, match="outro protocolo"):
        cws.close_window(
            manifest, report, tmp_path / "c.csv", root=tmp_path, protocol="P5"
        )


# --------------------------------------------------------------------------- #
# 5. Runner sombra (F3)
# --------------------------------------------------------------------------- #
def p6mom_stub() -> dict:
    return {
        "record_type": "protocolo",
        "id": "P6-MOM",
        "statement": "pre-registro da janela prospectiva de 90 dias MOM_TF240_LB96",
        "source": "memory/journal.md",
        "status": "ativo",
        "recorded_at": "2026-10-23",
    }


def p6mom_approval(**overrides) -> dict:
    record = {
        "record_type": "protocolo",
        "id": "P6-MOM-RISK",
        "statement": "aprovacao do limite de risco da janela P6-MOM",
        "source": "memory/journal.md",
        "status": "ativo",
        "recorded_at": "2026-10-23",
        "protocol_ref": "P6-MOM",
        "risk_limit_approved": True,
        "limit_drawdown_net": -0.10,
        "metric": "max_drawdown_net",
        "scope": "pesquisa prospectiva em sombra; sem ordens reais",
        "window_start_authorized": False,
    }
    record.update(overrides)
    return record


def write_ledger(path: Path, records: list[dict]) -> None:
    path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n",
        encoding="utf-8",
    )


@pytest.fixture
def mom_env(tmp_path, monkeypatch):
    shadow = tmp_path / "shadow"
    monkeypatch.setattr(rsp, "SHADOW_ROOT", shadow)
    out = shadow / "sessao_p6mom"
    ledger = tmp_path / "ledger.jsonl"
    write_ledger(ledger, [p6mom_stub(), p6mom_approval()])
    ref = tmp_path / "aprovacao_p6mom.json"
    ref.write_text(
        json.dumps({
            "ledger": str(ledger),
            "record_id": "P6-MOM-RISK",
            "protocol_ref": "P6-MOM",
            "limit_drawdown_net": -0.10,
        }),
        encoding="utf-8",
    )
    seg0 = tmp_path / "seg0.csv"
    make_frame(MOM_BASE, 600, seed=21).to_csv(seg0, index=False)
    seg1 = tmp_path / "seg1.csv"
    make_frame(MOM_BASE + pd.Timedelta(minutes=600), 600, seed=22).to_csv(seg1, index=False)
    return {
        "tmp": tmp_path,
        "shadow": shadow,
        "out": out,
        "ledger": ledger,
        "ref": ref,
        "seg0": seg0,
        "seg1": seg1,
    }


def mom_argv(env, segment: Path, protocol: str | None = None) -> list[str]:
    argv = [
        "--segment", str(segment),
        "--out", str(env["out"]),
        "--risk-approval", str(env["ref"]),
        "--ledger", str(env["ledger"]),
    ]
    if protocol is not None:
        argv += ["--protocol", protocol]
    return argv


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


def read_events(out: Path) -> list[dict]:
    path = out / "events.jsonl"
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_p6mom_runner_happy_first_segment(mom_env, monkeypatch, capsys):
    with read_spy(monkeypatch) as reads:
        rc = rsp.main(mom_argv(mom_env, mom_env["seg0"], "P6-MOM"))
    assert rc == 0
    allowed = {
        str(mom_env["ref"].resolve()), str(mom_env["ledger"].resolve()),
        str(mom_env["seg0"].resolve()),
        str((mom_env["out"] / "state.json").resolve()),
    } | {str((rsp.ROOT / rel).resolve()) for rel in rsp.P6MOM_CODE_DEPENDENCIES}
    unexpected = [path for path in reads if path not in allowed]
    assert not unexpected, f"leituras fora do conjunto fechado: {unexpected}"
    for path in reads:
        norm = path.replace("\\", "/")
        assert "/data/raw/" not in norm, f"CSV historico aberto: {path}"
        assert "/research/out/" not in norm, f"relatorio de pesquisa aberto: {path}"
        assert not norm.endswith("journal.md"), f"journal aberto: {path}"

    state = json.loads((mom_env["out"] / "state.json").read_text(encoding="utf-8"))
    monitor = json.loads(
        (mom_env["out"] / "risk_monitor.json").read_text(encoding="utf-8")
    )
    assert state["protocol"] == "P6-MOM"
    assert state["variant"] == "MOM_TF240_LB96"
    assert state["window_id"] == "prospective_90d"
    assert state["segments"] == [str(mom_env["seg0"].resolve())]
    assert "research/mom_tf240.py" in state["code_manifest"]
    assert set(state["code_manifest"]) == set(rsp.P6MOM_CODE_DEPENDENCIES)
    assert state["costs"] == {"fee_bps_per_side": 10.0, "slippage_bps_per_side": 5.0}
    assert monitor["protocol"] == "P6-MOM"
    assert monitor["limit_drawdown_net"] == -0.10
    assert monitor["breached"] is False
    assert isinstance(monitor["max_drawdown_net"], float)
    assert read_events(mom_env["out"]) == []

    out_lines = capsys.readouterr().out
    for term in ("sharpe", "net_total", "%", "profit"):
        assert term not in out_lines.lower(), f"metrica divulgada no stdout: {term}"


def test_p6mom_runner_resume_second_segment(mom_env):
    assert rsp.main(mom_argv(mom_env, mom_env["seg0"], "P6-MOM")) == 0
    assert rsp.main(mom_argv(mom_env, mom_env["seg1"], "P6-MOM")) == 0
    state = json.loads((mom_env["out"] / "state.json").read_text(encoding="utf-8"))
    assert state["segments"] == [
        str(mom_env["seg0"].resolve()), str(mom_env["seg1"].resolve())
    ]
    assert state["last_timestamp"] == (
        MOM_BASE + pd.Timedelta(minutes=1199)
    ).isoformat()


def test_p5_approval_refused_for_p6mom_protocol(mom_env, tmp_path):
    p5_ref = tmp_path / "ref_p5.json"
    p5_ref.write_text(
        json.dumps({
            "ledger": str(mom_env["ledger"]),
            "record_id": "P6-MOM-RISK",
            "protocol_ref": "P5",
            "limit_drawdown_net": -0.10,
        }),
        encoding="utf-8",
    )
    rc = rsp.main([
        "--segment", str(mom_env["seg0"]),
        "--out", str(mom_env["out"]),
        "--risk-approval", str(p5_ref),
        "--ledger", str(mom_env["ledger"]),
        "--protocol", "P6-MOM",
    ])
    assert rc == 2
    assert not mom_env["out"].exists()


def test_p6mom_approval_refused_for_p5_protocol(mom_env):
    rc = rsp.main(mom_argv(mom_env, mom_env["seg0"], "P5"))
    assert rc == 2
    assert not mom_env["out"].exists()


def test_p6mom_session_resumed_as_p5_is_fatal(mom_env, tmp_path):
    assert rsp.main(mom_argv(mom_env, mom_env["seg0"], "P6-MOM")) == 0
    state_before = (mom_env["out"] / "state.json").read_bytes()
    monitor_before = (mom_env["out"] / "risk_monitor.json").read_bytes()
    p5_stub = {
        "record_type": "protocolo",
        "id": "P5",
        "statement": "pre-registro P5",
        "source": "memory/journal.md",
        "status": "ativo",
        "recorded_at": "2026-10-22",
    }
    p5_risk = {
        "record_type": "protocolo",
        "id": "P5-RISK",
        "statement": "aprovacao do limite de risco da janela",
        "source": "memory/journal.md",
        "status": "ativo",
        "recorded_at": "2026-10-23",
        "protocol_ref": "P5",
        "risk_limit_approved": True,
        "limit_drawdown_net": -0.10,
    }
    ledger = tmp_path / "ledger_both.jsonl"
    write_ledger(ledger, [p5_stub, p5_risk, p6mom_stub(), p6mom_approval()])
    p5_ref = tmp_path / "ref_p5.json"
    p5_ref.write_text(
        json.dumps({
            "ledger": str(ledger),
            "record_id": "P5-RISK",
            "protocol_ref": "P5",
            "limit_drawdown_net": -0.10,
        }),
        encoding="utf-8",
    )
    rc = rsp.main([
        "--segment", str(mom_env["seg1"]),
        "--out", str(mom_env["out"]),
        "--risk-approval", str(p5_ref),
        "--ledger", str(ledger),
        "--protocol", "P5",
    ])
    assert rc == 4
    assert (mom_env["out"] / "state.json").read_bytes() == state_before
    assert (mom_env["out"] / "risk_monitor.json").read_bytes() == monitor_before
    events = read_events(mom_env["out"])
    assert [e["event"] for e in events] == ["FATAL_SESSION_STOP"]
    assert "protocolo" in events[0]["detail"]


def test_p6mom_replay_matches_direct_mom_backtest():
    frame = make_frame(MOM_BASE, 240 * 110, seed=33, drift_after=240 * 62, drift=0.0002)
    max_dd, position = rsp._replay(frame, "MOM_TF240_LB96")
    events = mom_tf240.build_events(frame)
    assert events.any(), "fixture sem eventos; replay trivial"
    frame_dt = frame.copy()
    frame_dt["timestamp"] = pd.to_datetime(
        frame_dt["timestamp"], format="ISO8601", utc=True
    )
    bt, metrics = rsp.run_research.run_one(
        frame_dt, events, rsp.run_research.COST_SCENARIOS[1]
    )
    assert max_dd == pytest.approx(float(metrics["max_drawdown_net"]), abs=1e-12)
    assert position == pytest.approx(
        float(pd.to_numeric(bt["position"]).iloc[-1]), abs=1e-12
    )


def test_p6mom_risk_breach_wires_event_and_exit(mom_env, monkeypatch, capsys):
    monkeypatch.setattr(rsp, "_replay", lambda candles, variant=None: (-0.55, 0.0))
    rc = rsp.main(mom_argv(mom_env, mom_env["seg0"], "P6-MOM"))
    assert rc == 3
    monitor = json.loads(
        (mom_env["out"] / "risk_monitor.json").read_text(encoding="utf-8")
    )
    assert monitor["protocol"] == "P6-MOM"
    assert monitor["breached"] is True
    assert monitor["max_drawdown_net"] == pytest.approx(-0.55, abs=1e-12)
    assert monitor["limit_drawdown_net"] == -0.10
    events = read_events(mom_env["out"])
    assert [e["event"] for e in events] == ["RISK_LIMIT_BREACHED"]
    assert "nao e resultado" in events[0]["detail"]
    assert "INTERRUPCAO: RISK_LIMIT_BREACHED" in capsys.readouterr().out
    state = json.loads((mom_env["out"] / "state.json").read_text(encoding="utf-8"))
    assert state["segments"] == [str(mom_env["seg0"].resolve())]


def test_p6mom_risk_breach_boundary_equal_limit(mom_env, monkeypatch):
    monkeypatch.setattr(rsp, "_replay", lambda candles, variant=None: (-0.10, 0.0))
    rc = rsp.main(mom_argv(mom_env, mom_env["seg0"], "P6-MOM"))
    assert rc == 3
    monitor = json.loads(
        (mom_env["out"] / "risk_monitor.json").read_text(encoding="utf-8")
    )
    assert monitor["breached"] is True


def test_p6mom_p5_record_cannot_grant_p6mom_risk(mom_env, tmp_path):
    ledger = tmp_path / "ledger_p5only.jsonl"
    write_ledger(ledger, [
        p6mom_stub(),
        {
            "record_type": "protocolo",
            "id": "P5-RISK",
            "statement": "aprovacao P5",
            "source": "memory/journal.md",
            "status": "ativo",
            "recorded_at": "2026-10-23",
            "protocol_ref": "P5",
            "risk_limit_approved": True,
            "limit_drawdown_net": -0.10,
        },
    ])
    ref = tmp_path / "ref_p5risk.json"
    ref.write_text(
        json.dumps({
            "ledger": str(ledger),
            "record_id": "P5-RISK",
            "protocol_ref": "P6-MOM",
            "limit_drawdown_net": -0.10,
        }),
        encoding="utf-8",
    )
    rc = rsp.main([
        "--segment", str(mom_env["seg0"]),
        "--out", str(mom_env["out"]),
        "--risk-approval", str(ref),
        "--ledger", str(ledger),
        "--protocol", "P6-MOM",
    ])
    assert rc == 2


# --------------------------------------------------------------------------- #
# 6. Avaliador final (F1)
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def full_closed_90(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("win90eval")
    mp = pytest.MonkeyPatch()
    mp.setattr(cws, "_utc_now", lambda: WIN90_AFTER.to_pydatetime())
    try:
        manifest = tmp / "manifest.jsonl"
        for day in range(90):
            register_p6mom_segment(tmp, day)
        report_path = tmp / "integrity.json"
        report = cws.verify_manifest(manifest, root=tmp, protocol="P6-MOM")
        assert report["verdict"] == "PASS", report["reasons"]
        assert report["complete_30d"] is True
        cws.write_report(report, report_path)
        consolidated = tmp / "consolidated_1m.csv"
        closure = cws.close_window(
            manifest, report_path, consolidated, root=tmp, protocol="P6-MOM"
        )
        yield {
            "tmp": tmp,
            "manifest": manifest,
            "report": report_path,
            "consolidated": consolidated,
            "closure": closure,
        }
    finally:
        mp.undo()


def p6_argv(fixture, out_dir: Path) -> list[str]:
    return [
        "--csv", str(fixture["consolidated"]),
        "--manifest", str(fixture["manifest"]),
        "--integrity-report", str(fixture["report"]),
        "--out", str(out_dir),
        "--protocol", "P6-MOM",
    ]


def test_p6mom_evaluator_happy_path(full_closed_90, tmp_path, monkeypatch):
    monkeypatch.setattr(rwe, "_utc_now", lambda: WIN90_AFTER.to_pydatetime())
    out_dir = tmp_path / "window_evaluation"
    audit = {
        name: cws.sha256_file(ROOT / "research" / "out" / name)
        for name in ("research_results.json", "csv_integrity.json")
    }
    before_files = sorted(p.name for p in (ROOT / "research" / "out").iterdir())
    with read_spy(monkeypatch) as reads:
        rc = rwe.main(p6_argv(full_closed_90, out_dir))
    assert rc == 0
    allowed = {
        str(full_closed_90["consolidated"].resolve()),
        str(full_closed_90["manifest"].resolve()),
        str(full_closed_90["report"].resolve()),
    } | {str((ROOT / rel).resolve()) for rel in rwe.P6MOM_CODE_DEPENDENCIES}
    unexpected = {path for path in reads} - allowed
    assert not unexpected, f"leituras fora do conjunto fechado: {unexpected}"
    for path in reads:
        norm = path.replace("\\", "/")
        assert "/data/raw/" not in norm, f"CSV historico aberto: {path}"
        assert "/research/out/" not in norm, f"relatorio de pesquisa aberto: {path}"

    outputs = sorted(out_dir.glob("window_evaluation_P6-MOM_*.json"))
    assert len(outputs) == 1
    result = json.loads(outputs[0].read_text(encoding="utf-8"))
    assert result["report"] == "window_evaluation"
    assert result["protocol"] == "P6-MOM"
    assert result["variant"] == "MOM_TF240_LB96"
    assert result["window"]["days"] == 90
    assert result["window"]["start_utc"] == WIN90_START.isoformat()
    assert result["data"]["csv_rows"] == 90 * 1440
    assert result["config"] == mom_tf240.CONFIG
    assert "selection_note" in result
    assert "nao garante resultado futuro" in result["selection_note"]
    assert "research/mom_tf240.py" in result["code_hashes"]
    assert "original_config" not in result
    frozen = result["frozen_criteria"]
    assert frozen["verdict"] in {"APROVADO", "REPROVADO", "INCONCLUSIVO"}
    assert frozen["risk_limit_drawdown_net"] == -0.10
    assert frozen["min_complete_trades_required"] == 10
    assert result["costs"]["fee_bps_per_side"] == 10.0
    assert result["costs"]["slippage_bps_per_side"] == 5.0
    assert result["costs"]["round_trip_bps"] == 30.0
    assert "net_total_return" in result["metrics"]
    assert "net_total_return" in result["metrics_stress_60bps"]
    for name, digest in audit.items():
        assert cws.sha256_file(ROOT / "research" / "out" / name) == digest
    after_files = sorted(p.name for p in (ROOT / "research" / "out").iterdir())
    assert after_files == before_files


def test_evaluator_p6mom_closure_refused_under_p5_protocol(full_closed_90, tmp_path, monkeypatch):
    monkeypatch.setattr(rwe, "_utc_now", lambda: WIN90_AFTER.to_pydatetime())
    out_p5 = tmp_path / "window_evaluation"
    rc = rwe.main([
        "--csv", str(full_closed_90["consolidated"]),
        "--manifest", str(full_closed_90["manifest"]),
        "--integrity-report", str(full_closed_90["report"]),
        "--out", str(out_p5),
    ])
    assert rc == 2
    assert not list(out_p5.glob("window_evaluation_*.json")) if out_p5.exists() else True


def minimal_chain(closure_overrides: dict) -> list[dict]:
    overrides = dict(closure_overrides)
    days = int(overrides.get("days", 30))
    entries: list[dict] = []
    for seq in range(days):
        entry = {
            "record": "segment",
            "seq": seq,
            "file": f"s{seq:03d}.csv",
            "sha256": f"{seq:064x}"[-64:],
            "prev_sha256": rwe.canonical_sha256(entries[-1]) if entries else None,
        }
        entries.append(entry)
    end = WIN90_START + pd.Timedelta(days=days)
    closure = {
        "record": "window_closed",
        "prev_sha256": rwe.canonical_sha256(entries[-1]),
        "protocol": "P5",
        "window_id": "w",
        "start_record_id": "s",
        "window_start_utc": WIN90_START.isoformat(),
        "window_end_utc": end.isoformat(),
        "closed_at_utc": (end + pd.Timedelta(minutes=5)).isoformat(),
        "days": days,
        "segments": [
            {"seq": e["seq"], "file": e["file"], "sha256": e["sha256"]}
            for e in entries
        ],
    }
    closure.update(overrides)
    entries.append(closure)
    return entries


def test_evaluator_cli_p5_closure_refused_under_p6mom(tmp_path):
    manifest = tmp_path / "manifest.jsonl"
    write_manifest(manifest, [json.dumps(e) for e in minimal_chain({})])
    rc = rwe.main([
        "--csv", str(tmp_path / "nao_existe.csv"),
        "--manifest", str(manifest),
        "--integrity-report", str(tmp_path / "r.json"),
        "--out", str(tmp_path / "window_evaluation"),
        "--protocol", "P6-MOM",
    ])
    assert rc == 2


def test_evaluator_cli_p6mom_closure_refused_under_p5(tmp_path):
    closure_overrides = {
        "protocol": "P6-MOM",
        "days": 90,
        "window_end_utc": WIN90_END.isoformat(),
        "closed_at_utc": WIN90_AFTER.isoformat(),
    }
    manifest = tmp_path / "manifest.jsonl"
    write_manifest(manifest, [json.dumps(e) for e in minimal_chain(closure_overrides)])
    rc = rwe.main([
        "--csv", str(tmp_path / "nao_existe.csv"),
        "--manifest", str(manifest),
        "--integrity-report", str(tmp_path / "r.json"),
        "--out", str(tmp_path / "window_evaluation"),
    ])
    assert rc == 2


def test_validate_closure_separates_days_and_protocol():
    entries_p5 = minimal_chain({})
    closure = rwe.validate_closure(entries_p5, "P5")
    assert closure["protocol"] == "P5"
    with pytest.raises(rwe.EvaluationRefused, match="protocolo P6-MOM"):
        rwe.validate_closure(entries_p5, "P6-MOM")
    entries_p6 = minimal_chain({
        "protocol": "P6-MOM",
        "days": 90,
        "window_end_utc": WIN90_END.isoformat(),
        "closed_at_utc": WIN90_AFTER.isoformat(),
    })
    with pytest.raises(rwe.EvaluationRefused, match="protocolo P5"):
        rwe.validate_closure(entries_p6, "P5")
    with pytest.raises(rwe.EvaluationRefused, match="90 dias"):
        rwe.validate_closure(minimal_chain({"protocol": "P6-MOM"}), "P6-MOM")
