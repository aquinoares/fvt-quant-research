"""Persist generated Trilha A state without losing concurrent branch updates."""

from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
import tempfile
from pathlib import Path
from typing import Any

KEY_COLUMNS = ("symbol", "interval", "open_time_ms")
BACKTEST_FILES = ("latest_backtest.json", "latest_backtest.md")


def _read_partition(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        fieldnames = list(reader.fieldnames or [])
        if not fieldnames or any(name not in fieldnames for name in KEY_COLUMNS):
            raise ValueError(f"CSV sem cabeçalho/chave canônica: {path}")
        rows = []
        for row in reader:
            if not row or all(value in (None, "") for value in row.values()):
                continue
            if any(not row.get(name) for name in KEY_COLUMNS):
                raise ValueError(f"Linha sem chave canônica em {path}")
            rows.append({name: (row.get(name) or "") for name in fieldnames})
        return fieldnames, rows


def _timestamp_key(row: dict[str, str]) -> tuple[int, str]:
    raw = row["open_time_ms"]
    try:
        return (int(raw), raw)
    except (TypeError, ValueError):
        return (math.inf, str(raw))


def merge_csv_directories(source_dir: Path, target_dir: Path) -> int:
    """Union source partitions into target, preserving target values on duplicate keys."""
    source_dir = Path(source_dir)
    target_dir = Path(target_dir)
    source_files = {p.relative_to(source_dir) for p in source_dir.rglob("*.csv")} if source_dir.is_dir() else set()
    target_files = {p.relative_to(target_dir) for p in target_dir.rglob("*.csv")} if target_dir.is_dir() else set()
    merged_rows = 0

    for relative in sorted(source_files | target_files, key=lambda p: p.as_posix()):
        source_path = source_dir / relative
        target_path = target_dir / relative
        source_fields, source_rows = _read_partition(source_path) if source_path.is_file() else ([], [])
        target_fields, target_rows = _read_partition(target_path) if target_path.is_file() else ([], [])
        fieldnames = target_fields or source_fields
        if source_fields and target_fields and source_fields != target_fields:
            raise ValueError(f"Esquema CSV divergente entre origem e estado: {relative}")
        if not fieldnames:
            continue

        # Keep the latest branch's existing row for a duplicate candle. Source-only
        # rows are appended, so a stale worktree cannot erase newer remote candles.
        rows_by_key: dict[tuple[str, str, str], dict[str, str]] = {}
        for row in target_rows:
            key = tuple(row[name] for name in KEY_COLUMNS)
            rows_by_key.setdefault(key, row)
        for row in source_rows:
            key = tuple(row[name] for name in KEY_COLUMNS)
            rows_by_key.setdefault(key, row)

        ordered = sorted(rows_by_key.values(), key=_timestamp_key)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="", delete=False, dir=target_path.parent) as stream:
            writer = csv.DictWriter(stream, fieldnames=fieldnames, extrasaction="ignore", lineterminator="\n")
            writer.writeheader()
            writer.writerows({name: row.get(name, "") for name in fieldnames} for row in ordered)
            temporary = Path(stream.name)
        temporary.replace(target_path)
        merged_rows += len(ordered)
    return merged_rows


def _run_epoch(path: Path) -> int | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        value = payload.get("run_at_epoch_ms") if isinstance(payload, dict) else None
        return value if isinstance(value, int) and not isinstance(value, bool) else None
    except (OSError, json.JSONDecodeError):
        return None


def _copy_reports(source: Path, target: Path) -> None:
    if not source.is_dir():
        return
    target.mkdir(parents=True, exist_ok=True)
    source_latest = source / "latest.json"
    target_latest = target / "latest.json"
    source_epoch = _run_epoch(source_latest) if source_latest.is_file() else None
    target_epoch = _run_epoch(target_latest) if target_latest.is_file() else None
    source_is_latest = source_latest.is_file() and (
        target_epoch is None or (source_epoch is not None and source_epoch >= target_epoch)
    )

    for source_path in source.rglob("*"):
        if not source_path.is_file():
            continue
        relative = source_path.relative_to(source)
        target_path = target / relative
        target_path.parent.mkdir(parents=True, exist_ok=True)
        if relative.as_posix() in ("latest.json", "latest.md") and not source_is_latest:
            continue
        if relative.name not in ("latest.json", "latest.md") and target_path.exists():
            continue
        shutil.copy2(source_path, target_path)


def merge_generated_state(source_root: Path, target_root: Path) -> None:
    """Reapply one run's generated outputs atop the latest learning-state worktree."""
    source_root = Path(source_root)
    target_root = Path(target_root)
    merge_csv_directories(source_root / "data", target_root / "data")
    _copy_reports(source_root / "reports", target_root / "reports")

    source_experiments = source_root / "experiments"
    target_experiments = target_root / "experiments"
    target_experiments.mkdir(parents=True, exist_ok=True)
    for filename in BACKTEST_FILES:
        source_path = source_experiments / filename
        if source_path.is_file():
            shutil.copy2(source_path, target_experiments / filename)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--target-root", type=Path, required=True)
    args = parser.parse_args()
    merge_generated_state(args.source_root, args.target_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
