import csv
from pathlib import Path

from learning.state_persistence import merge_csv_directories


FIELDS = ["symbol", "interval", "open_time_ms", "open_time_utc", "open", "high", "low", "close", "volume"]


def _write(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _row(timestamp, close):
    return {
        "symbol": "BTCUSDT", "interval": "1m", "open_time_ms": str(timestamp),
        "open_time_utc": f"2026-10-25T00:{timestamp // 60000:02d}:00Z",
        "open": "1", "high": "2", "low": "0.5", "close": str(close), "volume": "10",
    }


def test_reapply_unions_concurrent_rows_without_overwriting_latest_branch_value(tmp_path):
    source = tmp_path / "generated" / "BTCUSDT_1m" / "2026-10.csv"
    target = tmp_path / "latest-state" / "BTCUSDT_1m" / "2026-10.csv"
    _write(source, [_row(60_000, "1.5"), _row(180_000, "1.8")])
    _write(target, [_row(60_000, "1.6"), _row(120_000, "1.7")])

    assert merge_csv_directories(source.parent.parent, target.parent.parent) == 3
    with target.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert [int(row["open_time_ms"]) for row in rows] == [60_000, 120_000, 180_000]
    assert rows[0]["close"] == "1.6"
    assert rows[1]["close"] == "1.7"
    assert rows[2]["close"] == "1.8"


def test_reapplying_the_same_generated_rows_is_idempotent(tmp_path):
    source_dir = tmp_path / "generated" / "BTCUSDT_1m"
    target_dir = tmp_path / "latest-state" / "BTCUSDT_1m"
    source = source_dir / "2026-10.csv"
    target = target_dir / "2026-10.csv"
    rows = [_row(60_000, "1.5"), _row(120_000, "1.6")]
    _write(source, rows)
    _write(target, rows)

    merge_csv_directories(source_dir.parent, target_dir.parent)
    merge_csv_directories(source_dir.parent, target_dir.parent)
    with target.open(encoding="utf-8", newline="") as stream:
        actual = list(csv.DictReader(stream))
    assert len(actual) == 2
    assert len({(row["symbol"], row["interval"], row["open_time_ms"]) for row in actual}) == 2
