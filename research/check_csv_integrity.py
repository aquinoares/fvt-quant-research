#!/usr/bin/env python3
"""Verifica integridade e continuidade temporal do CSV OHLCV auditado.

Somente leitura. Nao altera o CSV. Emite JSON em research/out/.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CSV = ROOT / "data" / "raw" / "BTCUSDT_1m.csv"
OUT = ROOT / "research" / "out" / "csv_integrity.json"
EXPECTED_SHA256 = "604835c55d98319cf6f26516040f6f285e02152b6ee984238c0d3359c2dbde41"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    digest = sha256_file(CSV)
    raw = pd.read_csv(CSV)
    ts = pd.to_datetime(raw["timestamp"], format="ISO8601", utc=True, errors="coerce")
    report: dict = {
        "csv": str(CSV),
        "sha256": digest,
        "sha256_matches_audit_constant": digest == EXPECTED_SHA256,
        "rows": int(len(raw)),
        "columns": list(raw.columns),
        "timestamp_parse_failures": int(ts.isna().sum()),
        "first_timestamp_utc": ts.iloc[0].isoformat(),
        "last_timestamp_utc": ts.iloc[-1].isoformat(),
        "duplicate_timestamps": int(ts.duplicated().sum()),
        "monotonic_increasing": bool(ts.is_monotonic_increasing),
    }
    diffs = ts.diff().dropna()
    bad = diffs != pd.Timedelta(minutes=1)
    report["non_1min_gaps_or_jumps"] = int(bad.sum())
    if bad.any():
        idx = np.flatnonzero(bad.to_numpy())[:20]
        report["gap_examples"] = [
            {
                "row": int(i) + 1,
                "prev": ts.iloc[int(i)].isoformat(),
                "cur": ts.iloc[int(i) + 1].isoformat(),
                "delta": str(diffs.iloc[int(i)]),
            }
            for i in idx
        ]
    span = (ts.iloc[-1] - ts.iloc[0]).total_seconds() / 60.0 + 1
    report["expected_rows_from_span"] = int(span)
    report["rows_match_span"] = int(len(raw)) == int(span)
    ohlcv = raw[["open", "high", "low", "close", "volume"]].apply(pd.to_numeric, errors="coerce")
    report["non_finite_ohlcv_cells"] = int((~np.isfinite(ohlcv.to_numpy(dtype="float64"))).sum())
    report["non_positive_prices"] = int((ohlcv[["open", "high", "low", "close"]] <= 0).sum().sum())
    report["negative_volume"] = int((ohlcv["volume"] < 0).sum())
    invalid_range = (raw["high"] < raw[["open", "close", "low"]].max(axis=1)) | (
        raw["low"] > raw[["open", "close", "high"]].min(axis=1)
    )
    report["ohlc_range_violations"] = int(invalid_range.sum())
    parent_counts = ts.dt.floor("15min").value_counts().sort_index()
    report["incomplete_15m_parent_bars"] = int((parent_counts != 15).sum())
    parent_counts5 = ts.dt.floor("5min").value_counts().sort_index()
    report["incomplete_5m_parent_bars"] = int((parent_counts5 != 5).sum())
    report["verdict"] = (
        "PASS"
        if (
            report["timestamp_parse_failures"] == 0
            and report["duplicate_timestamps"] == 0
            and report["non_1min_gaps_or_jumps"] == 0
            and report["monotonic_increasing"]
            and report["rows_match_span"]
            and report["non_finite_ohlcv_cells"] == 0
            and report["non_positive_prices"] == 0
            and report["negative_volume"] == 0
            and report["ohlc_range_violations"] == 0
        )
        else "FAIL"
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
