#!/usr/bin/env python3
"""Passo operacional manual da janela P6-MOM (MOM_TF240_LB96, 90 dias).

Coleta candles 1m NOVOS (publicos, sem credenciais) com scripts/download_klines.py
e os alimenta a scripts/run_shadow_prospectivo.py --protocol P6-MOM.

Nao ha agendador automatico configurado neste repositorio: este passo precisa ser
executado manualmente (ou por um agendador do sistema configurado pelo usuario)
a cada periodo desejado. Nao envia ordens, nao acessa endpoints de negociacao e
nao preenche lacunas com dados historicos: o download comeca exatamente no minuto
apois o ultimo timestamp do state.json (ou no inicio da janela, na primeira
execucao) e avanca somente ate o ultimo minuto completo.

Codigos de saida: 0 ok; 2 recusa/validacao; 3 limite de risco atingido (novas
entradas bloqueadas; nao continuar alimentando a sessao); 4 falha fatal/coleta;
5 nada a coletar ainda (antes do inicio, sem dados novos ou janela encerrada).
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import download_klines  # noqa: E402

SYMBOL = "BTCUSDT"
PROTOCOL = "P6-MOM"
WINDOW_ID = "P6MOM-20261025T000000Z"
WINDOW_START = datetime(2026, 10, 25, 0, 0, 0, tzinfo=timezone.utc)
WINDOW_END = WINDOW_START + timedelta(days=90)
SESSION_DIR = ROOT / "data" / "shadow" / "p6_mom_mom_tf240_lb96_20261025T000000Z"
SEGMENTS_DIR = SESSION_DIR / "segments"
REPORTS_DIR = SESSION_DIR / "reports"
STATE_PATH = SESSION_DIR / "state.json"
MONITOR_PATH = SESSION_DIR / "risk_monitor.json"
RISK_REF = ROOT / "memory" / "p6_mom_risk_approval_ref.json"
LEDGER = ROOT / "memory" / "hypotheses_ledger.jsonl"

EXIT_OK = 0
EXIT_NOT_DUE = 5


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> int:
    now = datetime.now(timezone.utc)
    if now < WINDOW_START:
        print(f"AGUARDANDO_INICIO: janela comeca em {_iso(WINDOW_START)} (agora {_iso(now)}).")
        return EXIT_NOT_DUE

    if MONITOR_PATH.exists():
        monitor = json.loads(MONITOR_PATH.read_text(encoding="utf-8"))
        if monitor.get("breached"):
            print("INTERRUPCAO_RISCO: limite de drawdown atingido; novas entradas bloqueadas.")
            return 3

    next_start = WINDOW_START
    if STATE_PATH.exists():
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        if state.get("protocol") != PROTOCOL:
            print("FATAL: state da sessao pertence a outro protocolo.", file=sys.stderr)
            return 4
        last_timestamp = state.get("last_timestamp")
        if last_timestamp:
            next_start = _parse_iso(last_timestamp) + timedelta(minutes=1)

    last_complete_ms = download_klines.last_complete_minute_ms()
    end = datetime.fromtimestamp(last_complete_ms / 1000, tz=timezone.utc)
    hard_end = WINDOW_END - timedelta(minutes=1)
    if next_start > hard_end:
        print("JANELA_COMPLETA: coleta encerrada; rode a avaliacao final unica.")
        return EXIT_NOT_DUE
    if end > hard_end:
        end = hard_end

    start_ms = (int(next_start.timestamp()) // 60) * 60 * 1000
    end_ms = (int(end.timestamp()) // 60) * 60 * 1000
    if end_ms < start_ms:
        print(f"NADA_NOVO: sem candle fechado depois de {_iso(next_start)}.")
        return EXIT_NOT_DUE

    SEGMENTS_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = SEGMENTS_DIR / f"segment_1m_{start_ms}_{end_ms}.csv"
    if csv_path.exists():
        print(f"Reutilizando CSV ja baixado: {csv_path}")
    else:
        rc = download_klines.main([
            "--symbol", SYMBOL,
            "--start", _iso(next_start),
            "--end", _iso(end),
            "--output", str(csv_path),
        ])
        if rc != 0:
            print(f"FALHA_COLETA: download_klines rc={rc}; segmento nao alimentado.", file=sys.stderr)
            return 4
        report_src = ROOT / "reports" / f"data_quality_{SYMBOL}_1m.json"
        if report_src.exists():
            REPORTS_DIR.mkdir(parents=True, exist_ok=True)
            shutil.copy2(
                report_src,
                REPORTS_DIR / f"data_quality_{SYMBOL}_1m_{start_ms}_{end_ms}.json",
            )

    return subprocess.call([
        sys.executable,
        str(ROOT / "scripts" / "run_shadow_prospectivo.py"),
        "--segment", str(csv_path),
        "--out", str(SESSION_DIR),
        "--risk-approval", str(RISK_REF),
        "--ledger", str(LEDGER),
        "--protocol", PROTOCOL,
        "--window-id", WINDOW_ID,
    ])


if __name__ == "__main__":
    raise SystemExit(main())
