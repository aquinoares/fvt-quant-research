from __future__ import annotations
import hashlib
import sys
from pathlib import Path
import numpy as np
import pandas as pd

EXPECTED_CSV_SHA256 = "604835C55D98319CF6F26516040F6F285E02152B6EE984238C0D3359C2DBDE41"
EXPECTED_ROWS = 129_600
ONE_MINUTE = pd.Timedelta(minutes=1)


def find_column(columns, aliases):
    normalized = {str(column).strip().lower(): column for column in columns}
    for alias in aliases:
        if alias in normalized:
            return normalized[alias]
    return None


def parse_timestamp(series):
    if pd.api.types.is_numeric_dtype(series):
        values = pd.to_numeric(series, errors="coerce")
        finite = values.dropna()
        if finite.empty:
            return pd.to_datetime(series, utc=True, errors="coerce")
        median = float(finite.abs().median())
        if median >= 1e17:
            unit = "ns"
        elif median >= 1e14:
            unit = "us"
        elif median >= 1e11:
            unit = "ms"
        else:
            unit = "s"
        print("Numeric timestamp unit:", unit)
        return pd.to_datetime(values, unit=unit, utc=True, errors="coerce")
    return pd.to_datetime(series, utc=True, errors="coerce")


def main():
    if len(sys.argv) != 3:
        print("Usage: audit_history.py <csv> <project_root>")
        return 2
    csv_path = Path(sys.argv[1])
    root = Path(sys.argv[2])
    raw = csv_path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest().upper()
    frame = pd.read_csv(csv_path)
    columns = frame.columns

    print("========== HISTORICAL DATA IDENTITY ==========")
    print("File:", str(csv_path))
    print("Bytes:", f"{len(raw):,}")
    print("SHA256:", digest)
    print("Matches SHA reported by download:", digest == EXPECTED_CSV_SHA256)
    print("Rows:", f"{len(frame):,}", "| expected:", f"{EXPECTED_ROWS:,}")
    print("Columns:", list(columns))

    time_col = find_column(columns, ("timestamp", "timestamp_utc", "open_time", "open_time_utc", "open_time_ms", "time", "datetime", "date"))
    if time_col is None:
        print("FAIL: timestamp column not found.")
        return 3
    timestamps = parse_timestamp(frame[time_col])
    invalid_ts = int(timestamps.isna().sum())
    valid_ts = timestamps.dropna()
    now = pd.Timestamp.now(tz="UTC")

    print("\n========== TIMESTAMP AUDIT ==========")
    print("Timestamp column:", time_col)
    print("Machine UTC now:", now.isoformat())
    print("Invalid timestamps:", invalid_ts)
    duplicate_count = int(valid_ts.duplicated().sum())
    deltas = valid_ts.diff().dropna()
    out_of_order = int((deltas < pd.Timedelta(0)).sum())
    zero_steps = int((deltas == pd.Timedelta(0)).sum())
    irregular = int((deltas != ONE_MINUTE).sum())
    gap_steps = deltas[deltas > ONE_MINUTE]
    missing_estimate = sum(max(0, int(delta.total_seconds() // 60) - 1) for delta in gap_steps)
    print("Duplicate timestamps:", duplicate_count)
    print("Out-of-order steps:", out_of_order)
    print("Zero-length steps:", zero_steps)
    print("Intervals different from 1 minute:", irregular)
    print("Intervals longer than 1 minute:", int(len(gap_steps)))
    print("Estimated missing minutes:", int(missing_estimate))
    if len(valid_ts):
        first_ts, last_ts = valid_ts.iloc[0], valid_ts.iloc[-1]
        last_close = last_ts + ONE_MINUTE
        print("First open UTC:", first_ts.isoformat())
        print("Last open UTC:", last_ts.isoformat())
        print("Last open Recife:", last_ts.tz_convert("America/Recife").isoformat())
        print("Expected last candle close:", last_close.isoformat())
        print("Last candle should be closed:", bool(last_close <= now))
        print("Timestamps in future:", int((valid_ts > now).sum()))
        print("Candles not yet closed:", int(((valid_ts + ONE_MINUTE) > now).sum()))
        print("Total span:", str(last_ts - first_ts))

    print("\n========== OHLCV VALIDATION ==========")
    open_col = find_column(columns, ("open",))
    high_col = find_column(columns, ("high",))
    low_col = find_column(columns, ("low",))
    close_col = find_column(columns, ("close",))
    volume_col = find_column(columns, ("volume", "base_volume"))
    needed = [open_col, high_col, low_col, close_col, volume_col]
    if any(col is None for col in needed):
        print("FAIL: OHLCV columns not found:", dict(open=open_col, high=high_col, low=low_col, close=close_col, volume=volume_col))
        return 4
    numeric = frame[needed].apply(pd.to_numeric, errors="coerce")
    missing_numeric = int(numeric.isna().sum().sum())
    finite_matrix = np.isfinite(numeric.to_numpy(dtype="float64", na_value=np.nan))
    nonfinite_rows = int((~finite_matrix.all(axis=1)).sum())
    price_cols = [open_col, high_col, low_col, close_col]
    nonpositive_price_rows = int((numeric[price_cols] <= 0).any(axis=1).sum())
    negative_volume_rows = int((numeric[volume_col] < 0).sum())
    high_invalid = numeric[high_col] < numeric[[open_col, close_col, low_col]].max(axis=1)
    low_invalid = numeric[low_col] > numeric[[open_col, close_col, high_col]].min(axis=1)
    range_invalid_rows = int((high_invalid | low_invalid).sum())
    print("Missing/non-numeric OHLCV values:", missing_numeric)
    print("Rows with non-finite values:", nonfinite_rows)
    print("Rows with non-positive prices:", nonpositive_price_rows)
    print("Rows with negative volume:", negative_volume_rows)
    print("Rows with inconsistent OHLC:", range_invalid_rows)

    close_time_col = find_column(columns, ("close_time",))
    close_time_bad = 0
    if close_time_col is not None:
        close_times = parse_timestamp(frame[close_time_col])
        expected_close_times = timestamps + pd.Timedelta(milliseconds=999) + pd.Timedelta(seconds=59)
        close_time_bad = int((close_times != expected_close_times).sum())
        print("Close-time mismatches (expected open + 59.999 seconds):", close_time_bad)
    else:
        print("Close-time field: not present; optional check skipped.")

    print("\n========== SOURCE FILE ENCODING ==========")
    encoding_ok = True
    mojibake_found = False
    markers = (chr(0x00C3), chr(0x00C2), chr(0x00E2) + chr(0x20AC), chr(0x00F0) + chr(0x0178))
    for relative in ("src/convergencia/signals.py", "src/convergencia/data.py", "src/convergencia/backtest.py"):
        path = root / relative
        content = path.read_bytes()
        print(relative, "SHA256:", hashlib.sha256(content).hexdigest().upper())
        try:
            decoded = content.decode("utf-8", errors="strict")
            print("  Strict UTF-8: OK")
            suspicious = [token.encode("unicode_escape").decode("ascii") for token in markers if token in decoded]
            if suspicious:
                mojibake_found = True
                print("  Possible mojibake markers:", suspicious)
            else:
                print("  Common mojibake markers: none found")
        except UnicodeDecodeError as exc:
            encoding_ok = False
            print("  Strict UTF-8: FAILED:", str(exc))

    temporal_ok = (
        invalid_ts == 0 and duplicate_count == 0 and out_of_order == 0 and zero_steps == 0
        and irregular == 0 and missing_estimate == 0 and len(valid_ts) == len(frame)
        and len(valid_ts) > 0 and (valid_ts.max() + ONE_MINUTE) <= now
        and int((valid_ts > now).sum()) == 0
    )
    ohlcv_ok = (missing_numeric == 0 and nonfinite_rows == 0 and nonpositive_price_rows == 0
                and negative_volume_rows == 0 and range_invalid_rows == 0 and close_time_bad == 0)
    rows_ok = len(frame) == EXPECTED_ROWS
    print("\n========== RESULT ==========")
    print("Temporal quality:", "PASS" if temporal_ok else "REVIEW")
    print("OHLCV quality:", "PASS" if ohlcv_ok else "REVIEW")
    print("Expected row count:", rows_ok)
    print("UTF-8 source files:", "PASS" if encoding_ok else "REVIEW")
    print("Possible mojibake in source files:", mojibake_found)
    print("No trading signals or orders were generated.")
    return 0 if temporal_ok and ohlcv_ok and rows_ok and encoding_ok else 5

if __name__ == "__main__":
    raise SystemExit(main())
