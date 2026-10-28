import csv
from pathlib import Path

import pytest

from learning import collector

MIN = collector.MINUTE_MS
NOW = 1_704_067_200_000  # 2024-01-01T00:00:00Z


def raw_kline(open_ms, close_ms=None, close="1.5"):
    if close_ms is None:
        close_ms = open_ms + MIN - 1
    return [open_ms, "1.0", "2.0", "0.5", close, "10.0", close_ms, "15.0", 5, "4.0", "6.0", "0"]


def row(open_ms, interval="1m", open_price="1.0", high="2.0", low="0.5", close="1.5"):
    duration = collector.HOUR4_MS if interval == "4h" else MIN
    return {
        "symbol": "BTCUSDT", "interval": interval,
        "open_time_ms": str(open_ms), "open_time_utc": collector.ms_to_iso(open_ms),
        "open": open_price, "high": high, "low": low, "close": close, "volume": "10.0",
        "close_time_ms": str(open_ms + duration - 1),
        "close_time_utc": collector.ms_to_iso(open_ms + duration - 1),
        "quote_volume": "15.0", "trade_count": "5", "taker_buy_base_volume": "4.0",
        "taker_buy_quote_volume": "6.0",
    }


def write_partition(root: Path, timestamps, duplicate_first=False):
    records = [row(ts) for ts in timestamps]
    if duplicate_first and records:
        records.insert(1, dict(records[0]))
    if not records:
        folder = root / "data" / "BTCUSDT_1m"
        folder.mkdir(parents=True, exist_ok=True)
        return folder / "empty.csv"
    path = collector.month_path(root / "data", "1m", int(records[0]["open_time_ms"]))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=collector.COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)
    return path


def fake_fetcher(rows):
    def fetch(start_ms, end_ms, limit):
        return [r for r in rows if start_ms <= int(r[0]) <= end_ms][:limit]
    return fetch


def test_fills_internal_gap_and_backfills_tail(tmp_path):
    t0 = NOW - 5 * MIN
    write_partition(tmp_path, [t0, t0 + 2 * MIN])
    source = [raw_kline(t0 + i * MIN) for i in (1, 3, 4)]
    report = collector.collect(
        tmp_path, now_ms=NOW, fetcher=fake_fetcher(source),
        max_requests=10, seed_utc=collector.ms_to_iso(t0),
    )
    assert report["gaps_found"] == 1
    assert report["gaps_filled"] == 1
    assert report["gaps_remaining"] == 0
    assert report["new_candles"] == 3
    assert report["candle_count"] == 5
    assert report["status"] == "ok"
    assert (tmp_path / "reports" / "latest.md").is_file()


def test_persisted_duplicates_are_removed(tmp_path):
    t0 = NOW - MIN
    path = write_partition(tmp_path, [t0], duplicate_first=True)
    report = collector.collect(
        tmp_path, now_ms=NOW, fetcher=fake_fetcher([]),
        seed_utc=collector.ms_to_iso(t0),
    )
    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 1
    assert report["duplicates_removed"] == 1
    assert report["candle_count"] == 1


def test_request_budget_leaves_large_backfill_pending(tmp_path):
    seed = collector.parse_utc_ms(collector.DEFAULT_SEED_UTC)
    page_rows = [raw_kline(seed + i * MIN) for i in range(collector.API_LIMIT)]
    calls = []

    def fetch(start, end, limit):
        calls.append((start, end, limit))
        return [r for r in page_rows if start <= r[0] <= end][:limit]

    report = collector.collect(
        tmp_path, now_ms=NOW, fetcher=fetch, max_requests=2,
        seed_utc=collector.DEFAULT_SEED_UTC,
    )
    assert report["requests_used"] <= 2
    assert len(calls) <= 2
    assert report["pending_backfill_candles"] > 0
    assert report["status"] == "backfill_pending"
    assert report["empty_pages"] == 1
    assert report["queued_ranges_remaining"] == 0


def test_budget_exhaustion_records_remaining_queue_and_pending(tmp_path):
    seed = collector.parse_utc_ms(collector.DEFAULT_SEED_UTC)

    def fetch(start, end, limit):
        count = min(limit, (end - start) // MIN + 1)
        return [raw_kline(start + i * MIN) for i in range(count)]

    report = collector.collect(
        tmp_path, now_ms=NOW, fetcher=fetch, max_requests=2,
        seed_utc=collector.DEFAULT_SEED_UTC,
    )
    assert report["requests_used"] == 2
    assert report["new_candles"] == 2 * collector.API_LIMIT
    assert report["queued_ranges_remaining"] == 1
    assert report["pending_backfill_candles"] > 0
    assert report["status"] == "backfill_pending"
    markdown = (tmp_path / "reports" / "latest.md").read_text(encoding="utf-8")
    assert "Faixas ainda na fila de backfill: 1." in markdown


def test_open_candle_is_discarded():
    current_open = (NOW // MIN) * MIN
    assert collector.normalize_kline(raw_kline(current_open, current_open + MIN - 1), NOW) is None


def test_tail_is_prioritized_over_historical_gap_when_budget_is_one(tmp_path):
    t0 = NOW - 10 * MIN
    write_partition(tmp_path, [t0, t0 + 2 * MIN])
    source = [raw_kline(t0 + i * MIN) for i in range(10)]
    calls = []

    def fetch(start, end, limit):
        calls.append((start, end, limit))
        return [r for r in source if start <= r[0] <= end][:limit]

    report = collector.collect(
        tmp_path, now_ms=NOW, fetcher=fetch, max_requests=1,
        seed_utc=collector.ms_to_iso(t0),
    )
    assert len(calls) == 1
    assert calls[0][0] == t0 + 3 * MIN
    assert report["new_candles"] == 7
    assert report["gaps_remaining"] == 1
    folder = tmp_path / "data" / "BTCUSDT_1m"
    persisted = {
        int(r["open_time_ms"])
        for path in folder.glob("*.csv")
        for r in csv.DictReader(path.open(encoding="utf-8", newline=""))
    }
    assert t0 + MIN not in persisted
    assert t0 + 9 * MIN in persisted


def test_empty_api_is_recorded_without_inventing_data(tmp_path):
    report = collector.collect(tmp_path, now_ms=NOW, fetcher=fake_fetcher([]))
    assert report["status"] == "empty_api"
    assert report["candle_count"] == 0
    assert report["last_candle_open_time_utc"] is None
    assert "nenhum dado foi inventado" in report["message"]


@pytest.mark.parametrize("status_code", [403, 451])
def test_http_geoblock_is_reported_clearly(tmp_path, status_code):
    def blocked(_start, _end, _limit):
        raise collector.APIError(status_code, f"HTTP {status_code}")

    report = collector.collect(tmp_path, now_ms=NOW, fetcher=blocked)
    assert report["status"] == "blocked"
    assert report["api_http_status"] == status_code
    assert "bloqueio geográfico/regional" in report["message"]
    assert report["candle_count"] == 0
    assert (tmp_path / "reports" / "latest.json").is_file()


def test_4h_aggregation_is_aligned_and_requires_240_contiguous_minutes(tmp_path):
    bucket = NOW - collector.HOUR4_MS
    folder = tmp_path / "data" / "BTCUSDT_1m"
    folder.mkdir(parents=True)
    path = folder / "2023-12.csv"
    records = [row(bucket + i * MIN) for i in range(240)]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=collector.COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)
    count = collector.aggregate_4h(tmp_path / "data", now_ms=NOW)
    fourh = list((tmp_path / "data" / "BTCUSDT_4h").glob("*.csv"))
    assert count == 1 and len(fourh) == 1
    with fourh[0].open(encoding="utf-8", newline="") as stream:
        result = list(csv.DictReader(stream))
    assert int(result[0]["open_time_ms"]) == bucket
    assert result[0]["interval"] == "4h"
    assert int(result[0]["close_time_ms"]) == bucket + collector.HOUR4_MS - 1

    fourh[0].unlink()
    incomplete = [r for i, r in enumerate(records) if i != 123]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=collector.COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(incomplete)
    assert collector.aggregate_4h(tmp_path / "data", now_ms=NOW) == 0
    assert not fourh[0].exists()


def test_collection_is_idempotent_for_duplicate_api_rows(tmp_path):
    t0 = NOW - 2 * MIN
    first, second = raw_kline(t0), raw_kline(t0 + MIN)
    def fetch(start, end, limit):
        return [r for r in [first, first, second] if start <= r[0] <= end]
    report = collector.collect(tmp_path, now_ms=NOW, fetcher=fetch, seed_utc=collector.ms_to_iso(t0))
    assert report["new_candles"] == 2
    assert report["duplicates_removed"] == 1
    assert report["candle_count"] == 2


def test_coverage_summary_reports_first_candle_expected_minutes_and_daily_gaps():
    t0 = collector.parse_utc_ms("2024-01-01T23:58:00Z")
    result = collector.summarize_coverage([t0, t0 + MIN, t0 + 3 * MIN])
    assert result["first_candle_open_time_utc"] == "2024-01-01T23:58:00Z"
    assert result["coverage_minutes_present"] == 3
    assert result["coverage_minutes_expected"] == 4
    assert result["coverage_percent"] == 75.0
    assert result["daily_gaps"] == [{"date_utc": "2024-01-02", "missing_minutes": 1}]


def test_coverage_without_candles_is_unknown_not_zero():
    result = collector.summarize_coverage([])
    assert result["coverage_percent"] is None
    assert result["coverage_minutes_present"] is None
    assert result["coverage_minutes_expected"] is None
    assert result["coverage_target_percent"] is None
    assert result["coverage_target_minutes_present"] is None
    assert result["coverage_target_minutes_expected"] is None
    assert result["first_candle_open_time_utc"] is None


def test_in_range_coverage_is_100_but_target_coverage_exposes_missing_tail(tmp_path):
    t0 = NOW - 1_000 * MIN
    write_partition(tmp_path, [t0 + i * MIN for i in range(5)])
    report = collector.collect(
        tmp_path, now_ms=NOW, fetcher=fake_fetcher([]),
        seed_utc=collector.ms_to_iso(t0),
    )
    assert report["coverage_percent"] == 100.0
    assert report["coverage_minutes_present"] == 5
    assert report["coverage_minutes_expected"] == 5
    last_closed = (NOW // MIN) * MIN - MIN
    assert report["coverage_target_minutes_expected"] == (last_closed - t0) // MIN + 1
    assert report["coverage_target_minutes_present"] == 5
    assert report["coverage_target_percent"] < 1.0
    assert report["coverage_target_utc"] == collector.ms_to_iso(last_closed)


def test_summarize_coverage_without_target_leaves_target_metrics_unknown():
    t0 = collector.parse_utc_ms("2024-01-01T23:58:00Z")
    result = collector.summarize_coverage([t0, t0 + MIN, t0 + 3 * MIN])
    assert result["coverage_percent"] == 75.0
    assert result["coverage_target_percent"] is None
    assert result["coverage_target_minutes_present"] is None
    assert result["coverage_target_minutes_expected"] is None


def test_markdown_report_separates_in_range_and_target_coverage(tmp_path):
    t0 = NOW - 100 * MIN
    write_partition(tmp_path, [t0 + i * MIN for i in range(4)])
    collector.collect(
        tmp_path, now_ms=NOW, fetcher=fake_fetcher([]),
        seed_utc=collector.ms_to_iso(t0),
    )
    markdown = (tmp_path / "reports" / "latest.md").read_text(encoding="utf-8")
    assert "Cobertura dentro do intervalo observado" in markdown
    assert "Cobertura total até o instante-alvo" in markdown


def full_generator_fetcher():
    def fetch(start, end, limit):
        count = min(limit, (end - start) // MIN + 1)
        return [raw_kline(start + i * MIN) for i in range(count)]
    return fetch


def persisted_opens(root: Path) -> list[int]:
    folder = root / "data" / "BTCUSDT_1m"
    return sorted(
        int(r["open_time_ms"])
        for path in folder.glob("*.csv")
        for r in csv.DictReader(path.open(encoding="utf-8", newline=""))
    )


def test_resume_mid_tail_continues_from_last_persisted_candle(tmp_path):
    t0 = NOW - 2_500 * MIN
    fetch = full_generator_fetcher()
    first = collector.collect(
        tmp_path, now_ms=NOW, fetcher=fetch, max_requests=1,
        seed_utc=collector.ms_to_iso(t0),
    )
    assert first["requests_used"] == 1
    assert first["new_candles"] == collector.API_LIMIT
    assert first["queued_ranges_remaining"] == 1
    assert persisted_opens(tmp_path) == [t0 + i * MIN for i in range(collector.API_LIMIT)]

    calls = []
    def recording_fetch(start, end, limit):
        calls.append(start)
        return fetch(start, end, limit)

    second = collector.collect(
        tmp_path, now_ms=NOW, fetcher=recording_fetch, max_requests=1,
        seed_utc=collector.ms_to_iso(t0),
    )
    assert calls == [t0 + collector.API_LIMIT * MIN]
    assert second["new_candles"] == collector.API_LIMIT
    assert second["candle_count"] == 2 * collector.API_LIMIT
    opens = persisted_opens(tmp_path)
    assert opens == [t0 + i * MIN for i in range(2 * collector.API_LIMIT)]
    assert len(opens) == len(set(opens))

    third = collector.collect(
        tmp_path, now_ms=NOW, fetcher=recording_fetch, max_requests=1,
        seed_utc=collector.ms_to_iso(t0),
    )
    assert third["new_candles"] == 500
    assert third["candle_count"] == 2_500
    assert third["status"] == "ok"
    assert third["coverage_percent"] == 100.0
    assert third["coverage_target_percent"] == 100.0


def test_second_run_is_idempotent_and_byte_stable(tmp_path):
    t0 = NOW - 30 * MIN
    fetch = full_generator_fetcher()
    collector.collect(
        tmp_path, now_ms=NOW, fetcher=fetch, max_requests=10,
        seed_utc=collector.ms_to_iso(t0),
    )
    files = sorted((tmp_path / "data" / "BTCUSDT_1m").glob("*.csv"))
    before = {path.name: path.read_bytes() for path in files}
    report = collector.collect(
        tmp_path, now_ms=NOW, fetcher=fetch, max_requests=10,
        seed_utc=collector.ms_to_iso(t0),
    )
    assert report["requests_used"] == 0
    assert report["new_candles"] == 0
    assert report["duplicates_removed"] == 0
    assert report["status"] == "ok"
    after = {path.name: path.read_bytes() for path in files}
    assert before == after


def test_dedup_key_across_disk_and_api_counts_single_candle(tmp_path):
    t0 = NOW - 4 * MIN
    write_partition(tmp_path, [t0, t0 + 3 * MIN])
    source = [raw_kline(t0 + MIN), raw_kline(t0 + MIN), raw_kline(t0 + 2 * MIN)]
    report = collector.collect(
        tmp_path, now_ms=NOW, fetcher=fake_fetcher(source),
        seed_utc=collector.ms_to_iso(t0),
    )
    assert report["new_candles"] == 2
    assert report["duplicates_removed"] == 1
    assert report["candle_count"] == 4
    opens = persisted_opens(tmp_path)
    assert opens == [t0, t0 + MIN, t0 + 2 * MIN, t0 + 3 * MIN]


def test_empty_page_within_range_is_counted_and_gap_stays_recorded(tmp_path):
    t0 = NOW - 5 * MIN
    write_partition(tmp_path, [t0, t0 + 2 * MIN, t0 + 3 * MIN, t0 + 4 * MIN])
    report = collector.collect(
        tmp_path, now_ms=NOW, fetcher=fake_fetcher([]),
        seed_utc=collector.ms_to_iso(t0),
    )
    assert report["requests_used"] == 1
    assert report["empty_pages"] == 1
    assert report["new_candles"] == 0
    assert report["gaps_found"] == 1
    assert report["gaps_remaining"] == 1
    assert report["status"] == "backfill_pending"
    markdown = (tmp_path / "reports" / "latest.md").read_text(encoding="utf-8")
    assert "Páginas vazias: 1" in markdown


def test_partial_run_persists_only_fetched_state(tmp_path):
    t0 = NOW - 5_000 * MIN
    report = collector.collect(
        tmp_path, now_ms=NOW, fetcher=full_generator_fetcher(), max_requests=1,
        seed_utc=collector.ms_to_iso(t0),
    )
    assert report["new_candles"] == collector.API_LIMIT
    assert report["candle_count"] == collector.API_LIMIT
    opens = persisted_opens(tmp_path)
    assert opens == [t0 + i * MIN for i in range(collector.API_LIMIT)]
    state = (tmp_path / "reports" / "latest.json").read_text(encoding="utf-8")
    for fragment in ('"requests_used": 1', '"queued_ranges_remaining": 1', '"max_requests": 1'):
        assert fragment in state
    archived = list((tmp_path / "reports").glob("quality-*.json"))
    assert len(archived) == 1
