#!/usr/bin/env python3
"""Avaliacao final da janela prospectiva (F1) - protocolos P5 e P6-MOM.

Somente executa APOS o fechamento valido da janela. Conjunto FECHADO de
dados externos (unicos arquivos de dados abertos): CSV da janela, manifesto
e relatorio de integridade - todos explicitados na linha de comando e
vinculados pelo registro terminal "window_closed". O CSV historico
(data/raw/BTCUSDT_1m.csv), caches de mercado, segmentos nao fornecidos,
reports/ e relatorios auditados de research/out/ NUNCA sao abertos.

Protocolos:
- P5: 30 dias, variante M15_original, custos P4 (10+5 bps/lado).
- P6-MOM: 90 dias, variante MOM_TF240_LB96 (research/mom_tf240.py),
  custos P4 + criterios congelados aplicados no fechamento (stress 60 bps).

Dependencias de codigo (lista fechada por protocolo, abertas apenas para
import/hash): este arquivo, research/run_research.py e
src/convergencia/{__init__,strategy,signals,backtest,data}.py +
features/{__init__,fibonacci,fractal,momentum,regime,volume}.py; P6-MOM
acrescenta research/mom_tf240.py.

Bloqueios: sem window_closed valido; intervalo != exatamente os dias do
protocolo em [start_utc, end_utc); fechamento anterior ao fim real da
janela; relogio real anterior ao fim da janela (sem excecao de relogio no
CLI de producao); SHA do CSV ou do relatorio divergente do fechamento;
caminho de CSV divergente do fechamento; relatorio de outro protocolo;
destino proibido. Gravado apenas em destino novo.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research"))
sys.path.insert(0, str(ROOT / "src"))

import run_research  # noqa: E402

HISTORICAL_CSV = ROOT / "data" / "raw" / "BTCUSDT_1m.csv"
FORBIDDEN_OUTPUTS = (
    ROOT / "research" / "out" / "csv_integrity.json",
    ROOT / "research" / "out" / "research_results.json",
)
CODE_DEPENDENCIES = (
    "research/run_window_evaluation.py",
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
P6MOM_CODE_DEPENDENCIES = CODE_DEPENDENCIES + ("research/mom_tf240.py",)
PROTOCOLS = {
    "P5": {"variant": "M15_original", "days": 30},
    "P6-MOM": {"variant": "MOM_TF240_LB96", "days": 90},
}
PROTOCOL = "P5"
EXPECTED_DAYS = 30
MINUTE = pd.Timedelta(minutes=1)


def code_dependencies(protocol: str = PROTOCOL) -> tuple[str, ...]:
    if protocol == "P6-MOM":
        return P6MOM_CODE_DEPENDENCIES
    return CODE_DEPENDENCIES


class EvaluationRefused(RuntimeError):
    """Avaliacao antecipada ou vinculos invalidos."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def canonical_json(obj: dict) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def canonical_sha256(obj: dict) -> str:
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _parse_utc(value: object, what: str) -> pd.Timestamp:
    try:
        stamp = pd.Timestamp(str(value))
    except Exception as exc:  # noqa: BLE001
        raise EvaluationRefused(f"{what}: timestamp invalido: {value!r}") from exc
    if stamp.tzinfo is None or stamp.utcoffset() != timedelta(0):
        raise EvaluationRefused(f"{what}: timestamp nao UTC: {value!r}")
    return stamp.tz_convert("UTC")


def load_manifest(path: Path) -> list[dict]:
    if not Path(path).is_file():
        raise EvaluationRefused(f"manifesto inexistente: {path}")
    entries: list[dict] = []
    for lineno, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise EvaluationRefused(f"manifesto linha {lineno} invalida: {exc}") from exc
    if not entries:
        raise EvaluationRefused("manifesto vazio")
    return entries


def verify_chain(entries: list[dict]) -> None:
    if entries[0].get("prev_sha256") is not None:
        raise EvaluationRefused("primeira entrada do manifesto sem prev_sha256 nulo")
    for i in range(1, len(entries)):
        expected = canonical_sha256(entries[i - 1])
        if entries[i].get("prev_sha256") != expected:
            raise EvaluationRefused(f"cadeia do manifesto quebrada na entrada {i}")


def validate_closure(entries: list[dict], protocol: str = PROTOCOL) -> dict:
    days = PROTOCOLS[protocol]["days"]
    if not entries or entries[-1].get("record") != "window_closed":
        raise EvaluationRefused("manifesto sem fechamento window_closed")
    closure = entries[-1]
    body = entries[:-1]
    if sum(1 for e in entries if e.get("record") == "window_closed") != 1:
        raise EvaluationRefused("mais de um fechamento no manifesto")
    verify_chain(entries)
    if closure.get("protocol") != protocol:
        raise EvaluationRefused(f"fechamento nao identifica o protocolo {protocol}")
    window_id = closure.get("window_id")
    start_record_id = closure.get("start_record_id")
    if not window_id or not start_record_id:
        raise EvaluationRefused("fechamento sem window_id/start_record_id")
    start = _parse_utc(closure.get("window_start_utc"), "window_start_utc")
    end = _parse_utc(closure.get("window_end_utc"), "window_end_utc")
    closed_at = _parse_utc(closure.get("closed_at_utc"), "closed_at_utc")
    if end - start != pd.Timedelta(days=days):
        raise EvaluationRefused(
            f"intervalo nao cobre exatamente {days} dias em [start, end)"
        )
    if int(closure.get("days", -1)) != days:
        raise EvaluationRefused(f"days do fechamento difere de {days}")
    if closed_at < end:
        raise EvaluationRefused("fechamento anterior ao fim real da janela")
    declared = closure.get("segments")
    if not isinstance(declared, list) or len(declared) != days:
        raise EvaluationRefused(f"fechamento nao declara exatamente {days} segmentos")
    for i, item in enumerate(declared):
        if not isinstance(item, dict) or set(item) != {"seq", "file", "sha256"}:
            raise EvaluationRefused(f"declaracao de segmento {i} malformada")
        if item["seq"] != i:
            raise EvaluationRefused(f"sequencia de segmentos nao contigua: {item}")
    segments = [e for e in body if e.get("record") == "segment"]
    if len(body) != days or len(segments) != days:
        raise EvaluationRefused(
            f"corpo do manifesto com {len(body)} registros (esperado {days} segmentos)"
        )
    triplets = [
        {"seq": e.get("seq"), "file": e.get("file"), "sha256": e.get("sha256")}
        for e in segments
    ]
    if declared != triplets:
        raise EvaluationRefused("segmentos do fechamento divergem do corpo do manifesto")
    return closure


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, required=True, help="CSV consolidado da janela")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--integrity-report", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True, help="Diretorio window_evaluation/")
    parser.add_argument("--expected-sha256", default=None, help="SHA opcional extra do CSV")
    parser.add_argument("--protocol", choices=sorted(PROTOCOLS), default=PROTOCOL,
                        help="Protocolo da janela (padrao P5; P6-MOM exige 90 dias/MOM)")
    args = parser.parse_args(argv)
    try:
        return _evaluate(args)
    except EvaluationRefused as exc:
        print(f"AVALIACAO RECUSADA: {exc}", file=sys.stderr)
        return 2


def _evaluate(args) -> int:
    protocol = args.protocol
    days = PROTOCOLS[protocol]["days"]
    csv_path = Path(args.csv).resolve()
    manifest_path = Path(args.manifest).resolve()
    report_path = Path(args.integrity_report).resolve()
    out_dir = Path(args.out).resolve()

    if csv_path == HISTORICAL_CSV.resolve():
        raise EvaluationRefused("CSV historico nao pode ser usado na avaliacao da janela")
    if out_dir.name != "window_evaluation":
        raise EvaluationRefused("destino deve ser um diretorio window_evaluation/")
    for forbidden in FORBIDDEN_OUTPUTS:
        if out_dir == forbidden.resolve().parent or out_dir == forbidden.resolve():
            raise EvaluationRefused(f"destino proibido: {out_dir}")
    stamp = _utc_now().strftime("%Y%m%dT%H%M%SZ")
    target = out_dir / f"window_evaluation_{protocol}_{stamp}.json"
    if target.exists():
        raise EvaluationRefused(f"destino ja existe: {target}")
    for other in (manifest_path, report_path):
        for forbidden in FORBIDDEN_OUTPUTS:
            if other == forbidden.resolve():
                raise EvaluationRefused(f"entrada proibida: {other}")

    entries = load_manifest(manifest_path)
    closure = validate_closure(entries, protocol)
    start = _parse_utc(closure["window_start_utc"], "window_start_utc")
    end = _parse_utc(closure["window_end_utc"], "window_end_utc")
    now = _utc_now()
    now_stamp = pd.Timestamp(now)
    if now_stamp.tzinfo is None:
        now_stamp = now_stamp.tz_localize("UTC")
    if now_stamp < end:
        raise EvaluationRefused("janela ainda nao terminou (relogio real anterior ao fim)")

    if not report_path.is_file():
        raise EvaluationRefused(f"relatorio de integridade inexistente: {report_path}")
    if str(report_path) != str(Path(closure.get("integrity_report_path", "")).resolve()):
        raise EvaluationRefused("relatorio de integridade difere do vinculo do fechamento")
    report_bytes = report_path.read_bytes()
    if hashlib.sha256(report_bytes).hexdigest() != closure.get("integrity_report_sha256"):
        raise EvaluationRefused("SHA do relatorio de integridade difere do fechamento")
    try:
        report = json.loads(report_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvaluationRefused(f"relatorio ilegivel: {exc}") from exc
    if report.get("verdict") != "PASS":
        raise EvaluationRefused("integridade da janela nao e PASS")
    if report.get("protocol", PROTOCOL) != protocol:
        raise EvaluationRefused("relatorio de integridade pertence a outro protocolo")
    if report.get("window_id") != closure.get("window_id"):
        raise EvaluationRefused("relatorio pertence a outra janela")
    if report.get("record") == "window_closed":
        raise EvaluationRefused("relatorio referencia o fechamento (circularidade)")

    if str(csv_path) != str(Path(closure.get("consolidated_csv_path", "")).resolve()):
        raise EvaluationRefused("CSV difere do caminho vinculado no fechamento")
    csv_sha = sha256_file(csv_path)
    if csv_sha != closure.get("consolidated_csv_sha256"):
        raise EvaluationRefused("SHA do CSV difere do fechamento")
    if args.expected_sha256 and csv_sha != str(args.expected_sha256).lower():
        raise EvaluationRefused("--expected-sha256 difere do SHA do CSV")

    candles = pd.read_csv(csv_path)
    rows = int(len(candles))
    if rows != int(closure.get("consolidated_rows", -1)):
        raise EvaluationRefused("linhas do CSV diferem do fechamento")
    if rows != days * 1440:
        raise EvaluationRefused(f"CSV nao tem {days * 1440} linhas de 1m")
    ts = pd.to_datetime(candles["timestamp"], format="ISO8601", utc=True, errors="raise")
    if ts.iloc[0] != start or ts.iloc[-1] != end - MINUTE:
        raise EvaluationRefused("intervalo real do CSV difere de [start_utc, end_utc)")
    if ts.duplicated().any() or (ts.diff().dropna() != MINUTE).any():
        raise EvaluationRefused("CSV da janela com lacuna/duplicata/desordem")

    scenario = run_research.COST_SCENARIOS[1]
    if (scenario.fee_bps_per_side, scenario.slippage_bps_per_side) != (10.0, 5.0):
        raise EvaluationRefused("cenario de custos nao e o padrao P4 (10+5 bps/lado)")
    extra_result: dict = {}
    if protocol == "P6-MOM":
        import mom_tf240  # noqa: PLC0415 - dentro do ramo do protocolo

        frame = candles.copy()
        frame["timestamp"] = ts
        events = mom_tf240.build_events(frame)
        _bt, metrics = run_research.run_one(frame, events, scenario)
        stress = run_research.CostScenario("STRESS_60BPS_RT", 20.0, 10.0)
        if stress.round_trip_bps != 60.0:
            raise EvaluationRefused("cenario de stress nao e 60 bps por operacao")
        _bt_stress, metrics_stress = run_research.run_one(frame, events, stress)
        frozen = mom_tf240.frozen_criteria(metrics, metrics_stress["net_total_return"])
        extra_result = {
            "config": dict(mom_tf240.CONFIG),
            "metrics_stress_60bps": metrics_stress,
            "frozen_criteria": frozen,
            "selection_note": (
                "variante selecionada em dados historicos; desempenho prospectivo "
                "nao garante resultado futuro"
            ),
        }
    else:
        feats = run_research.generate_features(candles, "15m", run_research.ORIGINAL_CONFIG)
        run_research.reconcile_full(feats)
        events = feats["signal"].to_numpy()
        _bt, metrics = run_research.run_one(feats, events, scenario)
        extra_result = {"original_config": asdict(run_research.ORIGINAL_CONFIG)}

    code_hashes = {}
    for rel in code_dependencies(protocol):
        path = ROOT / rel
        if not path.is_file():
            raise EvaluationRefused(f"dependencia de codigo ausente: {rel}")
        code_hashes[rel] = sha256_file(path)

    result = {
        "report": "window_evaluation",
        "protocol": protocol,
        "window_id": closure.get("window_id"),
        "start_record_id": closure.get("start_record_id"),
        "window": {
            "start_utc": closure["window_start_utc"],
            "end_utc": closure["window_end_utc"],
            "days": days,
            "closed_at_utc": closure["closed_at_utc"],
        },
        "data": {
            "csv_path_resolved": str(csv_path),
            "csv_sha256": csv_sha,
            "csv_rows": rows,
            "manifest_path_resolved": str(manifest_path),
            "integrity_report_path_resolved": str(report_path),
            "integrity_report_sha256": closure.get("integrity_report_sha256"),
        },
        "code_hashes": code_hashes,
        "variant": PROTOCOLS[protocol]["variant"],
        **extra_result,
        "costs": {
            "scenario": scenario.label,
            "fee_bps_per_side": scenario.fee_bps_per_side,
            "slippage_bps_per_side": scenario.slippage_bps_per_side,
            "round_trip_bps": scenario.round_trip_bps,
        },
        "generated_at_utc": _utc_now().isoformat(),
        "metrics": metrics,
    }
    payload = json.dumps(
        run_research._jsonable(result), indent=2, ensure_ascii=False, allow_nan=False
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(payload + "\n", encoding="utf-8")
    os.replace(tmp, target)
    print(f"avaliacao gravada em: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
