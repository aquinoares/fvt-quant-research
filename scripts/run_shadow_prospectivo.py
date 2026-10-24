#!/usr/bin/env python3
"""Sombra prospectiva continua com monitoramento exclusivo de risco (F3) - P5.

Autorizacao: a aprovacao vem de um registro persistente no ledger real
(memory/hypotheses_ledger.jsonl). O arquivo --risk-approval e apenas uma
REFERENCIA a esse registro; um JSON isolado nunca concede autorizacao.
Registro exigido: record_type=protocolo, status=ativo, protocol_ref=P5,
risk_limit_approved=true, limit_drawdown_net numerico NEGATIVO em [-1, 0)
(ex.: -0.10; breach quando max_drawdown_net <= limit_drawdown_net), campos
obrigatorios do esquema do ledger, id diferente de P5.

Escreve somente dentro do diretorio --out (exigido sob data/shadow/):
  state.json        - operacional SEM equity/pico/drawdown (posicao, ultimo
                      timestamp, segmentos, observacao bruta reanchor_open/
                      reanchor_ts, code_manifest); equidade fica so em
                      memoria, reconstruida por replay no resume.
  risk_monitor.json - UNICO arquivo de desempenho: max_drawdown_net, limit_
                      (signo conservado, ex.: -0.10; breached = max_drawdown_
                      net <= limit_drawdown_net), breached, updated_at_utc,
                      protocol (excecao do item 6 de P5: monitoramento
                      restrito do limite).
  events.jsonl      - eventos de interrupcao COLLECTION_FAILURE (rc 2),
                      RISK_LIMIT_BREACHED (rc 3), FATAL_SESSION_STOP (rc 4).
                      Interrupcao nunca e resultado.

Nunca abre: CSV historico, relatorios de pesquisa, janela F1/F2, journal.
Replay determinista: features + reconciliacao + run_one com custos P4
(DEFAULT_30BPS_RT) sobre todos os segmentos acumulados.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research"))
sys.path.insert(0, str(ROOT / "src"))

import run_research  # noqa: E402

SHADOW_ROOT = ROOT / "data" / "shadow"
DEFAULT_LEDGER = ROOT / "memory" / "hypotheses_ledger.jsonl"
LEDGER_REQUIRED_FIELDS = {
    "record_type", "id", "statement", "source", "status", "recorded_at",
}
CODE_DEPENDENCIES = (
    "scripts/run_shadow_prospectivo.py",
    "research/run_research.py",
    "src/convergencia/__init__.py",
    "src/convergencia/strategy.py",
    "src/convergencia/signals.py",
    "src/convergencia/backtest.py",
    "src/convergencia/data.py",
    "src/convergencia/features/__init__.py",
    "src/convergencia/features/fibonacci.py",
    "src/convergencia/features/fractal.py",
    "src/convergencia/features/momentum.py",
    "src/convergencia/features/regime.py",
    "src/convergencia/features/volume.py",
)
PROTOCOL = "P5"
VARIANT = "M15_original"
PROTOCOLS = {
    "P5": {"variant": "M15_original", "days": 30},
    "P6-MOM": {"variant": "MOM_TF240_LB96", "days": 90},
}
P6MOM_CODE_DEPENDENCIES = CODE_DEPENDENCIES + ("research/mom_tf240.py",)
MINUTE = pd.Timedelta(minutes=1)

EXIT_OK = 0
EXIT_REFUSED = 2
EXIT_RISK_BREACH = 3
EXIT_FATAL = 4


class ShadowRefused(RuntimeError):
    """Entrada invalida ou continuidade violada (eventuais = COLLECTION_FAILURE)."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _utc_now().isoformat()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def code_manifest(protocol: str = PROTOCOL) -> dict[str, str]:
    deps = P6MOM_CODE_DEPENDENCIES if protocol == "P6-MOM" else CODE_DEPENDENCIES
    manifest: dict[str, str] = {}
    for rel in deps:
        path = ROOT / rel
        if not path.is_file():
            raise ShadowRefused(f"dependencia de codigo ausente: {rel}")
        manifest[rel] = sha256_file(path)
    return manifest


def _atomic_write_json(path: Path, payload: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, path)


def append_event(path: Path, event: str, detail: str) -> None:
    record = {"event": event, "at_utc": _now_iso(), "detail": detail}
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, ensure_ascii=False) + "\n")


def load_ledger(path: Path) -> list[dict]:
    if not path.is_file():
        raise ShadowRefused(f"ledger inexistente: {path}")
    records: list[dict] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ShadowRefused(f"ledger linha {lineno} invalida: {exc}") from exc
    if not records:
        raise ShadowRefused("ledger vazio")
    return records


def validate_approval(ref_path: Path, ledger_path: Path, protocol: str = PROTOCOL) -> dict:
    ref_path = Path(ref_path)
    if not ref_path.is_file():
        raise ShadowRefused(f"referencia de aprovacao inexistente: {ref_path}")
    try:
        ref = json.loads(ref_path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ShadowRefused(f"referencia de aprovacao ilegivel: {exc}") from exc
    missing = {"ledger", "record_id", "protocol_ref", "limit_drawdown_net"} - set(ref)
    if missing:
        raise ShadowRefused(f"referencia de aprovacao sem campos: {sorted(missing)}")
    if ref["protocol_ref"] != protocol:
        raise ShadowRefused(f"referencia de aprovacao nao aponta para {protocol}")
    if Path(ref["ledger"]).resolve() != Path(ledger_path).resolve():
        raise ShadowRefused("referencia de aprovacao aponta para outro ledger")
    try:
        limit = float(ref["limit_drawdown_net"])
    except (TypeError, ValueError) as exc:
        raise ShadowRefused("limit_drawdown_net nao numerico") from exc
    if not (-1.0 <= limit < 0.0) or not math.isfinite(limit):
        raise ShadowRefused("limit_drawdown_net fora de [-1, 0)")

    record_id = str(ref["record_id"])
    if record_id == protocol:
        raise ShadowRefused(f"o proprio registro {protocol} nao e aprovacao de risco")
    records = load_ledger(Path(ledger_path))
    matches = [r for r in records if r.get("id") == record_id]
    if len(matches) != 1:
        raise ShadowRefused(
            f"referencia nao resolve para exatamente 1 registro no ledger: {record_id}"
        )
    record = matches[0]
    absent = LEDGER_REQUIRED_FIELDS - set(record)
    if absent:
        raise ShadowRefused(f"registro de aprovacao sem campos obrigatorios: {sorted(absent)}")
    if record.get("record_type") != "protocolo":
        raise ShadowRefused("registro de aprovacao nao e protocolo")
    if record.get("status") != "ativo":
        raise ShadowRefused("registro de aprovacao nao esta ativo")
    if record.get("protocol_ref") != protocol:
        raise ShadowRefused(f"registro de aprovacao nao referencia {protocol}")
    if record.get("risk_limit_approved") is not True:
        raise ShadowRefused("registro de aprovacao nao marca risk_limit_approved=true")
    record_limit = record.get("limit_drawdown_net")
    try:
        record_limit_f = float(record_limit)
    except (TypeError, ValueError) as exc:
        raise ShadowRefused("limite do ledger nao numerico") from exc
    if not math.isclose(record_limit_f, limit, rel_tol=0.0, abs_tol=1e-12):
        raise ShadowRefused("limite do ledger difere da referencia")
    return {"reference": ref, "record": record, "limit": limit}


def load_segment(path: Path) -> pd.DataFrame:
    path = Path(path)
    if not path.is_file():
        raise ShadowRefused(f"segmento inexistente: {path}")
    try:
        frame = pd.read_csv(path)
    except Exception as exc:  # noqa: BLE001
        raise ShadowRefused(f"segmento ilegivel: {exc}") from exc
    required = {"timestamp", "open", "high", "low", "close", "volume"}
    absent = required - set(frame.columns)
    if absent:
        raise ShadowRefused(f"segmento sem colunas: {sorted(absent)}")
    if len(frame) == 0:
        raise ShadowRefused("segmento vazio")
    for col in ("open", "high", "low", "close", "volume"):
        try:
            frame[col] = pd.to_numeric(frame[col], errors="raise")
        except Exception as exc:  # noqa: BLE001
            raise ShadowRefused(f"coluna {col} nao numerica: {exc}") from exc
    try:
        ts = pd.to_datetime(frame["timestamp"], format="ISO8601", utc=True, errors="raise")
    except Exception as exc:  # noqa: BLE001
        raise ShadowRefused(f"timestamp invalido: {exc}") from exc
    if ts.duplicated().any():
        raise ShadowRefused("segmento com timestamps duplicados")
    if not ts.is_monotonic_increasing:
        raise ShadowRefused("segmento fora de ordem")
    if len(ts) > 1 and (ts.diff().dropna() != MINUTE).any():
        raise ShadowRefused("segmento com lacuna ou salto de tempo")
    return frame


def _parse_ts(value: object) -> pd.Timestamp:
    stamp = pd.Timestamp(str(value))
    if stamp.tzinfo is None:
        stamp = stamp.tz_localize("UTC")
    return stamp.tz_convert("UTC")


def _replay(candles: pd.DataFrame, variant: str = VARIANT) -> tuple[float, float]:
    scenario = run_research.COST_SCENARIOS[1]
    if (scenario.fee_bps_per_side, scenario.slippage_bps_per_side) != (10.0, 5.0):
        raise RuntimeError("cenario de custos nao e o padrao P4")
    if variant == "MOM_TF240_LB96":
        frame = candles.copy()
        if not pd.api.types.is_datetime64_any_dtype(frame["timestamp"]):
            frame["timestamp"] = pd.to_datetime(
                frame["timestamp"], format="ISO8601", utc=True, errors="raise"
            )
        events = _mom_events(frame)
        bt, metrics = run_research.run_one(frame, events, scenario)
    else:
        features = run_research.generate_features(candles, "15m", run_research.ORIGINAL_CONFIG)
        run_research.reconcile_full(features)
        events = features["signal"].to_numpy()
        bt, metrics = run_research.run_one(features, events, scenario)
    max_dd = float(metrics["max_drawdown_net"])
    position = float(pd.to_numeric(bt["position"]).iloc[-1]) if len(bt) else 0.0
    return max_dd, position


def _mom_events(candles: pd.DataFrame) -> np.ndarray:
    """Eventos MOM_TF240_LB96 (delegados ao modulo congelado research/mom_tf240)."""
    import mom_tf240

    return mom_tf240.build_events(candles)


def _fresh_state(manifest: dict[str, str], window_id: str,
                 protocol: str = PROTOCOL, variant: str = VARIANT) -> dict:
    return {
        "protocol": protocol,
        "variant": variant,
        "window_id": window_id,
        "costs": {"fee_bps_per_side": 10.0, "slippage_bps_per_side": 5.0},
        "started_at_utc": _now_iso(),
        "updated_at_utc": _now_iso(),
        "segments": [],
        "last_timestamp": None,
        "position": 0.0,
        "reanchor_open": None,
        "reanchor_ts": None,
        "code_manifest": manifest,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--segment", type=Path, required=True, help="CSV 1m a acrescentar")
    parser.add_argument("--out", type=Path, required=True, help="Diretorio da sessao")
    parser.add_argument("--risk-approval", type=Path, required=True,
                        help="Referencia JSON ao registro de aprovacao no ledger")
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--protocol", choices=sorted(PROTOCOLS), default=PROTOCOL,
                        help="Protocolo dono da sessao (padrao P5; P6-MOM usa MOM_TF240_LB96)")
    parser.add_argument("--window-id", default=None)
    args = parser.parse_args(argv)
    protocol = args.protocol
    spec = PROTOCOLS[protocol]
    if args.window_id is None:
        args.window_id = f"prospective_{spec['days']}d"
    try:
        approval = validate_approval(args.risk_approval, Path(args.ledger), protocol)
    except ShadowRefused as exc:
        print(f"AUTORIZACAO RECUSADA: {exc}", file=sys.stderr)
        return EXIT_REFUSED

    out = Path(args.out).resolve()
    shadow_root = SHADOW_ROOT.resolve()
    if out == shadow_root or shadow_root not in out.parents:
        print(f"AUTORIZACAO RECUSADA: --out fora de data/shadow/: {out}", file=sys.stderr)
        return EXIT_REFUSED
    out.mkdir(parents=True, exist_ok=True)
    state_path = out / "state.json"
    monitor_path = out / "risk_monitor.json"
    events_path = out / "events.jsonl"
    limit = approval["limit"]

    try:
        return _process(args, out, state_path, monitor_path, events_path, limit, protocol)
    except ShadowRefused as exc:
        append_event(events_path, "COLLECTION_FAILURE", str(exc)[:300])
        print(f"FALHA DE COLETA: {exc}", file=sys.stderr)
        return EXIT_REFUSED
    except Exception as exc:  # noqa: BLE001
        append_event(events_path, "FATAL_SESSION_STOP",
                     f"{type(exc).__name__}: {exc}"[:300])
        print(f"PARADA FATAL: {type(exc).__name__}", file=sys.stderr)
        return EXIT_FATAL


def _process(args, out: Path, state_path: Path, monitor_path: Path,
             events_path: Path, limit: float, protocol: str = PROTOCOL) -> int:
    variant = PROTOCOLS[protocol]["variant"]
    manifest = code_manifest(protocol)
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            append_event(events_path, "FATAL_SESSION_STOP", f"state ilegivel: {exc}"[:300])
            return EXIT_FATAL
        if state.get("protocol") != protocol or state.get("variant") != variant:
            append_event(events_path, "FATAL_SESSION_STOP", "state de outro protocolo")
            return EXIT_FATAL
        if state.get("code_manifest") != manifest:
            append_event(events_path, "FATAL_SESSION_STOP",
                         "code_manifest divergente do codigo atual")
            return EXIT_FATAL
    else:
        state = _fresh_state(manifest, args.window_id, protocol, variant)

    segment_path = Path(args.segment).resolve()
    if str(segment_path) in state["segments"]:
        raise ShadowRefused(f"segmento ja registrado: {segment_path}")
    segment = load_segment(segment_path)
    segment_ts = pd.to_datetime(
        segment["timestamp"], format="ISO8601", utc=True, errors="raise"
    )

    if state["last_timestamp"] is not None:
        expected = _parse_ts(state["last_timestamp"]) + MINUTE
        if segment_ts.iloc[0] != expected:
            raise ShadowRefused(
                "segmento nao continua o ultimo timestamp observado "
                f"(esperado {expected.isoformat()}, obtido "
                f"{segment_ts.iloc[0].isoformat()})"
            )

    frames: list[pd.DataFrame] = []
    for rel in [*state["segments"], str(segment_path)]:
        frames.append(load_segment(Path(rel)))
    candles = (
        pd.concat(frames, ignore_index=True)
        .drop_duplicates(subset="timestamp", keep="last")
        .sort_values("timestamp", kind="mergesort")
        .reset_index(drop=True)
    )
    ts_all = pd.to_datetime(
        candles["timestamp"], format="ISO8601", utc=True, errors="raise"
    )
    if len(candles) > 1 and (ts_all.diff().dropna() != MINUTE).any():
        raise ShadowRefused("historico acumulado com lacuna")

    if variant == VARIANT:
        max_dd, position = _replay(candles)
    else:
        max_dd, position = _replay(candles, variant)
    breached = bool(max_dd <= limit)
    _atomic_write_json(monitor_path, {
        "max_drawdown_net": max_dd,
        "limit_drawdown_net": limit,
        "breached": breached,
        "updated_at_utc": _now_iso(),
        "protocol": protocol,
    })

    last_ts = ts_all.iloc[-1]
    state.update({
        "updated_at_utc": _now_iso(),
        "segments": [*state["segments"], str(segment_path)],
        "last_timestamp": last_ts.isoformat(),
        "position": position,
        "reanchor_open": float(candles["open"].iloc[-1]),
        "reanchor_ts": last_ts.isoformat(),
    })
    _atomic_write_json(state_path, state)

    if breached:
        append_event(events_path, "RISK_LIMIT_BREACHED",
                     "limite de drawdown atingido; sessao interrompida; "
                     "interrupcao nao e resultado")
        print("INTERRUPCAO: RISK_LIMIT_BREACHED")
        return EXIT_RISK_BREACH
    print("sessao gravada")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
