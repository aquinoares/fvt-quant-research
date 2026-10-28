#!/usr/bin/env python3
"""Coletor de dados públicos da Trilha A. EXPLORATÓRIO — NÃO É PROVA."""
from __future__ import annotations

import argparse
import bisect
import csv
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Iterable

API_URL = "https://data-api.binance.vision/api/v3/klines"
SYMBOL, INTERVAL = "BTCUSDT", "1m"
MINUTE_MS, HOUR4_MS = 60_000, 240 * 60_000
API_LIMIT, DEFAULT_MAX_REQUESTS = 1000, 10
DEFAULT_SEED_UTC = "2020-01-01T00:00:00Z"
COLUMNS = [
    "symbol", "interval", "open_time_ms", "open_time_utc", "open", "high", "low",
    "close", "volume", "close_time_ms", "close_time_utc", "quote_volume",
    "trade_count", "taker_buy_base_volume", "taker_buy_quote_volume",
]


class APIError(RuntimeError):
    def __init__(self, status: int | None, detail: str):
        super().__init__(detail)
        self.status, self.detail = status, detail


def ms_to_iso(value: int) -> str:
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc).isoformat(
        timespec="seconds"
    ).replace("+00:00", "Z")


def parse_utc_ms(value: str) -> int:
    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("LEARNING_START_UTC precisa conter fuso horário UTC.")
    return int(parsed.astimezone(timezone.utc).timestamp() * 1000)


def _decimal_text(value: Decimal) -> str:
    return format(value.normalize(), "f") if value else "0"


def normalize_kline(row: Any, now_ms: int) -> dict[str, str] | None:
    """Normaliza apenas candle de 1m fechado; descarta o candle em formação."""
    if not isinstance(row, (list, tuple)) or len(row) < 11:
        return None
    try:
        open_ms, close_ms = int(row[0]), int(row[6])
        last_closed_open = (now_ms // MINUTE_MS) * MINUTE_MS - MINUTE_MS
        if open_ms > last_closed_open or close_ms >= now_ms:
            return None
        if close_ms < open_ms or close_ms > open_ms + MINUTE_MS - 1:
            return None
        trades = int(row[8])
        numbers = [str(Decimal(str(row[i]))) for i in (1, 2, 3, 4, 5, 7, 9, 10)]
    except (ValueError, TypeError, ArithmeticError):
        return None
    return {
        "symbol": SYMBOL, "interval": INTERVAL,
        "open_time_ms": str(open_ms), "open_time_utc": ms_to_iso(open_ms),
        "open": numbers[0], "high": numbers[1], "low": numbers[2], "close": numbers[3],
        "volume": numbers[4], "close_time_ms": str(close_ms),
        "close_time_utc": ms_to_iso(close_ms), "quote_volume": numbers[5],
        "trade_count": str(trades), "taker_buy_base_volume": numbers[6],
        "taker_buy_quote_volume": numbers[7],
    }


def fetch_klines(start_ms: int, end_ms: int, limit: int = API_LIMIT) -> list[Any]:
    """Usa somente API pública e anônima; timeout de 12 s, uma repetição de rede."""
    if start_ms > end_ms:
        return []
    params = urllib.parse.urlencode({
        "symbol": SYMBOL, "interval": INTERVAL, "startTime": int(start_ms),
        "endTime": int(end_ms), "limit": min(API_LIMIT, max(1, int(limit))),
    })
    request = urllib.request.Request(
        API_URL + "?" + params,
        headers={"User-Agent": "fvt-quant-learning/1.0", "Accept": "application/json"},
    )
    for attempt in range(2):
        try:
            with urllib.request.urlopen(request, timeout=12) as response:
                payload = response.read()
            result = json.loads(payload.decode("utf-8"))
            if not isinstance(result, list):
                raise APIError(None, "A API pública retornou um formato diferente de lista.")
            return result
        except urllib.error.HTTPError as exc:
            raise APIError(exc.code, f"HTTP {exc.code} no endpoint público Binance.") from None
        except urllib.error.URLError as exc:
            if attempt == 0:
                time.sleep(1)
                continue
            raise APIError(None, f"Falha de rede no endpoint público: {type(exc.reason).__name__}.") from None
        except (TimeoutError, json.JSONDecodeError) as exc:
            if attempt == 0 and isinstance(exc, TimeoutError):
                time.sleep(1)
                continue
            raise APIError(None, f"Resposta/timeout inválido ({type(exc).__name__}).") from None
    raise APIError(None, "Falha de rede não classificada.")


def write_csv(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=COLUMNS, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows({col: row.get(col, "") for col in COLUMNS} for row in rows)
    temp.replace(path)


def month_path(data_dir: Path, interval: str, open_ms: int) -> Path:
    dt = datetime.fromtimestamp(open_ms / 1000, tz=timezone.utc)
    return data_dir / f"{SYMBOL}_{interval}" / f"{dt.year:04d}-{dt.month:02d}.csv"


def scan_existing(folder: Path, interval: str) -> tuple[list[int], int, int]:
    """Lê uma partição mensal de cada vez e remove duplicatas/malformados."""
    folder.mkdir(parents=True, exist_ok=True)
    seen: set[tuple[str, str, int]] = set()
    timestamps: list[int] = []
    duplicates = invalid = 0
    for path in sorted(folder.glob("*.csv")):
        kept, dirty, prior_ts = [], False, None
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            for row in csv.DictReader(stream):
                try:
                    ts = int(row["open_time_ms"])
                    symbol, row_interval = row.get("symbol") or SYMBOL, row.get("interval") or interval
                    if symbol != SYMBOL or row_interval != interval:
                        raise ValueError("símbolo/intervalo inesperado")
                except (KeyError, ValueError, TypeError):
                    invalid += 1
                    dirty = True
                    continue
                key = (symbol, row_interval, ts)
                if key in seen:
                    duplicates += 1
                    dirty = True
                    continue
                seen.add(key)
                timestamps.append(ts)
                kept.append(row)
                if prior_ts is not None and ts < prior_ts:
                    dirty = True
                prior_ts = ts
        if dirty:
            kept.sort(key=lambda item: int(item["open_time_ms"]))
            write_csv(path, kept)
    timestamps.sort()
    return timestamps, duplicates, invalid


def find_gaps(timestamps: list[int]) -> list[tuple[int, int]]:
    return [
        (left + MINUTE_MS, right - MINUTE_MS)
        for left, right in zip(timestamps, timestamps[1:])
        if right - left > MINUTE_MS
    ]


def missing_minutes(timestamps: list[int], start_ms: int, end_ms: int) -> int:
    if start_ms > end_ms:
        return 0
    expected = (end_ms - start_ms) // MINUTE_MS + 1
    present = bisect.bisect_right(timestamps, end_ms) - bisect.bisect_left(timestamps, start_ms)
    return max(0, expected - present)


def save_new_records(data_dir: Path, records: list[dict[str, str]], interval: str) -> None:
    grouped: dict[Path, list[dict[str, str]]] = defaultdict(list)
    for row in records:
        grouped[month_path(data_dir, interval, int(row["open_time_ms"]))].append(row)
    for path, additions in grouped.items():
        merged: dict[int, dict[str, str]] = {}
        if path.is_file():
            with path.open("r", encoding="utf-8-sig", newline="") as stream:
                for row in csv.DictReader(stream):
                    try:
                        merged[int(row["open_time_ms"])] = row
                    except (KeyError, ValueError):
                        continue
        for row in additions:
            merged[int(row["open_time_ms"])] = row
        write_csv(path, (merged[key] for key in sorted(merged)))


def iter_one_minute_rows(data_dir: Path):
    for path in sorted((data_dir / f"{SYMBOL}_{INTERVAL}").glob("*.csv")):
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            for row in csv.DictReader(stream):
                try:
                    if row.get("symbol") == SYMBOL and row.get("interval") == INTERVAL:
                        int(row["open_time_ms"])
                        yield row
                except (KeyError, ValueError):
                    continue


def aggregate_4h(data_dir: Path, now_ms: int) -> int:
    """Agrega candles 4h em baldes UTC 00/04/08/12/16/20 somente se houver 240 candles."""
    grouped: dict[Path, list[dict[str, str]]] = defaultdict(list)
    bucket_start: int | None = None
    bucket: list[dict[str, str]] = []
    count = 0

    def flush():
        nonlocal count
        if len(bucket) != 240 or bucket_start is None or now_ms < bucket_start + HOUR4_MS:
            return
        expected = [bucket_start + i * MINUTE_MS for i in range(240)]
        if [int(r["open_time_ms"]) for r in bucket] != expected:
            return
        try:
            close_ms = bucket_start + HOUR4_MS - 1
            record = {
                "symbol": SYMBOL, "interval": "4h",
                "open_time_ms": str(bucket_start), "open_time_utc": ms_to_iso(bucket_start),
                "open": bucket[0]["open"],
                "high": _decimal_text(max(Decimal(r["high"]) for r in bucket)),
                "low": _decimal_text(min(Decimal(r["low"]) for r in bucket)),
                "close": bucket[-1]["close"],
                "volume": _decimal_text(sum((Decimal(r["volume"]) for r in bucket), Decimal(0))),
                "close_time_ms": str(close_ms), "close_time_utc": ms_to_iso(close_ms),
                "quote_volume": _decimal_text(sum((Decimal(r["quote_volume"]) for r in bucket), Decimal(0))),
                "trade_count": str(sum(int(r["trade_count"]) for r in bucket)),
                "taker_buy_base_volume": _decimal_text(sum((Decimal(r["taker_buy_base_volume"]) for r in bucket), Decimal(0))),
                "taker_buy_quote_volume": _decimal_text(sum((Decimal(r["taker_buy_quote_volume"]) for r in bucket), Decimal(0))),
            }
        except (ArithmeticError, KeyError, ValueError):
            return
        grouped[month_path(data_dir, "4h", bucket_start)].append(record)
        count += 1

    for row in iter_one_minute_rows(data_dir):
        try:
            open_ms, close_ms = int(row["open_time_ms"]), int(row["close_time_ms"])
            if close_ms >= now_ms:
                continue
        except (KeyError, ValueError):
            continue
        start = (open_ms // HOUR4_MS) * HOUR4_MS
        if bucket_start != start:
            flush()
            bucket_start, bucket = start, []
        bucket.append(row)
    flush()
    out_folder = data_dir / f"{SYMBOL}_4h"
    for path in sorted(out_folder.glob("*.csv")) if out_folder.exists() else []:
        if path not in grouped:
            path.unlink()
    for path, rows in grouped.items():
        write_csv(path, rows)
    return count



def summarize_coverage(timestamps: list[int], target_ms: int | None = None) -> dict[str, Any]:
    """In-range coverage (first..last on disk) plus total coverage up to target_ms.

    coverage_percent mede apenas o intervalo já existente em disco. coverage_target_*
    mede a cobertura total até o instante-alvo, para não mascarar cauda não coletada.
    """
    unique = sorted(set(ts for ts in timestamps if isinstance(ts, int)))
    if not unique:
        return {
            "first_candle_open_time_utc": None,
            "coverage_percent": None,
            "coverage_minutes_present": None,
            "coverage_minutes_expected": None,
            "coverage_target_percent": None,
            "coverage_target_minutes_present": None,
            "coverage_target_minutes_expected": None,
            "coverage_target_utc": None,
            "daily_gaps": [],
        }
    first, last = unique[0], unique[-1]
    expected = max(1, (last - first) // MINUTE_MS + 1)
    present = len(unique)
    target_percent = target_present = target_expected = None
    target_utc = None
    if target_ms is not None and target_ms >= first:
        target_expected = (target_ms - first) // MINUTE_MS + 1
        target_present = bisect.bisect_right(unique, target_ms)
        target_percent = round(target_present / max(1, target_expected) * 100, 6)
        target_utc = ms_to_iso(target_ms)
    gaps_by_day: dict[str, int] = defaultdict(int)
    for gap_start, gap_end in find_gaps(unique):
        cursor = gap_start
        while cursor <= gap_end:
            day_start = (cursor // 86_400_000) * 86_400_000
            day_end = day_start + 86_400_000 - MINUTE_MS
            end_here = min(gap_end, day_end)
            missing = (end_here - cursor) // MINUTE_MS + 1
            day = datetime.fromtimestamp(cursor / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
            gaps_by_day[day] += missing
            cursor = end_here + MINUTE_MS
    return {
        "first_candle_open_time_utc": ms_to_iso(first),
        "coverage_percent": round(present / expected * 100, 6),
        "coverage_minutes_present": present,
        "coverage_minutes_expected": expected,
        "coverage_target_percent": target_percent,
        "coverage_target_minutes_present": target_present,
        "coverage_target_minutes_expected": target_expected,
        "coverage_target_utc": target_utc,
        "daily_gaps": [
            {"date_utc": day, "missing_minutes": count}
            for day, count in sorted(gaps_by_day.items())
        ][-90:],
    }

def report_markdown(report: dict[str, Any]) -> str:
    return "\n".join([
        "# Relatório de qualidade — Trilha A", "",
        "**EXPLORATÓRIO — NÃO É PROVA.**", "",
        f"- Execução UTC: {report.get('run_at_utc')}",
        f"- Estado: {report.get('status')}",
        f"- Fonte pública: Binance Spot; símbolo {report.get('symbol')}; intervalo {report.get('interval')}.",
        f"- Requisições: {report.get('requests_used')}/{report.get('max_requests')}.",
        f"- Candles novos nesta execução: {report.get('new_candles')}.",
        f"- Candles únicos persistidos: {report.get('candle_count')}.",
        f"- Primeira data UTC: {report.get('first_candle_open_time_utc') or '—'}.",
        f"- Cobertura dentro do intervalo observado (primeiro→último candle em disco): {report.get('coverage_percent') if report.get('coverage_percent') is not None else '—'}% ({report.get('coverage_minutes_present')} / {report.get('coverage_minutes_expected')} minutos).",
        f"- Cobertura total até o instante-alvo ({report.get('coverage_target_utc') or '—'}): {report.get('coverage_target_percent') if report.get('coverage_target_percent') is not None else '—'}% ({report.get('coverage_target_minutes_present')} / {report.get('coverage_target_minutes_expected')} minutos).",
        f"- Dias com lacunas UTC registrados: {len(report.get('daily_gaps', []))}.",
        f"- Lacunas encontradas antes: {report.get('gaps_found')} intervalos / {report.get('missing_minutes_before')} minutos ausentes.",
        f"- Lacunas totalmente preenchidas: {report.get('gaps_filled')}; candles recuperados dentro delas: {report.get('gap_candles_filled')}.",
        f"- Lacunas remanescentes: {report.get('gaps_remaining')} intervalos / {report.get('missing_minutes_after')} minutos ausentes.",
        f"- Duplicatas removidas/ignoradas: {report.get('duplicates_removed')}.",
        f"- Último candle fechado UTC: {report.get('last_candle_open_time_utc') or 'não disponível'}.",
        f"- Idade do último candle (s desde abertura): {report.get('age_last_candle_seconds') if report.get('age_last_candle_seconds') is not None else 'não disponível'}.",
        f"- Backfill estimado pendente: {report.get('pending_backfill_candles')} candles.",
        f"- Faixas ainda na fila de backfill: {report.get('queued_ranges_remaining')}.",
        f"- Páginas vazias: {report.get('empty_pages')}; registros recebidos da API: {report.get('api_rows_received')}.",
        f"- HTTP: {report.get('api_http_status') if report.get('api_http_status') is not None else 'sem erro HTTP registrado'}.",
        "", "## Observações", "", report.get("message", "Sem mensagem."),
        "",
        "Candles de 4h são agregados localmente nos baldes UTC 00:00, 04:00, 08:00, 12:00, 16:00 e 20:00, somente com 240 candles de 1m contíguos e fechados.",
        "Esta coleta não usa endpoints privados, chaves, ordens nem artefatos/estado da Trilha B.", "",
    ])


def write_reports(root: Path, report: dict[str, Any]) -> None:
    out = root / "reports"
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.fromtimestamp(report["run_at_epoch_ms"] / 1000, tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = re.sub(r"[^A-Za-z0-9_.-]", "_", str(report.get("run_id") or "local"))[:80]
    serialized = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    markdown = report_markdown(report)
    (out / "latest.json").write_text(serialized, encoding="utf-8")
    (out / "latest.md").write_text(markdown, encoding="utf-8")
    (out / f"quality-{stamp}-{run_id}.json").write_text(serialized, encoding="utf-8")
    (out / f"quality-{stamp}-{run_id}.md").write_text(markdown, encoding="utf-8")


def collect(root: Path, now_ms: int | None = None,
            fetcher: Callable[[int, int, int], list[Any]] | None = None,
            max_requests: int = DEFAULT_MAX_REQUESTS, run_id: str = "local",
            seed_utc: str | None = None) -> dict[str, Any]:
    root = Path(root)
    data_dir = root / "data"
    now_ms = int(now_ms if now_ms is not None else time.time() * 1000)
    fetcher = fetcher or fetch_klines
    max_requests = max(1, min(100, int(max_requests)))
    last_closed = (now_ms // MINUTE_MS) * MINUTE_MS - MINUTE_MS
    timestamps, persisted_duplicates, invalid_rows = scan_existing(
        data_dir / f"{SYMBOL}_{INTERVAL}", INTERVAL
    )
    before_gaps = find_gaps(timestamps)
    before_missing = sum((end - start) // MINUTE_MS + 1 for start, end in before_gaps)
    seen = set(timestamps)
    if seed_utc is None:
        seed_utc = os.environ.get("LEARNING_START_UTC", DEFAULT_SEED_UTC)
    seed_ms = parse_utc_ms(seed_utc)
    tail_start = timestamps[-1] + MINUTE_MS if timestamps else seed_ms
    # Fila prioriza a cauda (dados mais recentes primeiro); lacunas históricas vêm depois.
    queue: list[tuple[int, int, str]] = []
    if tail_start <= last_closed:
        queue.append((tail_start, last_closed, "tail"))
    queue.extend((a, b, "gap") for a, b in before_gaps)
    original_gaps = list(before_gaps)
    new_records: list[dict[str, str]] = []
    duplicate_api_rows = requests_used = empty_pages = api_rows_received = 0
    error: APIError | None = None
    while queue and requests_used < max_requests:
        start, end, _kind = queue.pop(0)
        if start > end:
            continue
        page_end = min(end, start + (API_LIMIT - 1) * MINUTE_MS)
        requests_used += 1
        try:
            raw_rows = fetcher(start, page_end, API_LIMIT)
        except APIError as exc:
            error = exc
            break
        except Exception as exc:
            error = APIError(None, f"Falha de coleta ({type(exc).__name__}).")
            break
        api_rows_received += len(raw_rows)
        if not raw_rows:
            empty_pages += 1
            continue
        accepted: list[int] = []
        for raw in raw_rows:
            try:
                open_ms = int(raw[0])
            except (IndexError, TypeError, ValueError):
                continue
            if open_ms < start or open_ms > page_end:
                continue
            record = normalize_kline(raw, now_ms)
            if record is None:
                continue
            accepted.append(open_ms)
            if open_ms in seen:
                duplicate_api_rows += 1
                continue
            seen.add(open_ms)
            new_records.append(record)
        if accepted:
            next_start = max(accepted) + MINUTE_MS
            if next_start <= end:
                queue.insert(0, (next_start, end, _kind))

    save_new_records(data_dir, new_records, INTERVAL)
    timestamps = sorted(seen)
    coverage = summarize_coverage(timestamps, target_ms=last_closed)
    four_hour_count = aggregate_4h(data_dir, now_ms)
    after_gaps = find_gaps(timestamps)
    missing_after = sum((end - start) // MINUTE_MS + 1 for start, end in after_gaps)
    gaps_filled = gap_candles_filled = 0
    for start, end in original_gaps:
        remaining = missing_minutes(timestamps, start, end)
        gap_candles_filled += max(0, (end - start) // MINUTE_MS + 1 - remaining)
        if remaining == 0:
            gaps_filled += 1
    latest = timestamps[-1] if timestamps else None
    pending = max(0, (last_closed - latest) // MINUTE_MS) if latest is not None else max(0, (last_closed - seed_ms) // MINUTE_MS + 1)
    if error is not None and error.status in (403, 451):
        status = "blocked"
        message = f"HTTP {error.status} no endpoint público Binance; o runner pode estar sujeito a bloqueio geográfico/regional. O coletor não tentou autenticação nem contorno."
    elif error is not None:
        status, message = "api_error", f"Falha na API pública: {error.detail}"
    elif not timestamps and requests_used > 0:
        status, message = "empty_api", "A API não devolveu candles para o intervalo solicitado; nenhum dado foi inventado."
    elif after_gaps or pending > 0 or queue:
        status, message = "backfill_pending", "Backfill continua em próximas execuções; lacunas e atraso são registrados sem impedir nova coleta."
    elif empty_pages:
        status, message = "warning", "A API devolveu uma ou mais páginas vazias; confira lacunas e idade do último candle."
    else:
        status, message = "ok", "Coleta concluída dentro do orçamento de requisições; dados exploratórios, sem inferência de desempenho."
    age = max(0, (now_ms - latest) // 1000) if latest is not None else None
    report = {
        "label": "EXPLORATÓRIO — NÃO É PROVA", "schema_version": 1,
        "run_id": str(run_id), "run_at_utc": ms_to_iso(now_ms), "run_at_epoch_ms": now_ms,
        "status": status, "message": message, "symbol": SYMBOL, "interval": INTERVAL,
        "endpoint": API_URL, "uses_public_endpoint_only": True,
        "new_candles": len(new_records), "candle_count": len(timestamps),
        "first_candle_open_time_utc": coverage["first_candle_open_time_utc"],
        "coverage_percent": coverage["coverage_percent"],
        "coverage_minutes_present": coverage["coverage_minutes_present"],
        "coverage_minutes_expected": coverage["coverage_minutes_expected"],
        "coverage_target_percent": coverage["coverage_target_percent"],
        "coverage_target_minutes_present": coverage["coverage_target_minutes_present"],
        "coverage_target_minutes_expected": coverage["coverage_target_minutes_expected"],
        "coverage_target_utc": coverage["coverage_target_utc"],
        "daily_gaps": coverage["daily_gaps"],
        "gaps_found": len(before_gaps), "missing_minutes_before": before_missing,
        "gaps_filled": gaps_filled, "gap_candles_filled": gap_candles_filled,
        "gaps_remaining": len(after_gaps), "missing_minutes_after": missing_after,
        "duplicates_removed": persisted_duplicates + duplicate_api_rows,
        "invalid_rows_removed": invalid_rows,
        "last_candle_open_time_utc": ms_to_iso(latest) if latest is not None else None,
        "age_last_candle_seconds": age, "pending_backfill_candles": pending,
        "requests_used": requests_used, "max_requests": max_requests,
        "empty_pages": empty_pages, "api_rows_received": api_rows_received,
        "api_http_status": error.status if error is not None else None,
        "queued_ranges_remaining": len(queue), "four_hour_candles_aggregated": four_hour_count,
    }
    write_reports(root, report)
    return report


def append_summary(report: dict[str, Any], path: str | None) -> None:
    if not path:
        return
    lines = [
        "## Trilha A — qualidade de coleta", "",
        "**EXPLORATÓRIO — NÃO É PROVA.**", "",
        f"- Estado: **{report['status']}**",
        f"- Candles novos: {report['new_candles']} · únicos persistidos: {report['candle_count']}",
        f"- Lacunas encontradas/preenchidas/restantes: {report['gaps_found']} / {report['gaps_filled']} / {report['gaps_remaining']}",
        f"- Duplicatas removidas/ignoradas: {report['duplicates_removed']}",
        f"- Último candle UTC: {report['last_candle_open_time_utc'] or 'não disponível'}",
        f"- Idade (s): {report['age_last_candle_seconds'] if report['age_last_candle_seconds'] is not None else 'não disponível'}",
        f"- Backfill estimado pendente: {report['pending_backfill_candles']} candles",
        f"- Requisições: {report['requests_used']}/{report['max_requests']}",
        "- Relatório humano: learning/reports/latest.md (também arquivado por execução)", "",
        report["message"], "",
    ]
    with open(path, "a", encoding="utf-8") as stream:
        stream.write("\n".join(lines))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("learning"))
    parser.add_argument("--max-requests", type=int, default=DEFAULT_MAX_REQUESTS)
    parser.add_argument("--run-id", default=os.environ.get("GITHUB_RUN_ID", "local"))
    args = parser.parse_args(argv)
    report = collect(args.root, max_requests=args.max_requests, run_id=args.run_id)
    append_summary(report, os.environ.get("GITHUB_STEP_SUMMARY"))
    print(f"{report['label']}: status={report['status']}; new={report['new_candles']}; gaps={report['gaps_remaining']}; duplicates={report['duplicates_removed']}")
    return 2 if report["status"] in ("blocked", "api_error") else 0
