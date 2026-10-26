"""Validate the versioned Trilha A quality report before exposing its metrics."""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

LABEL = "EXPLORATÓRIO — NÃO É PROVA"
INTEGER_FIELDS = (
    "candle_count", "new_candles", "gaps_found", "gaps_filled", "gaps_remaining",
    "duplicates_removed", "age_last_candle_seconds", "pending_backfill_candles",
    "coverage_minutes_present", "coverage_minutes_expected",
)
NUMERIC_FIELDS = INTEGER_FIELDS + ("coverage_percent",)
REQUIRED_FIELDS = (
    "schema_version", "label", "status", "run_at_utc", "symbol", "interval", "message",
    "candle_count", "new_candles", "gaps_found", "gaps_filled", "gaps_remaining",
    "duplicates_removed", "age_last_candle_seconds", "pending_backfill_candles",
    "coverage_percent", "coverage_minutes_present", "coverage_minutes_expected",
    "first_candle_open_time_utc", "daily_gaps",
)


def _empty_fields(reason: str, status: str = "awaiting") -> dict[str, Any]:
    return {
        "label": LABEL,
        "status": status,
        "symbol": "BTCUSDT",
        "interval": "1m",
        "latest_run_at_utc": None,
        "latest_candle_open_time_utc": None,
        "candle_count_1m": None,
        "new_candles": None,
        "gaps_found": None,
        "gaps_filled": None,
        "gaps_remaining": None,
        "duplicates_removed": None,
        "age_last_candle_seconds": None,
        "pending_backfill_candles": None,
        "coverage_percent": None,
        "coverage_minutes_present": None,
        "coverage_minutes_expected": None,
        "first_candle_open_time_utc": None,
        "daily_gaps": [],
        "message": reason,
        "report_available": False,
        "quality_report_reason": reason,
        "latest_report_url": None,
        "latest_run_url": None,
    }


def _validate_report(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return "raiz JSON não é um objeto."
    missing = [name for name in REQUIRED_FIELDS if name not in payload]
    if missing:
        return "campos obrigatórios ausentes: " + ", ".join(missing[:5]) + "."
    if payload.get("schema_version") != 1:
        return "schema_version incompatível."
    for name in ("status", "run_at_utc", "symbol", "interval", "message"):
        if not isinstance(payload.get(name), str) or not payload[name].strip():
            return f"campo obrigatório {name} ausente ou inválido."
    if not isinstance(payload.get("daily_gaps"), list):
        return "daily_gaps não é uma lista."
    for name in NUMERIC_FIELDS:
        value = payload.get(name)
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            return f"campo numérico {name} inválido."
        if name in INTEGER_FIELDS and not isinstance(value, int):
            return f"campo inteiro {name} inválido."
    coverage = payload.get("coverage_percent")
    if coverage is not None and coverage > 100:
        return "coverage_percent fora do intervalo 0–100."
    if payload.get("first_candle_open_time_utc") is not None and not isinstance(payload["first_candle_open_time_utc"], str):
        return "first_candle_open_time_utc inválido."
    if payload.get("last_candle_open_time_utc") is not None and not isinstance(payload["last_candle_open_time_utc"], str):
        return "last_candle_open_time_utc inválido."
    return None


def read_quality_report(path: Path) -> dict[str, Any]:
    """Return safe feed fields and the original payload, or only explicit unknown values."""
    path = Path(path)
    if not path.is_file():
        reason = "Relatório de qualidade ausente na branch learning-state (learning/reports/latest.json); métricas não disponíveis."
        return {"learning": _empty_fields(reason), "report": None}

    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        reason = "Relatório de qualidade ilegível em learning-state; métricas omitidas."
        return {"learning": _empty_fields(reason, "unknown"), "report": None}

    if not raw.strip():
        reason = "Relatório de qualidade vazio na branch learning-state (learning/reports/latest.json); métricas omitidas."
        return {"learning": _empty_fields(reason, "unknown"), "report": None}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        reason = "Relatório de qualidade corrompido em learning-state (JSON inválido); métricas omitidas."
        return {"learning": _empty_fields(reason, "unknown"), "report": None}

    validation_error = _validate_report(payload)
    if validation_error:
        reason = "Relatório de qualidade inválido/corrompido em learning-state: " + validation_error + " Métricas omitidas."
        return {"learning": _empty_fields(reason, "unknown"), "report": None}

    run_id = payload.get("run_id")
    run_url = (
        "https://github.com/aquinoares/fvt-quant-research/actions/runs/" + run_id
        if isinstance(run_id, (str, int)) and re.fullmatch(r"[0-9]+", str(run_id))
        else None
    )
    fields = {
        "label": payload.get("label") if isinstance(payload.get("label"), str) else LABEL,
        "status": payload["status"],
        "symbol": payload["symbol"],
        "interval": payload["interval"],
        "latest_run_at_utc": payload["run_at_utc"],
        "latest_candle_open_time_utc": payload.get("last_candle_open_time_utc"),
        "candle_count_1m": payload["candle_count"],
        "new_candles": payload["new_candles"],
        "gaps_found": payload["gaps_found"],
        "gaps_filled": payload["gaps_filled"],
        "gaps_remaining": payload["gaps_remaining"],
        "duplicates_removed": payload["duplicates_removed"],
        "age_last_candle_seconds": payload["age_last_candle_seconds"],
        "pending_backfill_candles": payload["pending_backfill_candles"],
        "coverage_percent": payload["coverage_percent"],
        "coverage_minutes_present": payload["coverage_minutes_present"],
        "coverage_minutes_expected": payload["coverage_minutes_expected"],
        "first_candle_open_time_utc": payload["first_candle_open_time_utc"],
        "daily_gaps": payload["daily_gaps"],
        "message": payload["message"],
        "report_available": True,
        "quality_report_reason": None,
        "latest_report_url": "https://github.com/aquinoares/fvt-quant-research/blob/learning-state/learning/reports/latest.md",
        "latest_run_url": run_url,
    }
    return {"learning": fields, "report": payload}
