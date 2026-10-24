"""Testes do CLI de download de klines: janela, aliases de caminho e temporarios.

Sem rede: toda resposta da API e simulada. Escritas ocorrem apenas em tmp_path
(dl.ROOT e redirecionado) ou, para os testes de subprocesso do CLI, em erro de
validacao antecedido a qualquer criacao de diretorio (sentinela confere).
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
DL_PATH = ROOT / "scripts" / "download_klines.py"

_spec = importlib.util.spec_from_file_location("download_klines_under_test", DL_PATH)
dl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dl)

IS_NT = os.name == "nt"
UTC = timezone.utc
FIXED_NOW_MS = 1_770_000_000_000
WIN_START = 1_769_996_400_000


def _fixed_clock(monkeypatch) -> None:
    monkeypatch.setattr(dl, "last_complete_minute_ms", lambda now_ms=None: FIXED_NOW_MS)


def _frame(start_ms: int, end_ms: int, drop: set[int] | None = None) -> pd.DataFrame:
    drop = drop or set()
    count = (end_ms - start_ms) // dl.ONE_MINUTE_MS + 1
    start = pd.to_datetime(start_ms, unit="ms", utc=True)
    stamps = [ts for i, ts in enumerate(pd.date_range(start, periods=count, freq="min")) if i not in drop]
    return pd.DataFrame({
        "timestamp": stamps,
        "open": [100.0] * len(stamps),
        "high": [101.0] * len(stamps),
        "low": [99.0] * len(stamps),
        "close": [100.5] * len(stamps),
        "volume": [10.0] * len(stamps),
        "close_time": [ts + pd.Timedelta(minutes=1) - pd.Timedelta(milliseconds=1) for ts in stamps],
        "quote_volume": [1000.0] * len(stamps),
        "trades": [50] * len(stamps),
        "taker_buy_base_volume": [5.0] * len(stamps),
        "taker_buy_quote_volume": [500.0] * len(stamps),
    })


def _api_rows(start_ms: int, count: int, offset: int = 0) -> list[list]:
    rows = []
    for i in range(count):
        open_ms = start_ms + (offset + i) * dl.ONE_MINUTE_MS
        rows.append([open_ms, 100.0, 101.0, 99.0, 100.5, 10.0, open_ms + 59_999,
                     1000.0, 50, 5.0, 500.0, 0])
    return rows


def _tree_state() -> dict[str, tuple[int, int]]:
    state: dict[str, tuple[int, int]] = {}
    for base in (ROOT / "data" / "raw", ROOT / "reports", ROOT / "research" / "out"):
        if not base.is_dir():
            state[f"absent:{base}"] = (0, 0)
            continue
        for path in sorted(base.rglob("*")):
            if path.is_file():
                stat = path.stat()
                state[str(path)] = (stat.st_size, stat.st_mtime_ns)
    return state


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        [sys.executable, str(DL_PATH), *args],
        capture_output=True, text=True, cwd=str(ROOT), env=env, timeout=180,
    )


def _short_alias(path: Path) -> Path | None:
    if not IS_NT:
        return None
    import ctypes
    buf = ctypes.create_unicode_buffer(65_536)
    length = ctypes.windll.kernel32.GetShortPathNameW(str(path), buf, 65_536)
    if not length:
        return None
    short = Path(buf.value)
    if dl._path_key(short) == dl._path_key(path):
        return None
    return short


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def read(self):
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    monkeypatch.setattr(dl, "ROOT", tmp_path)
    return tmp_path


# ---------------------------------------------------------------------------
# CLI via subprocess (arvore real): regressao do H1 + sentinela de escrita
# ---------------------------------------------------------------------------

def test_cli_bootstrap_registers_src_on_sys_path():
    expected = str(DL_PATH.resolve().parents[1] / "src")
    assert expected in sys.path, "H1: o CLI precisa injetar src/ antes de importar convergencia"


def test_cli_help_exits_zero_without_artifacts():
    before = _tree_state()
    proc = _run_cli("--help")
    assert proc.returncode == 0, proc.stderr
    assert "usage:" in proc.stdout
    assert "--start" in proc.stdout and "--overwrite" in proc.stdout
    assert _tree_state() == before


def test_cli_rejects_bad_symbol_without_artifacts():
    before = _tree_state()
    proc = _run_cli("--symbol", "BTC USDT")
    assert proc.returncode == 2, (proc.stdout, proc.stderr)
    assert "symbol deve conter apenas letras e numeros" in proc.stderr
    assert _tree_state() == before


def test_cli_requires_end_with_start():
    before = _tree_state()
    proc = _run_cli("--start", "2026-01-01")
    assert proc.returncode == 2, (proc.stdout, proc.stderr)
    assert "--start e --end devem ser informados juntos" in proc.stderr
    assert _tree_state() == before


def test_cli_rejects_days_combined_with_window():
    before = _tree_state()
    proc = _run_cli("--days", "5", "--start", "2026-01-01", "--end", "2026-01-02")
    assert proc.returncode == 2, (proc.stdout, proc.stderr)
    assert "mutuamente exclusivos" in proc.stderr
    assert _tree_state() == before


# ---------------------------------------------------------------------------
# Helpers de tempo e janela
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("now_ms,expected", [
    (1_770_000_000_000, 1_769_999_940_000),
    (1_770_000_029_999, 1_769_999_940_000),
    (1_770_000_059_999, 1_769_999_940_000),
    (1_770_000_060_000, 1_770_000_000_000),
])
def test_last_complete_minute_ms_excludes_forming_candle(now_ms, expected):
    assert dl.last_complete_minute_ms(now_ms) == expected
    assert dl.last_complete_minute_ms(now_ms) % dl.ONE_MINUTE_MS == 0


@pytest.mark.parametrize("value,expected", [
    ("2026-10-23", datetime(2026, 10, 23, 0, 0, 0, tzinfo=UTC)),
    ("2026-10-23T00:00", datetime(2026, 10, 23, 0, 0, 0, tzinfo=UTC)),
    ("2026-10-23T00:00:00", datetime(2026, 10, 23, 0, 0, 0, tzinfo=UTC)),
    ("2026-10-23T00:00:00Z", datetime(2026, 10, 23, 0, 0, 0, tzinfo=UTC)),
    ("2026-10-23T00:00:00.000Z", datetime(2026, 10, 23, 0, 0, 0, tzinfo=UTC)),
    ("2026-10-23T02:00:00+02:00", datetime(2026, 10, 23, 0, 0, 0, tzinfo=UTC)),
])
def test_parse_utc_moment_accepts_iso_forms(value, expected):
    parsed = dl.parse_utc_moment(value)
    assert parsed == expected
    assert parsed.utcoffset() == timedelta(0)


@pytest.mark.parametrize("value", ["", "   ", "not-a-date", "2026-13-01", "23/10/2026"])
def test_parse_utc_moment_rejects_invalid(value):
    with pytest.raises(argparse.ArgumentTypeError, match="momento invalido"):
        dl.parse_utc_moment(value)


def test_explicit_window_ms_aligns_to_minutes_and_counts():
    start = datetime(2026, 1, 1, 0, 0, 30, tzinfo=UTC)
    end = datetime(2026, 1, 1, 0, 4, 59, tzinfo=UTC)
    start_ms, end_ms = dl.explicit_window_ms(start, end, now_ms=FIXED_NOW_MS)
    assert start_ms % dl.ONE_MINUTE_MS == 0
    assert end_ms % dl.ONE_MINUTE_MS == 0
    assert (end_ms - start_ms) // dl.ONE_MINUTE_MS + 1 == 5
    assert pd.to_datetime(start_ms, unit="ms", utc=True).hour == 0


def test_explicit_window_ms_rejects_end_before_start():
    start = datetime(2026, 1, 1, 0, 5, 0, tzinfo=UTC)
    end = datetime(2026, 1, 1, 0, 1, 0, tzinfo=UTC)
    with pytest.raises(ValueError, match="--end anterior a --start"):
        dl.explicit_window_ms(start, end, now_ms=FIXED_NOW_MS)


def test_explicit_window_ms_rejects_forming_candle():
    start = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
    end = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)
    with pytest.raises(ValueError, match="ainda em formacao"):
        dl.explicit_window_ms(start, end, now_ms=FIXED_NOW_MS)


def test_explicit_window_ms_rejects_oversize_window():
    start = datetime(2020, 1, 1, tzinfo=UTC)
    end = datetime(2026, 1, 1, tzinfo=UTC)
    with pytest.raises(ValueError, match="excede 365 dias"):
        dl.explicit_window_ms(start, end, now_ms=FIXED_NOW_MS)


def test_resolve_window_days_mode_uses_last_complete_minute():
    args = dl.build_parser().parse_args(["--days", "2"])
    start_ms, end_ms, mode = dl.resolve_window(args, now_ms=FIXED_NOW_MS)
    assert mode == "days"
    assert end_ms == dl.last_complete_minute_ms(FIXED_NOW_MS)
    assert start_ms == end_ms - (2 * 1440 - 1) * dl.ONE_MINUTE_MS


def test_resolve_window_defaults_to_90_days():
    args = dl.build_parser().parse_args([])
    _, _, mode = dl.resolve_window(args, now_ms=FIXED_NOW_MS)
    assert args.days == 90
    assert mode == "days"


def test_resolve_window_requires_both_bounds():
    args = dl.build_parser().parse_args(["--start", "2026-01-01"])
    with pytest.raises(ValueError, match="--start e --end devem ser informados juntos"):
        dl.resolve_window(args, now_ms=FIXED_NOW_MS)
    args = dl.build_parser().parse_args(["--end", "2026-01-01"])
    with pytest.raises(ValueError, match="--start e --end devem ser informados juntos"):
        dl.resolve_window(args, now_ms=FIXED_NOW_MS)


def test_resolve_window_rejects_days_combined_with_window():
    args = dl.build_parser().parse_args(
        ["--days", "5", "--start", "2026-01-01", "--end", "2026-01-02"]
    )
    with pytest.raises(ValueError, match="mutuamente exclusivos"):
        dl.resolve_window(args, now_ms=FIXED_NOW_MS)


# ---------------------------------------------------------------------------
# Validacao do CLI
# ---------------------------------------------------------------------------

def test_validate_cli_rejects_bad_symbol(sandbox):
    args = dl.build_parser().parse_args(["--symbol", "BTC USDT"])
    with pytest.raises(ValueError, match="symbol deve conter apenas letras e numeros"):
        dl.validate_cli(args, now_ms=FIXED_NOW_MS)


@pytest.mark.parametrize("days", ["0", "366"])
def test_validate_cli_rejects_days_out_of_range(sandbox, days):
    args = dl.build_parser().parse_args(["--days", days])
    with pytest.raises(ValueError, match="days deve estar entre 1 e 365"):
        dl.validate_cli(args, now_ms=FIXED_NOW_MS)


def test_validate_cli_existing_target_requires_overwrite(sandbox):
    csv = sandbox / "data" / "raw" / "TESTEX_1m.csv"
    csv.parent.mkdir(parents=True)
    csv.write_text("SENTINELA", encoding="utf-8")
    args = dl.build_parser().parse_args(["--symbol", "TESTEX", "--days", "1"])
    with pytest.raises(ValueError, match="ja existe"):
        dl.validate_cli(args, now_ms=FIXED_NOW_MS)
    assert csv.read_text(encoding="utf-8") == "SENTINELA"
    args = dl.build_parser().parse_args(
        ["--symbol", "TESTEX", "--days", "1", "--overwrite"]
    )
    plan = dl.validate_cli(args, now_ms=FIXED_NOW_MS)
    assert plan.csv_path == csv
    assert csv.read_text(encoding="utf-8") == "SENTINELA"


def test_validate_cli_plan_uses_pid_scoped_unique_temps(sandbox):
    args = dl.build_parser().parse_args(
        ["--symbol", "TESTEX", "--days", "1", "--overwrite"]
    )
    plan = dl.validate_cli(args, now_ms=FIXED_NOW_MS)
    assert plan.temp_csv.name == f"TESTEX_1m.csv.tmp-{os.getpid()}"
    assert plan.temp_report.name == f"data_quality_TESTEX_1m.json.tmp-{os.getpid()}"
    assert plan.temp_csv not in (plan.csv_path, plan.report_path, plan.temp_report)
    assert plan.temp_report not in (plan.csv_path, plan.report_path, plan.temp_csv)
    assert plan.mode == "days"
    assert plan.start_ms < plan.end_ms
    assert plan.end_ms == dl.last_complete_minute_ms(FIXED_NOW_MS)


# ---------------------------------------------------------------------------
# Aliases e colisao de caminhos
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not IS_NT, reason="normalizacao de aliases e especifica do Windows")
def test_path_key_normalizes_prefix_separators_case_and_trailing():
    extended = dl._path_key(Path("\\\\?\\C:\\Dados\\BTCUSDT_1M.CSV "))
    plain = dl._path_key(Path("c:/dados/btcusdt_1m.csv"))
    dotted = dl._path_key(Path("c:/dados/btcusdt_1m.csv."))
    assert extended == plain == dotted


def test_resolved_key_sees_relative_aliases(tmp_path):
    target = tmp_path / "sub" / "BTCUSDT_1m.csv"
    target.parent.mkdir(parents=True)
    target.write_text("x", encoding="utf-8")
    base = dl._resolved_key(target)
    assert dl._resolved_key(tmp_path / "sub" / ".." / "sub" / "BTCUSDT_1m.csv") == base
    if IS_NT:
        assert dl._resolved_key(Path("\\\\?\\" + str(target))) == base
        assert dl._resolved_key(Path(str(target).upper())) == base


def test_check_path_collisions_detects_duplicate_target(tmp_path):
    target = tmp_path / "a.csv"
    with pytest.raises(ValueError, match="colisao de caminhos"):
        dl.check_path_collisions([target, target])


def test_check_path_collisions_allows_distinct_paths(tmp_path):
    dl.check_path_collisions([
        tmp_path / "a.csv",
        tmp_path / "b.csv",
        tmp_path / "a.csv.tmp-1",
    ])


@pytest.mark.skipif(not IS_NT, reason="aliases fisicos sao especificos do Windows")
def test_check_path_collisions_detects_existing_aliases(tmp_path):
    target = tmp_path / "BTCUSDT_1m.csv"
    target.write_text("x", encoding="utf-8")
    aliases = [
        Path(str(target).upper()),
        Path("\\\\?\\" + str(target)),
        Path(str(target) + "."),
        Path(str(target) + " "),
    ]
    for alias in aliases:
        with pytest.raises(ValueError, match="colisao de caminhos"):
            dl.check_path_collisions([target, alias])


@pytest.mark.skipif(not IS_NT, reason="nome curto 8.3 e especifico do Windows")
def test_check_path_collisions_detects_83_alias(tmp_path):
    target = tmp_path / "BTCUSDT_1m.csv"
    target.write_text("x", encoding="utf-8")
    alias = _short_alias(target)
    if alias is None:
        pytest.skip("8.3 desativado neste volume")
    with pytest.raises(ValueError, match="colisao de caminhos"):
        dl.check_path_collisions([target, alias])


# ---------------------------------------------------------------------------
# Camada de rede (urlopen simulada)
# ---------------------------------------------------------------------------

def test_fetch_page_returns_payload(monkeypatch):
    rows = _api_rows(WIN_START, 3)
    monkeypatch.setattr(dl, "urlopen", lambda *a, **k: _FakeResponse(rows))
    assert dl.fetch_page("BTCUSDT", WIN_START, WIN_START + 2 * dl.ONE_MINUTE_MS) == rows


def test_fetch_page_rejects_non_list_payload_after_retries(monkeypatch):
    calls = {"n": 0}
    slept: list[int] = []

    def fake_urlopen(*args, **kwargs):
        calls["n"] += 1
        return _FakeResponse({"code": -1121, "msg": "Invalid symbol."})

    monkeypatch.setattr(dl, "urlopen", fake_urlopen)
    monkeypatch.setattr(dl.time, "sleep", slept.append)
    with pytest.raises(RuntimeError, match="5 tentativas"):
        dl.fetch_page("BTCUSDT", WIN_START, WIN_START)
    assert calls["n"] == 5
    assert slept == [1, 2, 4, 8]


def test_fetch_page_rejects_short_row_after_retries(monkeypatch):
    calls = {"n": 0}

    def fake_urlopen(*args, **kwargs):
        calls["n"] += 1
        return _FakeResponse([[1, 2, 3]])

    monkeypatch.setattr(dl, "urlopen", fake_urlopen)
    monkeypatch.setattr(dl.time, "sleep", lambda seconds: None)
    with pytest.raises(RuntimeError, match="5 tentativas"):
        dl.fetch_page("BTCUSDT", WIN_START, WIN_START)
    assert calls["n"] == 5


def test_fetch_page_retries_transient_error_then_succeeds(monkeypatch):
    rows = _api_rows(WIN_START, 2)
    calls = {"n": 0}
    slept: list[int] = []

    def fake_urlopen(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise URLError("rede instavel")
        return _FakeResponse(rows)

    monkeypatch.setattr(dl, "urlopen", fake_urlopen)
    monkeypatch.setattr(dl.time, "sleep", slept.append)
    assert dl.fetch_page("BTCUSDT", WIN_START, WIN_START + dl.ONE_MINUTE_MS) == rows
    assert calls["n"] == 2
    assert slept == [1]


def test_fetch_page_raises_immediately_on_client_http_error(monkeypatch):
    calls = {"n": 0}
    slept: list[int] = []

    def fake_urlopen(*args, **kwargs):
        calls["n"] += 1
        raise HTTPError("https://example.invalid", 404, "Not Found", None, None)

    monkeypatch.setattr(dl, "urlopen", fake_urlopen)
    monkeypatch.setattr(dl.time, "sleep", slept.append)
    with pytest.raises(RuntimeError, match="HTTP 404"):
        dl.fetch_page("BTCUSDT", WIN_START, WIN_START)
    assert calls["n"] == 1
    assert slept == []


# ---------------------------------------------------------------------------
# fetch_window (fetch_page simulada)
# ---------------------------------------------------------------------------

def test_fetch_window_paginates_with_strictly_advancing_cursors(monkeypatch):
    count = 2500
    end = WIN_START + (count - 1) * dl.ONE_MINUTE_MS
    all_rows = _api_rows(WIN_START, count)
    calls: list[int] = []

    def fake_fetch(symbol, start_ms, end_ms, timeout=20):
        calls.append(start_ms)
        page = [row for row in all_rows if start_ms <= row[0] <= end_ms]
        return page[: dl.LIMIT]

    monkeypatch.setattr(dl, "fetch_page", fake_fetch)
    monkeypatch.setattr(dl.time, "sleep", lambda seconds: None)
    frame = dl.fetch_window("TESTEX", WIN_START, end)
    assert len(frame) == count
    assert calls == [
        WIN_START,
        WIN_START + 1000 * dl.ONE_MINUTE_MS,
        WIN_START + 2000 * dl.ONE_MINUTE_MS,
    ]
    assert frame["timestamp"].is_monotonic_increasing
    assert frame["timestamp"].iloc[0] == pd.to_datetime(WIN_START, unit="ms", utc=True)
    assert frame["timestamp"].iloc[-1] == pd.to_datetime(end, unit="ms", utc=True)


def test_fetch_window_stops_on_short_page(monkeypatch):
    all_rows = _api_rows(WIN_START, 50)
    calls = {"n": 0}

    def fake_fetch(symbol, start_ms, end_ms, timeout=20):
        calls["n"] += 1
        return [row for row in all_rows if start_ms <= row[0] <= end_ms]

    monkeypatch.setattr(dl, "fetch_page", fake_fetch)
    end = WIN_START + 49 * dl.ONE_MINUTE_MS
    frame = dl.fetch_window("TESTEX", WIN_START, end)
    assert len(frame) == 50
    assert calls["n"] == 1


def test_fetch_window_raises_when_pagination_stalls(monkeypatch):
    stale = _api_rows(WIN_START - 2 * dl.ONE_MINUTE_MS, 2)
    monkeypatch.setattr(
        dl, "fetch_page", lambda symbol, s, e, timeout=20: stale
    )
    end = WIN_START + 99 * dl.ONE_MINUTE_MS
    with pytest.raises(RuntimeError, match="nao avancou"):
        dl.fetch_window("TESTEX", WIN_START, end)


def test_fetch_window_raises_on_empty_response(monkeypatch):
    monkeypatch.setattr(
        dl, "fetch_page", lambda symbol, s, e, timeout=20: []
    )
    end = WIN_START + 9 * dl.ONE_MINUTE_MS
    with pytest.raises(RuntimeError, match="nao retornou candles"):
        dl.fetch_window("TESTEX", WIN_START, end)


def test_fetch_window_rejects_row_before_start(monkeypatch):
    rows = [[WIN_START - dl.ONE_MINUTE_MS, 100.0, 101.0, 99.0, 100.5, 10.0,
             WIN_START - 1, 1000.0, 50, 5.0, 500.0, 0]]
    rows.extend(_api_rows(WIN_START, 5))
    monkeypatch.setattr(
        dl, "fetch_page", lambda symbol, s, e, timeout=20: rows
    )
    end = WIN_START + 4 * dl.ONE_MINUTE_MS
    with pytest.raises(RuntimeError, match="anterior ao inicio solicitado"):
        dl.fetch_window("TESTEX", WIN_START, end)


def test_fetch_window_rejects_row_after_end(monkeypatch):
    rows = _api_rows(WIN_START, 6)
    monkeypatch.setattr(
        dl, "fetch_page", lambda symbol, s, e, timeout=20: rows
    )
    end = WIN_START + 4 * dl.ONE_MINUTE_MS
    with pytest.raises(RuntimeError, match="posterior ao fim solicitado"):
        dl.fetch_window("TESTEX", WIN_START, end)


def test_fetch_window_rejects_duplicate_overlap(monkeypatch):
    rows = _api_rows(WIN_START, 5)
    rows.append(list(rows[0]))
    monkeypatch.setattr(
        dl, "fetch_page", lambda symbol, s, e, timeout=20: rows
    )
    end = WIN_START + 4 * dl.ONE_MINUTE_MS
    with pytest.raises(ValueError, match="duplicado"):
        dl.fetch_window("TESTEX", WIN_START, end)


# ---------------------------------------------------------------------------
# main() ponta a ponta (fetch_window simulada, ROOT em tmp_path)
# ---------------------------------------------------------------------------

def test_main_happy_path_writes_outputs_and_cleans_temps(sandbox, monkeypatch, capsys):
    _fixed_clock(monkeypatch)
    monkeypatch.setattr(
        dl, "fetch_window",
        lambda symbol, start_ms, end_ms, timeout=20: _frame(start_ms, end_ms),
    )
    rc = dl.main(["--symbol", "TESTEX", "--days", "1"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Qualidade: PASS" in out
    csv = sandbox / "data" / "raw" / "TESTEX_1m.csv"
    report_path = sandbox / "reports" / "data_quality_TESTEX_1m.json"
    assert csv.is_file()
    assert report_path.is_file()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["quality_status"] == "PASS"
    assert report["rows"] == report["expected_rows"] == 1440
    assert report["requested_days"] == 1
    assert report["mode"] == "days"
    assert report["duplicate_timestamps"] == 0
    digest = hashlib.sha256(csv.read_bytes()).hexdigest().upper()
    assert report["csv_sha256"] == digest
    assert any("renomeados em sequencia" in note for note in report["notes"])
    strays = [p for p in sandbox.rglob("*") if p.is_file() and ".tmp-" in p.name]
    assert strays == []


def test_main_gap_returns_warning_exit_2(sandbox, monkeypatch):
    _fixed_clock(monkeypatch)
    monkeypatch.setattr(
        dl, "fetch_window",
        lambda symbol, start_ms, end_ms, timeout=20: _frame(start_ms, end_ms, drop={500}),
    )
    rc = dl.main(["--symbol", "TESTEX", "--days", "1"])
    assert rc == 2
    report = json.loads(
        (sandbox / "reports" / "data_quality_TESTEX_1m.json").read_text(encoding="utf-8")
    )
    assert report["quality_status"] == "WARN_REVIEW_DATA_GAPS_OR_RANGE"
    assert report["irregular_minute_steps"] == 1
    assert report["estimated_missing_minutes"] == 1
    strays = [p for p in sandbox.rglob("*") if p.is_file() and ".tmp-" in p.name]
    assert strays == []


def test_main_cleans_temps_when_hashing_fails(sandbox, monkeypatch):
    _fixed_clock(monkeypatch)
    monkeypatch.setattr(
        dl, "fetch_window",
        lambda symbol, start_ms, end_ms, timeout=20: _frame(start_ms, end_ms),
    )

    def boom(path):
        raise OSError("boom")

    monkeypatch.setattr(dl, "sha256_file", boom)
    with pytest.raises(OSError, match="boom"):
        dl.main(["--symbol", "TESTEX", "--days", "1"])
    files = [p for p in sandbox.rglob("*") if p.is_file()]
    assert files == [], f"temporarios ou alvos deixados para tras: {files}"


def test_main_guard_blocks_existing_csv_before_network(sandbox, monkeypatch):
    csv = sandbox / "data" / "raw" / "TESTEX_1m.csv"
    csv.parent.mkdir(parents=True)
    csv.write_text("SENTINELA", encoding="utf-8")

    def no_network(*args, **kwargs):
        raise AssertionError("rede nao deve ser chamada antes da guarda")

    monkeypatch.setattr(dl, "fetch_window", no_network)
    with pytest.raises(SystemExit) as excinfo:
        dl.main(["--symbol", "TESTEX", "--days", "1"])
    assert excinfo.value.code == 2
    assert csv.read_text(encoding="utf-8") == "SENTINELA"


def test_main_output_redirects_csv_keeps_report_default(sandbox, monkeypatch):
    _fixed_clock(monkeypatch)
    monkeypatch.setattr(
        dl, "fetch_window",
        lambda symbol, start_ms, end_ms, timeout=20: _frame(start_ms, end_ms),
    )
    rc = dl.main(
        ["--symbol", "TESTEX", "--days", "1", "--output", "custom/OUT_1m.csv"]
    )
    assert rc == 0
    assert (sandbox / "custom" / "OUT_1m.csv").is_file()
    assert (sandbox / "reports" / "data_quality_TESTEX_1m.json").is_file()
    assert not (sandbox / "data" / "raw" / "TESTEX_1m.csv").exists()


def test_main_output_equal_to_report_is_collision(sandbox, monkeypatch):
    _fixed_clock(monkeypatch)

    def no_network(*args, **kwargs):
        raise AssertionError("rede nao deve ser chamada antes da colisao")

    monkeypatch.setattr(dl, "fetch_window", no_network)
    with pytest.raises(SystemExit) as excinfo:
        dl.main([
            "--symbol", "TESTEX", "--days", "1",
            "--output", "reports/data_quality_TESTEX_1m.json",
        ])
    assert excinfo.value.code == 2
    assert not (sandbox / "data").exists()
    assert not (sandbox / "reports").exists()


@pytest.mark.skipif(not IS_NT, reason="guarda por caixa exige sistema de arquivos insensivel")
def test_main_symbol_case_alias_hits_existing_guard(sandbox, monkeypatch):
    csv = sandbox / "data" / "raw" / "TESTEX_1m.csv"
    csv.parent.mkdir(parents=True)
    csv.write_text("SENTINELA", encoding="utf-8")

    def no_network(*args, **kwargs):
        raise AssertionError("rede nao deve ser chamada antes da guarda")

    monkeypatch.setattr(dl, "fetch_window", no_network)
    with pytest.raises(SystemExit) as excinfo:
        dl.main(["--symbol", "testex", "--days", "1"])
    assert excinfo.value.code == 2
    assert csv.read_text(encoding="utf-8") == "SENTINELA"


def test_main_explicit_window_writes_exact_range(sandbox, monkeypatch):
    _fixed_clock(monkeypatch)
    monkeypatch.setattr(
        dl, "fetch_window",
        lambda symbol, start_ms, end_ms, timeout=20: _frame(start_ms, end_ms),
    )
    rc = dl.main([
        "--symbol", "TESTEX",
        "--start", "2026-01-01T00:00:00Z",
        "--end", "2026-01-01T05:59:00Z",
    ])
    assert rc == 0
    report = json.loads(
        (sandbox / "reports" / "data_quality_TESTEX_1m.json").read_text(encoding="utf-8")
    )
    assert report["mode"] == "explicit_window"
    assert report["requested_days"] is None
    assert report["rows"] == report["expected_rows"] == 360
    assert report["requested_start_utc"] == "2026-01-01T00:00:00+00:00"
    assert report["first_timestamp_utc"].startswith("2026-01-01T00:00")
    assert report["last_timestamp_utc"].startswith("2026-01-01T05:59")
    assert report["quality_status"] == "PASS"
