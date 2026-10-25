"""Download publico e auditavel de candles Spot da Binance (sem credenciais).

Suporta janela explicita (--start/--end em UTC), detecta colisoes entre alvos
por alias de caminho (prefixo \\\\?\\, 8.3, caixa, separadores, ponto/espaco) e
sempre remove os temporarios do processo, inclusive em falha.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from convergencia.data import validate_ohlcv

BASE_URL = "https://data-api.binance.vision/api/v3/klines"
ONE_MINUTE_MS = 60_000
LIMIT = 1000
MAX_DAYS = 365
DEFAULT_DAYS = 90
COLUMNS = [
    "open_time", "open", "high", "low", "close", "volume",
    "close_time", "quote_volume", "trades", "taker_buy_base_volume",
    "taker_buy_quote_volume", "ignore",
]
NUMERIC_COLUMNS = [
    "open", "high", "low", "close", "volume", "quote_volume",
    "taker_buy_base_volume", "taker_buy_quote_volume",
]


def fetch_page(symbol: str, start_ms: int, end_ms: int, timeout: int = 20) -> list[list]:
    """Busca uma pagina de candles com retries limitados; endpoint so de leitura."""
    params = urlencode({
        "symbol": symbol,
        "interval": "1m",
        "startTime": start_ms,
        "endTime": end_ms,
        "limit": LIMIT,
    })
    request = Request(
        f"{BASE_URL}?{params}",
        headers={"User-Agent": "ConvergenciaPaiFilhoTrindade/0.1 historical-data-only"},
        method="GET",
    )
    last_error: Exception | None = None
    for attempt in range(5):
        try:
            with urlopen(request, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if not isinstance(payload, list):
                raise RuntimeError(f"Resposta inesperada da API: {str(payload)[:500]}")
            if payload and (not isinstance(payload[0], list) or len(payload[0]) < 12):
                raise RuntimeError("Formato de candle inesperado na resposta da API.")
            return payload
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, RuntimeError) as exc:
            last_error = exc
            if isinstance(exc, HTTPError) and exc.code not in (418, 429, 500, 502, 503, 504):
                raise RuntimeError(f"API retornou HTTP {exc.code}: {exc.reason}") from exc
            if attempt == 4:
                break
            wait = min(2 ** attempt, 16)
            print(f"Aviso: falha na requisicao ({exc}); nova tentativa em {wait}s.", file=sys.stderr)
            time.sleep(wait)
    raise RuntimeError(f"Nao foi possivel consultar a API depois de 5 tentativas: {last_error}")


def last_complete_minute_ms(now_ms: int | None = None) -> int:
    """Timestamp em ms do ultimo candle 1m ja fechado (exclui a vela em formacao)."""
    if now_ms is None:
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    if now_ms < ONE_MINUTE_MS:
        raise ValueError("relogio trivialmente pequeno")
    return (now_ms // ONE_MINUTE_MS) * ONE_MINUTE_MS - ONE_MINUTE_MS


def parse_utc_moment(value: str) -> datetime:
    """Converte 'YYYY-MM-DD' ou 'YYYY-MM-DDTHH:MM[:SS]' em instante UTC consciente."""
    text = value.strip()
    if text[-1:] in ("Z", "z"):
        text = text[:-1]
    try:
        moment = datetime.fromisoformat(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"momento invalido: {value!r} (use YYYY-MM-DD ou YYYY-MM-DDTHH:MM[:SS] em UTC)"
        ) from exc
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def explicit_window_ms(start: datetime, end: datetime, now_ms: int | None = None) -> tuple[int, int]:
    """Janela explicita alinhada ao minuto: start arredondado para baixo, end
    para o ultimo minuto completo <= end. Levanta erro se o fim incluir a vela
    em formacao ou se a janela exceder MAX_DAYS."""
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("--start/--end precisam de fuso horario (use UTC, ex.: 2026-10-23T00:00:00Z)")
    start_ms = (int(start.timestamp()) // 60) * 60 * 1000
    end_ms = (int(end.timestamp()) // 60) * 60 * 1000
    if end_ms < start_ms:
        raise ValueError("--end anterior a --start")
    last_complete = last_complete_minute_ms(now_ms)
    if end_ms > last_complete:
        raise ValueError("--end inclui o candle ainda em formacao; use um instante ja fechado no passado")
    rows = (end_ms - start_ms) // ONE_MINUTE_MS + 1
    if rows > MAX_DAYS * 1440:
        raise ValueError(f"janela excede {MAX_DAYS} dias ({rows:,} candles solicitados)")
    return start_ms, end_ms


def resolve_window(args: argparse.Namespace, now_ms: int | None = None) -> tuple[int, int, str]:
    """Retorna (start_ms, end_ms, modo) do pedido; modo em {days, explicit_window}."""
    has_start = args.start is not None
    has_end = args.end is not None
    if has_start != has_end:
        raise ValueError("--start e --end devem ser informados juntos")
    if has_start and args.days is not None:
        raise ValueError("--days e --start/--end sao mutuamente exclusivos")
    if not has_start and args.days is None:
        args.days = DEFAULT_DAYS
    if has_start:
        start_ms, end_ms = explicit_window_ms(args.start, args.end, now_ms=now_ms)
        return start_ms, end_ms, "explicit_window"
    last_complete = last_complete_minute_ms(now_ms)
    start_ms = last_complete - (args.days * 1440 - 1) * ONE_MINUTE_MS
    return start_ms, last_complete, "days"


def _path_key(path: Path) -> str:
    """Chave canonica de um caminho para deteccao de aliases.

    Normaliza o prefixo de comprimento estendido do Windows (\\\\?\\ e //?/),
    os dois separadores possiveis e, somente no Windows, caixa e os sufixos
    de ponto/espaco que o NTFS descarta silenciosamente ao criar arquivos.
    """
    text = str(path)
    if text.startswith("\\\\?\\UNC\\"):
        text = "\\\\" + text[len("\\\\?\\UNC\\"):]
    elif text.startswith("\\\\?\\"):
        text = text[len("\\\\?\\"):]
    elif text.startswith("//?/"):
        text = text[len("//?/"):]
    text = text.replace("\\", "/")
    if os.name == "nt":
        text = text.lower()
        text = "/".join(part.rstrip(" .") for part in text.split("/"))
    return text.rstrip("/")


def _resolved_key(path: Path) -> str:
    """Chave canonica apos resolucao (colapsa '..', separadores e 8.3 de caminhos existentes)."""
    try:
        resolved = path.resolve(strict=False)
    except (OSError, RuntimeError, ValueError):
        resolved = Path(os.path.abspath(path))
    return _path_key(resolved)


def check_path_collisions(targets: list[Path]) -> None:
    """Levanta erro se dois alvos sao o mesmo arquivo real (ou o mesmo alias).

    Compara chaves canonicas e, quando ambos existem, usa Path.samefile, que
    enxerga aliases que a comparacao textual nao resolve (8.3, junctions).
    """
    for i, first in enumerate(targets):
        for second in targets[i + 1:]:
            if _resolved_key(first) == _resolved_key(second):
                raise ValueError(f"colisao de caminhos: {first} e {second} apontam para o mesmo alvo")
            if first.exists() and second.exists():
                try:
                    same = first.samefile(second)
                except OSError:
                    same = False
                if same:
                    raise ValueError(
                        f"colisao de caminhos (samefile): {first} e {second} sao o mesmo arquivo"
                    )


def default_paths(root: Path, symbol: str) -> tuple[Path, Path]:
    """Caminhos padrao: CSV em data/raw/, relatorio de qualidade em reports/."""
    csv_path = root / "data" / "raw" / f"{symbol}_1m.csv"
    report_path = root / "reports" / f"data_quality_{symbol}_1m.json"
    return csv_path, report_path


def resolve_range_paths(root: Path, symbol: str, output: Path | None) -> tuple[Path, Path]:
    """Resolve o par (CSV, relatorio); --output relativo e ancorado na raiz do projeto."""
    default_csv, report_path = default_paths(root, symbol)
    csv_path = default_csv
    if output is not None:
        csv_path = output if output.is_absolute() else root / output
        csv_path = Path(os.path.abspath(csv_path))
    return csv_path, report_path


class CliPlan(NamedTuple):
    """Resultado imutavel da validacao do CLI antes de qualquer requisicao."""

    symbol: str
    mode: str
    start_ms: int
    end_ms: int
    csv_path: Path
    report_path: Path
    temp_csv: Path
    temp_report: Path


def validate_cli(args: argparse.Namespace, now_ms: int | None = None) -> CliPlan:
    """Valida simbolo, janela e alvos; nada de filesystem e criado aqui."""
    symbol = args.symbol.strip().upper()
    if not symbol.isalnum():
        raise ValueError("symbol deve conter apenas letras e numeros, por exemplo BTCUSDT")
    if args.days is not None and not 1 <= args.days <= MAX_DAYS:
        raise ValueError(f"days deve estar entre 1 e {MAX_DAYS} para esta etapa")
    start_ms, end_ms, mode = resolve_window(args, now_ms=now_ms)
    csv_path, report_path = resolve_range_paths(ROOT, symbol, args.output)
    suffix = f".tmp-{os.getpid()}"
    temp_csv = csv_path.with_name(csv_path.name + suffix)
    temp_report = report_path.with_name(report_path.name + suffix)
    check_path_collisions([csv_path, report_path, temp_csv, temp_report])
    if not args.overwrite and (csv_path.exists() or report_path.exists()):
        raise ValueError(
            "arquivo de saida ja existe; revise-o ou use --overwrite. "
            f"CSV: {csv_path} | relatorio: {report_path}"
        )
    return CliPlan(symbol, mode, start_ms, end_ms, csv_path, report_path, temp_csv, temp_report)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Baixa candles publicos da Binance Spot para backtest; nao envia ordens."
    )
    parser.add_argument("--symbol", default="BTCUSDT", help="Par Spot, padrao BTCUSDT")
    parser.add_argument(
        "--days", type=int, default=None,
        help=f"Dias completos terminando no ultimo minuto fechado (padrao {DEFAULT_DAYS}; exclusivo de --start/--end)",
    )
    parser.add_argument(
        "--start", type=parse_utc_moment, default=None, metavar="UTC",
        help="Inicio da janela: YYYY-MM-DD ou YYYY-MM-DDTHH:MM[:SS] (UTC)",
    )
    parser.add_argument(
        "--end", type=parse_utc_moment, default=None, metavar="UTC",
        help="Fim da janela: ultimo candle completo <= instante (exige --start)",
    )
    parser.add_argument(
        "--output", type=Path, default=None,
        help="CSV de saida (padrao data/raw/<SYMBOL>_1m.csv; relatorio sempre em reports/)",
    )
    parser.add_argument(
        "--overwrite", action="store_true",
        help="Permite substituir explicitamente o CSV e o relatorio existentes",
    )
    return parser


def fetch_window(symbol: str, start_ms: int, end_ms: int, timeout: int = 20) -> pd.DataFrame:
    """Baixa a janela [start_ms, end_ms] de candles 1m completos e a valida."""
    rows: list[list] = []
    cursor = start_ms
    request_count = 0
    while cursor <= end_ms:
        page = fetch_page(symbol, cursor, end_ms, timeout=timeout)
        request_count += 1
        if not page:
            break
        rows.extend(page)
        last_open = int(page[-1][0])
        next_cursor = last_open + ONE_MINUTE_MS
        if next_cursor <= cursor:
            raise RuntimeError("A paginacao nao avancou; interrompendo para evitar loop infinito.")
        cursor = next_cursor
        print(f"Pagina {request_count}: {len(rows):,} candles recebidos.")
        if len(page) < LIMIT:
            break
        time.sleep(0.15)

    if not rows:
        raise RuntimeError("A API nao retornou candles para o intervalo solicitado.")

    raw = pd.DataFrame(rows, columns=COLUMNS)
    raw["timestamp"] = pd.to_datetime(pd.to_numeric(raw["open_time"], errors="raise"), unit="ms", utc=True)
    raw["close_time"] = pd.to_datetime(pd.to_numeric(raw["close_time"], errors="raise"), unit="ms", utc=True)
    for col in NUMERIC_COLUMNS:
        raw[col] = pd.to_numeric(raw[col], errors="coerce")
    raw["trades"] = pd.to_numeric(raw["trades"], errors="coerce").astype("Int64")

    keep = ["timestamp", "open", "high", "low", "close", "volume", "close_time",
            "quote_volume", "trades", "taker_buy_base_volume", "taker_buy_quote_volume"]
    frame = validate_ohlcv(raw[keep].copy())

    start_dt = pd.to_datetime(start_ms, unit="ms", utc=True)
    end_dt = pd.to_datetime(end_ms, unit="ms", utc=True)
    if frame["timestamp"].iloc[0] < start_dt:
        raise RuntimeError("A API devolveu candle anterior ao inicio solicitado.")
    if frame["timestamp"].iloc[-1] > end_dt:
        raise RuntimeError("A API devolveu candle posterior ao fim solicitado.")
    return frame


def compute_gaps(frame: pd.DataFrame) -> tuple[int, int, list[dict]]:
    """Conta passos irregulares e minutos ausentes entre timestamps consecutivos."""
    delta = frame["timestamp"].diff().dropna()
    irregular = delta[delta != pd.Timedelta(minutes=1)]
    gaps: list[dict] = []
    missing_minutes = 0
    for idx, difference in irregular.items():
        previous = frame.loc[idx - 1, "timestamp"]
        current = frame.loc[idx, "timestamp"]
        missing = max(int(difference / pd.Timedelta(minutes=1)) - 1, 0)
        missing_minutes += missing
        if len(gaps) < 20:
            gaps.append({
                "previous": previous.isoformat(),
                "current": current.isoformat(),
                "missing_minutes_estimate": missing,
            })
    return len(irregular), missing_minutes, gaps


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def write_outputs(frame: pd.DataFrame, plan: CliPlan) -> tuple[str, str, dict]:
    """Grava CSV e relatorio via temporarios unicos do processo e os limpa sempre.

    LIMITACAO: os dois renomeios nao sao atomicos em conjunto. Se o processo
    morrer entre eles, o CSV pode ficar novo com o relatorio antigo; a
    inconsistencia e detectavel porque o relatorio guarda o csv_sha256
    calculado antes dos renomeios. Temporarios levam o PID no nome, nao
    colidem com artefatos de outras execucoes e sao removidos em finally.
    """
    if frame.empty:
        raise ValueError("Nada para gravar: frame vazio.")
    expected_rows = (plan.end_ms - plan.start_ms) // ONE_MINUTE_MS + 1
    plan.csv_path.parent.mkdir(parents=True, exist_ok=True)
    plan.report_path.parent.mkdir(parents=True, exist_ok=True)
    file_hash = ""
    status = "ERROR"
    report: dict = {}
    try:
        frame.to_csv(plan.temp_csv, index=False, date_format="%Y-%m-%dT%H:%M:%S.%f%z")
        file_hash = sha256_file(plan.temp_csv)
        irregular_count, missing_minutes, gaps = compute_gaps(frame)
        status = "PASS" if len(frame) == expected_rows and irregular_count == 0 else "WARN_REVIEW_DATA_GAPS_OR_RANGE"
        report = {
            "source": BASE_URL,
            "symbol": plan.symbol,
            "interval": "1m",
            "mode": plan.mode,
            "requested_days": expected_rows // 1440 if plan.mode == "days" else None,
            "requested_start_utc": pd.to_datetime(plan.start_ms, unit="ms", utc=True).isoformat(),
            "requested_end_utc": pd.to_datetime(plan.end_ms, unit="ms", utc=True).isoformat(),
            "expected_rows": expected_rows,
            "rows": int(len(frame)),
            "first_timestamp_utc": frame["timestamp"].iloc[0].isoformat(),
            "last_timestamp_utc": frame["timestamp"].iloc[-1].isoformat(),
            "duplicate_timestamps": int(frame["timestamp"].duplicated().sum()),
            "irregular_minute_steps": int(irregular_count),
            "estimated_missing_minutes": int(missing_minutes),
            "first_irregular_steps": gaps,
            "csv_sha256": file_hash,
            "quality_status": status,
            "notes": [
                "OHLCV validado pelo projeto antes de gravar.",
                "O endpoint e de dados publicos; nao foi usada autenticacao.",
                "Um relatorio PASS nao demonstra rentabilidade nem valida uma estrategia.",
                "Dados com lacunas devem ser investigados antes do backtest.",
                "CSV e relatorio sao gravados em temporarios do processo e renomeados em "
                "sequencia; uma falha entre os renomeios deixa o par inconsistente, "
                "detectavel pelo csv_sha256.",
            ],
        }
        plan.temp_report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        plan.temp_csv.replace(plan.csv_path)
        plan.temp_report.replace(plan.report_path)
    finally:
        for temp in (plan.temp_csv, plan.temp_report):
            try:
                if temp.exists():
                    temp.unlink()
            except OSError as exc:
                print(f"Aviso: temporario nao removido ({temp}): {exc}", file=sys.stderr)
    return file_hash, status, report


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        plan = validate_cli(args)
    except ValueError as exc:
        parser.error(str(exc))

    start_iso = pd.to_datetime(plan.start_ms, unit="ms", utc=True).isoformat()
    end_iso = pd.to_datetime(plan.end_ms, unit="ms", utc=True).isoformat()
    print(f"Fonte: {BASE_URL}")
    print("Acesso: somente dados publicos; nenhuma chave API ou conta e usada.")
    print(f"Par: {plan.symbol} | Intervalo: 1m | Janela {plan.mode}: {start_iso} -> {end_iso}")
    frame = fetch_window(plan.symbol, plan.start_ms, plan.end_ms)
    file_hash, status, report = write_outputs(frame, plan)

    print("\n--- RESUMO DO HISTORICO ---")
    print(f"Arquivo: {plan.csv_path}")
    print(f"Relatorio: {plan.report_path}")
    print(f"Candles: {report['rows']:,} | Esperados: {report['expected_rows']:,}")
    print(f"Primeiro candle UTC: {report['first_timestamp_utc']}")
    print(f"Ultimo candle UTC:   {report['last_timestamp_utc']}")
    print(
        f"Passos de tempo irregulares: {report['irregular_minute_steps']} | "
        f"Minutos ausentes estimados: {report['estimated_missing_minutes']}"
    )
    print(f"SHA256 CSV: {file_hash}")
    print(f"Qualidade: {status}")
    for gap in report["first_irregular_steps"]:
        print(
            f"  {gap['previous']} -> {gap['current']} | "
            f"minutos ausentes estimados: {gap['missing_minutes_estimate']}"
        )
    print("\nIMPORTANTE: nenhum sinal foi gerado e nenhuma ordem real foi enviada.")
    return 0 if status == "PASS" else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Download interrompido pelo usuario.", file=sys.stderr)
        raise SystemExit(130)
    except Exception as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        raise SystemExit(1)
