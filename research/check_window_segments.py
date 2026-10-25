#!/usr/bin/env python3
"""Verificador/registrador de segmentos diarios da janela prospectiva (F2).

Sem metricas de desempenho. Somente estrutura, continuidade temporal, OHLC
valido e cadeia de hashes canonicos. Nunca escreve em
research/out/csv_integrity.json nem research/out/research_results.json.

Cadeia canonica: para cada entrada i (i > 0):
    prev_sha256[i] == sha256(canonica(entrada[i - 1]))
onde canonica(x) = json.dumps(x, sort_keys=True, separators=(",", ":"),
ensure_ascii=False) em UTF-8 sobre o registro INTEGRO, incluindo o proprio
campo prev_sha256 de x. A primeira entrada usa prev_sha256 = None. Alterar
qualquer campo de qualquer entrada anterior invalida o elo seguinte. O
registro terminal "window_closed" participa da mesma cadeia.

Verificacao independente do registro terminal, sem circularidade: o
relatorio de integridade NUNCA referencia o fechamento; o fechamento
referencia o SHA do relatorio. A verificacao do terminal cruza (a) a cadeia,
(b) a lista de segmentos declarada no fechamento contra o corpo real do
manifesto, (c) o CSV consolidado e (d) o relatorio - todos recomputados.

Invalidacao antecipada da janela confirmatoria (regra emitida no relatorio):
candle ausente, duplicado, fora de ordem, segmento inconsistente ou sessao
incompleta invalida a janela; sem interpolacao, sem preenchimento retroativo,
sem estender os 30 dias apos consulta de resultados e sem misturar segmentos
de janelas diferentes; reinicio exige novo registro de protocolo/inicio
antes de nova coleta.

15m (derivada, justificada): o contexto Pai agrega barras COMPLETAS de
15min (bar_count == timeframe em research/run_research.py:61-62 e regra
identica em src/convergencia/strategy.py); a janela comeca 00:00 UTC, entao
a grade de 15m esta alinhada e a continuidade de 1m implica barras 15m
completas - e uma assercao de consistencia da premissa da estrategia,
exigida apenas apos PASS de 1m. A agregacao de 5m NAO e verificada: pertence
a variante M5, fora da avaliacao congelada (M15_original).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_OUTPUTS = (
    ROOT / "research" / "out" / "csv_integrity.json",
    ROOT / "research" / "out" / "research_results.json",
)
PROTOCOL = "P5"
EXPECTED_DAYS = 30
PROTOCOL_DAYS = {"P5": 30, "P6-MOM": 90}
MINUTE = pd.Timedelta(minutes=1)


class CheckError(RuntimeError):
    """Entrada invalida ou regra de integridade violada."""


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


def _parse_utc(value: str, what: str) -> pd.Timestamp:
    try:
        stamp = pd.Timestamp(value)
    except Exception as exc:  # noqa: BLE001 - mensagem propria
        raise CheckError(f"{what}: timestamp invalido: {value!r}") from exc
    if stamp.tzinfo is None or stamp.utcoffset() != timedelta(0):
        raise CheckError(f"{what}: timestamp nao UTC: {value!r}")
    return stamp.tz_convert("UTC")


def load_manifest(path: Path) -> list[dict]:
    path = Path(path)
    if not path.is_file():
        raise CheckError(f"manifesto inexistente: {path}")
    entries: list[dict] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise CheckError(f"manifesto linha {lineno} nao e JSON: {exc}") from exc
    if not entries:
        raise CheckError("manifesto vazio")
    return entries


def append_manifest(path: Path, entry: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="") as stream:
        stream.write(json.dumps(entry, ensure_ascii=False, sort_keys=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def verify_chain(entries: list[dict]) -> list[str]:
    reasons: list[str] = []
    first = entries[0]
    if first.get("prev_sha256") is not None:
        reasons.append("primeira entrada deve ter prev_sha256 nulo")
    for i in range(1, len(entries)):
        prev = entries[i - 1]
        cur = entries[i]
        expected = canonical_sha256(prev)
        if cur.get("prev_sha256") != expected:
            reasons.append(
                f"elo quebrado na entrada {i}: prev_sha256 divergente "
                f"(esperado {expected[:16]}..., obtido {str(cur.get('prev_sha256'))[:16]}...)"
            )
    return reasons


def check_segment_frame(frame: pd.DataFrame, parent_minutes: int = 15) -> dict:
    checks: dict = {}
    if "timestamp" not in frame.columns:
        raise CheckError("segmento sem coluna timestamp")
    ts = pd.to_datetime(frame["timestamp"], format="ISO8601", utc=True, errors="coerce")
    checks["timestamp_parse_failures"] = int(ts.isna().sum())
    rows = int(len(frame))
    checks["rows"] = rows
    if rows == 0 or ts.isna().any():
        raise CheckError(f"segmento com timestamps invalidos: {checks}")
    first, last = ts.iloc[0], ts.iloc[-1]
    checks["first_ts_utc"] = first.isoformat()
    checks["last_ts_utc"] = last.isoformat()
    span = int((last - first).total_seconds() // 60) + 1
    checks["expected_rows_from_span"] = span
    checks["rows_match_span"] = rows == span
    checks["duplicate_timestamps"] = int(ts.duplicated().sum())
    checks["monotonic_increasing"] = bool(ts.is_monotonic_increasing)
    diffs = ts.diff().dropna()
    checks["non_1min_steps"] = int((diffs != MINUTE).sum())
    ohlcv = frame[["open", "high", "low", "close", "volume"]].apply(
        pd.to_numeric, errors="coerce"
    )
    arr = ohlcv.to_numpy(dtype="float64")
    checks["non_finite_ohlcv_cells"] = int((~np.isfinite(arr)).sum())
    checks["non_positive_prices"] = int(
        (ohlcv[["open", "high", "low", "close"]] <= 0).sum().sum()
    )
    checks["negative_volume"] = int((ohlcv["volume"] < 0).sum())
    invalid_range = (ohlcv["high"] < ohlcv[["open", "close", "low"]].max(axis=1)) | (
        ohlcv["low"] > ohlcv[["open", "close", "high"]].min(axis=1)
    )
    checks["ohlc_range_violations"] = int(invalid_range.sum())
    if checks["non_1min_steps"] == 0 and checks["duplicate_timestamps"] == 0:
        counts = ts.dt.floor(f"{parent_minutes}min").value_counts()
        checks[f"incomplete_{parent_minutes}m_parent_bars"] = int(
            (counts != parent_minutes).sum()
        )
    else:
        checks[f"incomplete_{parent_minutes}m_parent_bars"] = None  # nao interpretavel sem 1m limpo
    checks["ok"] = (
        checks["timestamp_parse_failures"] == 0
        and checks["rows_match_span"]
        and checks["duplicate_timestamps"] == 0
        and checks["monotonic_increasing"]
        and checks["non_1min_steps"] == 0
        and checks["non_finite_ohlcv_cells"] == 0
        and checks["non_positive_prices"] == 0
        and checks["negative_volume"] == 0
        and checks["ohlc_range_violations"] == 0
        and checks[f"incomplete_{parent_minutes}m_parent_bars"] in (0, None)
    )
    return checks


def _segment_path(file_ref: str, root: Path) -> Path:
    p = Path(file_ref)
    return p if p.is_absolute() else (root / p)


def _rel_or_abs(file_path: Path, root: Path) -> str:
    resolved = Path(file_path).resolve()
    try:
        return resolved.relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(resolved)


def check_segment_file(file_path: Path, root: Path, parent_minutes: int = 15) -> tuple[dict, pd.DataFrame]:
    path = Path(file_path)
    if not path.is_file():
        raise CheckError(f"segmento inexistente: {path}")
    frame = pd.read_csv(path)
    checks = check_segment_frame(frame, parent_minutes=parent_minutes)
    checks["file"] = _rel_or_abs(path, root)
    checks["sha256"] = sha256_file(path)
    return checks, frame


def verify_closure(
    entries: list[dict],
    root: Path,
    integrity_report: Path | None = None,
    csv_path: Path | None = None,
    protocol: str = PROTOCOL,
) -> list[str]:
    """Verificacao independente do registro terminal (sem circularidade)."""
    expected_days = PROTOCOL_DAYS[protocol]
    reasons: list[str] = []
    if not entries or entries[-1].get("record") != "window_closed":
        return ["manifesto sem registro terminal window_closed"]
    closure = entries[-1]
    body = entries[:-1]
    reasons.extend(verify_chain(entries))
    if closure.get("protocol") != protocol:
        reasons.append(f"fechamento sem protocolo {protocol}")
    if not closure.get("window_id") or not closure.get("start_record_id"):
        reasons.append("fechamento sem window_id/start_record_id")
    try:
        start = _parse_utc(closure.get("window_start_utc", ""), "window_start_utc")
        end = _parse_utc(closure.get("window_end_utc", ""), "window_end_utc")
        closed_at = _parse_utc(closure.get("closed_at_utc", ""), "closed_at_utc")
    except CheckError as exc:
        return reasons + [str(exc)]
    if end - start != pd.Timedelta(days=expected_days):
        reasons.append(
            f"intervalo do fechamento nao cobre exatamente {expected_days} dias"
        )
    if int(closure.get("days", -1)) != expected_days:
        reasons.append(f"days do fechamento difere de {expected_days}")
    if closed_at < end:
        reasons.append("closed_at_utc anterior ao fim real da janela")
    declared = closure.get("segments")
    if not isinstance(declared, list) or len(declared) != expected_days:
        reasons.append(
            f"fechamento nao declara exatamente {expected_days} segmentos"
        )
        declared = declared if isinstance(declared, list) else []
    segments = [e for e in body if e.get("record") == "segment"]
    if len(segments) != expected_days:
        reasons.append(
            f"corpo do manifesto tem {len(segments)} segmentos (esperado {expected_days})"
        )
    triplets = [
        {"seq": e.get("seq"), "file": e.get("file"), "sha256": e.get("sha256")}
        for e in segments
    ]
    if declared != triplets:
        reasons.append("segmentos declarados no fechamento divergem do corpo do manifesto")
    if any(e.get("record") != "segment" for e in body):
        reasons.append("corpo do manifesto contem registro que nao e segment")
    report_path = Path(integrity_report) if integrity_report else Path(
        closure.get("integrity_report_path", "")
    )
    if not report_path.is_absolute():
        report_path = root / report_path if closure.get("integrity_report_path") else report_path
    if not report_path.is_file():
        reasons.append(f"relatorio de integridade inexistente: {report_path}")
    else:
        if sha256_file(report_path) != closure.get("integrity_report_sha256"):
            reasons.append("SHA do relatorio de integridade difere do fechamento")
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            reasons.append(f"relatorio ilegivel: {exc}")
            report = None
        if isinstance(report, dict):
            if report.get("verdict") != "PASS":
                reasons.append("relatorio de integridade nao e PASS")
            if report.get("window_id") != closure.get("window_id"):
                reasons.append("relatorio pertence a outro window_id")
            if report.get("record") == "window_closed":
                reasons.append("relatorio referencia o fechamento (circularidade)")
    csv_final = Path(csv_path) if csv_path else Path(closure.get("consolidated_csv_path", ""))
    if not csv_final.is_absolute():
        csv_final = root / csv_final if closure.get("consolidated_csv_path") else csv_final
    if not csv_final.is_file():
        reasons.append(f"CSV consolidado inexistente: {csv_final}")
    else:
        if str(csv_final.resolve()) != str(Path(closure.get("consolidated_csv_path", "x")).resolve()):
            reasons.append("CSV consolidado difere do caminho vinculado no fechamento")
        if sha256_file(csv_final) != closure.get("consolidated_csv_sha256"):
            reasons.append("SHA do CSV consolidado difere do fechamento")
    return reasons


def verify_manifest(manifest_path: Path, root: Path | None = None,
                    protocol: str = PROTOCOL) -> dict:
    expected_days = PROTOCOL_DAYS[protocol]
    parent_minutes = 15 if protocol == "P5" else 240
    root = Path(root or ROOT).resolve()
    entries = load_manifest(manifest_path)
    reasons: list[str] = []
    reasons.extend(verify_chain(entries))
    segments = [e for e in entries if e.get("record") == "segment"]
    tail = entries[len(segments):]
    if any(e.get("record") != "window_closed" for e in tail):
        reasons.append("registro terminal desconhecido")
    if not segments:
        reasons.append("nenhum segmento no manifesto")
        return _report(manifest_path, None, segments, False, reasons, [], protocol)
    uniform_fields = ("window_id", "start_record_id", "window_start_utc", "window_end_utc")
    for field in uniform_fields:
        values = {e.get(field) for e in segments}
        if len(values) != 1:
            reasons.append(f"campo {field} divergente entre segmentos (mistura de janelas)")
    window_id = segments[0].get("window_id")
    start = _parse_utc(segments[0].get("window_start_utc", ""), "window_start_utc")
    end = _parse_utc(segments[0].get("window_end_utc", ""), "window_end_utc")
    if end - start != pd.Timedelta(days=expected_days):
        reasons.append(
            f"declaracao da janela nao cobre exatamente {expected_days} dias"
        )
    seqs = [e.get("seq") for e in segments]
    if seqs != list(range(len(segments))):
        reasons.append(f"sequencia de segmentos nao contigua a partir de 0: {seqs}")
    if len(segments) > expected_days:
        reasons.append(f"mais de {expected_days} segmentos no manifesto")
    per_segment: list[dict] = []
    prev_last: pd.Timestamp | None = None
    for i, entry in enumerate(segments):
        file_ref = entry.get("file", "")
        path = _segment_path(file_ref, root)
        item: dict = {"seq": entry.get("seq"), "file": file_ref}
        if not path.is_file():
            item["ok"] = False
            item["reasons"] = ["segmento inexistente (sessao incompleta)"]
            reasons.append(f"seq {entry.get('seq')}: segmento inexistente")
            per_segment.append(item)
            prev_last = None
            continue
        try:
            checks, frame = check_segment_file(path, root, parent_minutes=parent_minutes)
        except CheckError as exc:
            item["ok"] = False
            item["reasons"] = [str(exc)]
            reasons.append(f"seq {entry.get('seq')}: {exc}")
            per_segment.append(item)
            continue
        item.update(checks)
        local: list[str] = []
        if checks["sha256"] != entry.get("sha256"):
            local.append("sha256 do arquivo difere do manifesto")
        if checks["rows"] != entry.get("rows"):
            local.append("rows do arquivo difere do manifesto")
        ts = pd.to_datetime(frame["timestamp"], format="ISO8601", utc=True, errors="raise")
        first, last = ts.iloc[0], ts.iloc[-1]
        if first.isoformat() != entry.get("first_ts_utc") or last.isoformat() != entry.get("last_ts_utc"):
            local.append("timestamps do arquivo difere do manifesto")
        if first < start or last >= end:
            local.append("segmento fora do intervalo declarado da janela")
        if not checks["ok"]:
            local.append("checks de conteudo do segmento reprovados")
        if prev_last is not None and first != prev_last + MINUTE:
            local.append(
                f"descontinuidade entre segmentos: {prev_last.isoformat()} -> {first.isoformat()}"
            )
        item["ok"] = not local
        item["reasons"] = local
        if local:
            reasons.append(f"seq {entry.get('seq')}: " + "; ".join(local))
        prev_last = last
        per_segment.append(item)
    # Incompletude NAO reprova o verificador diario (PASS parcial e util);
    # ela invalida o fechamento - gating feito por complete_30d em close_window.
    try:
        complete = (
            len(segments) == expected_days
            and seqs == list(range(expected_days))
            and bool(per_segment)
            and all(item.get("ok") for item in per_segment)
            and _parse_utc(segments[0].get("first_ts_utc", ""), "first") == start
            and _parse_utc(segments[-1].get("last_ts_utc", ""), "last") == end - MINUTE
        )
    except CheckError:
        complete = False
    if entries[-1].get("record") == "window_closed":
        closure_reasons = verify_closure(entries, root, protocol=protocol)
        if closure_reasons:
            reasons.extend(closure_reasons)
    return _report(manifest_path, window_id, segments, complete, reasons, per_segment,
                   protocol)


def _report(manifest_path, window_id, segments, complete, reasons, per_segment,
            protocol: str = PROTOCOL) -> dict:
    verdict = "PASS" if not reasons else "FAIL"
    return {
        "report": "window_integrity",
        "record": "integrity_report",
        "manifest_path": str(Path(manifest_path)),
        "protocol": protocol,
        "window_id": window_id,
        "segments_checked": len(segments),
        "expected_days": PROTOCOL_DAYS[protocol],
        "complete_30d": bool(complete),
        "verdict": verdict,
        "reasons": reasons,
        "per_segment": per_segment,
        "policy_invalidates_window": [
            "candle ausente",
            "candle duplicado",
            "candle fora de ordem",
            "segmento inconsistente",
            "sessao incompleta",
        ],
        "policy_no_repair": [
            "sem interpolacao",
            "sem preenchimento retroativo",
            "sem estender os 30 dias apos consulta de resultados",
            "sem misturar segmentos de janelas diferentes",
            "reinicio exige novo registro de protocolo/inicio antes da nova coleta",
        ],
        "generated_at_utc": _utc_now().isoformat(),
    }


def write_report(report: dict, out: Path) -> None:
    out = Path(out)
    resolved = out.resolve()
    for forbidden in FORBIDDEN_OUTPUTS:
        if resolved == forbidden.resolve():
            raise CheckError(f"destino proibido: {resolved}")
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    tmp.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, out)


def register_segment(
    manifest_path: Path,
    file_path: Path,
    seq: int,
    window_id: str,
    start_record_id: str,
    window_start_utc: str,
    window_end_utc: str,
    root: Path | None = None,
    protocol: str = PROTOCOL,
) -> dict:
    expected_days = PROTOCOL_DAYS[protocol]
    parent_minutes = 15 if protocol == "P5" else 240
    root = Path(root or ROOT).resolve()
    entries = []
    if Path(manifest_path).is_file():
        entries = load_manifest(manifest_path)
    if any(e.get("record") == "window_closed" for e in entries):
        raise CheckError("manifesto ja fechado; reinicio exige novo registro de protocolo/inicio")
    segments = [e for e in entries if e.get("record") == "segment"]
    if entries and any(e.get("record") != "segment" for e in entries):
        raise CheckError("manifesto contem registro nao-segment")
    if seq != len(segments):
        raise CheckError(f"seq esperado {len(segments)}, recebido {seq}")
    start = _parse_utc(window_start_utc, "window_start_utc")
    end = _parse_utc(window_end_utc, "window_end_utc")
    if end - start != pd.Timedelta(days=expected_days):
        raise CheckError(f"janela declarada nao cobre exatamente {expected_days} dias")
    if segments:
        for field, value in (
            ("window_id", window_id),
            ("start_record_id", start_record_id),
            ("window_start_utc", window_start_utc),
            ("window_end_utc", window_end_utc),
        ):
            if segments[0].get(field) != value:
                raise CheckError(f"divergencia de {field} com o manifesto (mistura de janelas)")
    checks, frame = check_segment_file(file_path, root, parent_minutes=parent_minutes)
    if not checks["ok"]:
        raise CheckError(f"segmento reprovado: {checks}")
    ts = pd.to_datetime(frame["timestamp"], format="ISO8601", utc=True, errors="raise")
    if ts.iloc[0] < start or ts.iloc[-1] >= end:
        raise CheckError("segmento fora do intervalo da janela")
    if segments:
        prev_last = _parse_utc(segments[-1]["last_ts_utc"], "prev_last")
        if ts.iloc[0] != prev_last + MINUTE:
            raise CheckError("descontinuidade em relacao ao segmento anterior")
    entry = {
        "record": "segment",
        "window_id": window_id,
        "start_record_id": start_record_id,
        "window_start_utc": window_start_utc,
        "window_end_utc": window_end_utc,
        "seq": seq,
        "file": _rel_or_abs(Path(file_path), root),
        "rows": checks["rows"],
        "first_ts_utc": checks["first_ts_utc"],
        "last_ts_utc": checks["last_ts_utc"],
        "sha256": checks["sha256"],
        "prev_sha256": canonical_sha256(segments[-1]) if segments else None,
        "registered_at_utc": _utc_now().isoformat(),
    }
    append_manifest(manifest_path, entry)
    return entry


def close_window(
    manifest_path: Path,
    integrity_report: Path,
    consolidated_out: Path,
    root: Path | None = None,
    protocol: str = PROTOCOL,
) -> dict:
    expected_days = PROTOCOL_DAYS[protocol]
    root = Path(root or ROOT).resolve()
    entries = load_manifest(manifest_path)
    if any(e.get("record") == "window_closed" for e in entries):
        raise CheckError("janela ja fechada")
    report_path = Path(integrity_report)
    if not report_path.is_file():
        raise CheckError(f"relatorio de integridade inexistente: {report_path}")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("verdict") != "PASS":
        raise CheckError("relatorio de integridade nao e PASS")
    if report.get("protocol", PROTOCOL) != protocol:
        raise CheckError("relatorio de integridade pertence a outro protocolo")
    segments = [e for e in entries if e.get("record") == "segment"]
    if len(segments) != expected_days:
        raise CheckError(f"sessao incompleta: {len(segments)}/{expected_days} segmentos")
    if report.get("window_id") != segments[0].get("window_id"):
        raise CheckError("relatorio pertence a outra janela")
    live = verify_manifest(manifest_path, root, protocol=protocol)
    if live["verdict"] != "PASS" or not live["complete_30d"]:
        raise CheckError(f"verificacao ao vivo reprovou: {live['reasons']}")
    start = _parse_utc(segments[0]["window_start_utc"], "start")
    end = _parse_utc(segments[0]["window_end_utc"], "end")
    now = pd.Timestamp(_utc_now())
    if now.tzinfo is None:
        now = now.tz_localize("UTC")
    if now < end:
        raise CheckError("fechamento anterior ao fim real da janela (relogio)")
    consolidated = Path(consolidated_out)
    if consolidated.exists():
        raise CheckError(f"destino consolidado ja existe: {consolidated}")
    consolidated.parent.mkdir(parents=True, exist_ok=True)
    tmp = consolidated.with_suffix(consolidated.suffix + ".tmp")
    frames = [
        pd.read_csv(_segment_path(e["file"], root)) for e in segments
    ]
    merged = pd.concat(frames, ignore_index=True)
    ts_all = pd.to_datetime(merged["timestamp"], format="ISO8601", utc=True, errors="raise")
    if ts_all.iloc[0] != start or ts_all.iloc[-1] != end - MINUTE:
        tmp.unlink(missing_ok=True)
        raise CheckError("consolidado nao cobre exato [start, end)")
    if ts_all.duplicated().any() or (ts_all.diff().dropna() != MINUTE).any():
        tmp.unlink(missing_ok=True)
        raise CheckError("consolidado com duplicata/lacuna")
    merged.to_csv(tmp, index=False)
    os.replace(tmp, consolidated)
    closure = {
        "record": "window_closed",
        "protocol": protocol,
        "window_id": segments[0]["window_id"],
        "start_record_id": segments[0]["start_record_id"],
        "window_start_utc": segments[0]["window_start_utc"],
        "window_end_utc": segments[0]["window_end_utc"],
        "days": expected_days,
        "segments": [
            {"seq": e["seq"], "file": e["file"], "sha256": e["sha256"]}
            for e in segments
        ],
        "consolidated_csv_path": str(consolidated.resolve()),
        "consolidated_csv_sha256": sha256_file(consolidated),
        "consolidated_rows": int(len(merged)),
        "integrity_report_path": str(report_path.resolve()),
        "integrity_report_sha256": sha256_file(report_path),
        "verdict": "PASS",
        "closed_at_utc": _utc_now().isoformat(),
        "prev_sha256": canonical_sha256(segments[-1]),
        "registered_at_utc": _utc_now().isoformat(),
    }
    closure_reasons = verify_closure(entries + [closure], root, protocol=protocol)
    if closure_reasons:
        consolidated.unlink(missing_ok=True)
        raise CheckError(f"fechamento reprovado na verificacao independente: {closure_reasons}")
    append_manifest(manifest_path, closure)
    return closure


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--protocol", choices=sorted(PROTOCOL_DAYS), default=PROTOCOL)
    sub = parser.add_subparsers(dest="mode", required=True)
    reg = sub.add_parser("register")
    reg.add_argument("--file", type=Path, required=True)
    reg.add_argument("--seq", type=int, required=True)
    reg.add_argument("--window-id", required=True)
    reg.add_argument("--start-record-id", required=True)
    reg.add_argument("--start-utc", required=True)
    reg.add_argument("--end-utc", required=True)
    ver = sub.add_parser("verify")
    ver.add_argument("--out", type=Path, required=True)
    clo = sub.add_parser("close")
    clo.add_argument("--integrity-report", type=Path, required=True)
    clo.add_argument("--consolidated-out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.mode == "register":
            entry = register_segment(
                args.manifest, args.file, args.seq, args.window_id,
                args.start_record_id, args.start_utc, args.end_utc, args.root,
                protocol=args.protocol,
            )
            print(f"segmento registrado seq={entry['seq']} sha={entry['sha256'][:16]}...")
            return 0
        if args.mode == "verify":
            report = verify_manifest(args.manifest, args.root, protocol=args.protocol)
            write_report(report, args.out)
            print(f"verdict={report['verdict']} razoes={len(report['reasons'])}")
            return 0 if report["verdict"] == "PASS" else 1
        closure = close_window(
            args.manifest, args.integrity_report, args.consolidated_out, args.root,
            protocol=args.protocol,
        )
        print(f"janela fechada window_id={closure['window_id']} csv={closure['consolidated_csv_sha256'][:16]}...")
        return 0
    except CheckError as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
