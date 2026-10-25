#!/usr/bin/env python3
"""Detector de look-ahead bias no pipeline M15_original (adaptacao Freqtrade).

Abordagem adaptada de freqtrade/docs/lookahead-analysis.md: calcular a
referencia no desenvolvimento inteiro, recalcular as MESMAS features com
varios prefixos temporais que compartilham o mesmo inicio e comparar, nos
timestamps comuns, todas as colunas de indicadores/features/sinais que
deveriam ser causais.

Fluxo:
  1. referencia = generate_features(candles_dev, "15m", ORIGINAL_CONFIG) +
     reconcile_full (interfaces reais de research/run_research.py).
  2. prefixos  = generate_features(candles_dev.iloc[:cut]) para cut em
     25%, 50% e 75% do desenvolvimento (mesmo inicio, mesmo codigo).
  3. comparacao coluna a coluna nas linhas comuns [0, cut):
       - colunas discretas/booleanas/temporais: igualdade EXATA (NaN==NaN).
       - colunas float: np.isclose com RTOL/ATOL explicitos.
  4. classificacao por divergencia:
       - BORDA      : dentro das ultimas TAIL_WINDOW_ROWS do corte E na
                      coluna sujeta ao mecanismo de truncagem documentado do
                      contexto Pai (merge_asof/ barra 15m incompleta).
       - REAL       : divergencia com passado identico (mid) ou divergencia
                      fora das colunas de truncagem (janela so-passada nao
                      pode mudar por truncamento futuro).
       - INCONCLUSIVO: coluna nao comparavel (ausente/tipo divergente) ou
                      bloqueio de recalculo (interface real indisponivel).
  5. veredito: INCONCLUSIVO (bloqueio), VAZAMENTO DETECTADO (qualquer REAL)
     ou PASSOU (somente BORDA ou nenhum).

Escopo permitido: apenas o desenvolvimento (treino + validacao). O bloco
final de teste de 25% e descartado imediatamente apos a leitura do CSV,
sem nenhum calculo. 100% offline.

Saidas: research/out/lookahead_audit_<UTC>/report.md e differences.csv.
Cria apenas arquivos novos; nunca sobrescreve resultados previos.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "research"), str(ROOT / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import run_research as rr  # noqa: E402

CSV = rr.CSV
EXPECTED_SHA256 = rr.EXPECTED_SHA256

PREFIX_FRACTIONS = (0.25, 0.50, 0.75)
RTOL = 1e-9
ATOL = 1e-12
TAIL_WINDOW_ROWS = 2
WARMUP_EXCLUDED_ROWS = 0

DISCRETE_COLUMNS = frozenset({
    "signal",
    "parent_direction",
    "child_direction",
    "fibonacci_confirmed",
    "regime_acceptable",
    "volume_confirmed",
    "momentum_confirmed",
    "buy_confirmations",
})
BENIGN_TAIL_COLUMNS = frozenset({
    "parent_direction",
    "parent_close",
    "signal",
    "buy_confirmations",
})

VERDICT_PASS = "PASSOU"
VERDICT_LEAK = "VAZAMENTO DETECTADO"
VERDICT_INCONCLUSIVE = "INCONCLUSIVO"

CODE_NOTES = {
    "timestamp": "entrada apos parse ISO8601 + sort estavel (strategy.py:118-120)",
    "open": "coluna de entrada repassada (strategy.py:126)",
    "high": "coluna de entrada repassada (strategy.py:126)",
    "low": "coluna de entrada repassada (strategy.py:126)",
    "close": "coluna de entrada repassada (strategy.py:126)",
    "volume": "coluna de entrada repassada (strategy.py:126)",
    "close_time": "coluna de entrada repassada (strategy.py:126)",
    "quote_volume": "coluna de entrada repassada (strategy.py:126)",
    "trades": "coluna de entrada repassada (strategy.py:126)",
    "taker_buy_base_volume": "coluna de entrada repassada (strategy.py:126)",
    "taker_buy_quote_volume": "coluna de entrada repassada (strategy.py:126)",
    "parent_direction": (
        "resample 15min closed=left so com barras completas (bar_count==15) e "
        "merge_asof backward com tolerance 15min (strategy.py:65-67, 83-88, 137-146)"
    ),
    "parent_close": (
        "fechamento da barra 15m completa unida por merge_asof backward "
        "(strategy.py:83-88, 137-147)"
    ),
    "child_direction": (
        "EWMs sobre a serie 1m com min_periods, comparacoes com shift(3) "
        "(strategy.py:150-157)"
    ),
    "fib_618": (
        "high.shift(1).rolling(fib_lookback).max/min — referencia anterior ao "
        "candle atual (strategy.py:160-162)"
    ),
    "atr": (
        "true_range com prev_close=close.shift(1) e rolling(atr_window).mean "
        "(strategy.py:165-169)"
    ),
    "fibonacci_confirmed": (
        "fib_touch usando apenas candle atual e anteriores (strategy.py:171-178)"
    ),
    "regime_zscore": (
        "rolling(regime_window).mean/std(ddof=1) — janela apenas-passada, "
        "sem estatistica global (strategy.py:181-183)"
    ),
    "regime_acceptable": "between sobre regime_zscore (strategy.py:184)",
    "relative_volume": (
        "baseline = quote_volume.shift(1).rolling(volume_lookback).mean "
        "(strategy.py:193-194)"
    ),
    "volume_confirmed": ">= relative_volume_min (strategy.py:195)",
    "normalized_slope": (
        "rolling(momentum_window).apply(_rolling_log_slope); a centralizacao "
        "de x/y ocorre SOMENTE dentro da janela (strategy.py:91-102, 198-203)"
    ),
    "normalized_acceleration": (
        "normalized_slope - normalized_slope.shift(momentum_window) "
        "(strategy.py:204)"
    ),
    "momentum_confirmed": "slope > 0 e aceleracao > 0 (strategy.py:205)",
    "signal": (
        "maquina de estados sequencial iniciada na linha 0; so emite eventos "
        "a partir de condicoes causais (strategy.py:225-236)"
    ),
    "buy_confirmations": (
        "soma das seis condicoes de compra causais (strategy.py:237-244)"
    ),
}
DEFAULT_NOTE = (
    "construcao nao catalogada; inspecionar generate_strategy_signals em "
    "src/convergencia/strategy.py"
)

CSV_FIELDS = [
    "record_type",
    "prefix_fraction",
    "cut_row",
    "cut_timestamp",
    "column",
    "row",
    "timestamp",
    "reference_value",
    "prefix_value",
    "abs_diff",
    "region",
    "classification",
    "explanation",
    "count_total_in_group",
    "count_mid_in_group",
    "count_tail_in_group",
    "first_timestamp",
    "last_timestamp",
    "occurrences_logged",
]


class LookaheadBlocker(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    return rr.sha256_file(path)


def load_dev_candles() -> tuple[pd.DataFrame, dict]:
    digest = sha256_file(CSV)
    if digest != EXPECTED_SHA256:
        raise LookaheadBlocker(f"SHA256 do CSV diverge do constante do projeto: {digest}")
    full = pd.read_csv(CSV)
    n = len(full)
    dev_end = int(n * (rr.SPLIT_FRACS["train"] + rr.SPLIT_FRACS["validation"]))
    dev = full.iloc[:dev_end].reset_index(drop=True)
    ts = pd.to_datetime(dev["timestamp"], format="ISO8601", utc=True)
    meta = {
        "csv_sha256": digest,
        "rows_total": n,
        "dev_rows": dev_end,
        "test_block_start": dev_end,
        "start_timestamp": str(ts.iloc[0]),
        "end_timestamp": str(ts.iloc[-1]),
        "split_fracs": dict(rr.SPLIT_FRACS),
    }
    return dev, meta


def compute_features(candles: pd.DataFrame) -> pd.DataFrame:
    feats = rr.generate_features(candles, "15m", rr.ORIGINAL_CONFIG)
    rr.reconcile_full(feats)
    return feats


def _is_exact_column(name: str, series: pd.Series) -> bool:
    if name in DISCRETE_COLUMNS:
        return True
    if pd.api.types.is_float_dtype(series):
        return False
    return True


def _classify(column: str, row: int, cut_row: int, comparable: bool) -> tuple[str, str, str]:
    if not comparable:
        return (
            "nao_comparavel",
            "INCONCLUSIVO",
            "coluna ausente ou com tipo divergente entre referencia e prefixo; "
            "causa nao determinada pelo metodo.",
        )
    tail_start = cut_row - TAIL_WINDOW_ROWS
    if row >= tail_start and column in BENIGN_TAIL_COLUMNS:
        return (
            "tail",
            "BORDA",
            "borda de truncagem documentada: no corte a barra 15m do contexto Pai "
            "ainda esta incompleta no prefixo (bar_count==15, strategy.py:67) e o "
            "merge_asof backward (strategy.py:137-147) usa a barra anterior; a "
            "divergencia ocorre apenas na ultima linha do prefixo, quando "
            "minute_available_at iguala o available_at da barra recem-fechada. "
            "Nao indica uso de dados futuros.",
        )
    note = CODE_NOTES.get(column, DEFAULT_NOTE)
    if row >= tail_start:
        return (
            "tail",
            "REAL",
            f"divergencia na borda do corte em coluna que NAO depende do "
            f"truncamento do contexto Pai: construcoes apenas-passadas "
            f"(rolling/EWM/shift negativo) nao mudam quando o futuro e cortado, "
            f"portanto o prefixo usa dados futuros nesta coluna. Construcao "
            f"inspecionada: {note}.",
        )
    return (
        "mid",
        "REAL",
        f"passado identico e futuro maior alteram o valor na mesma linha: "
        f"dependencia retrospectiva. Construcao inspecionada: {note}.",
    )


def compare_frames(
    reference: pd.DataFrame,
    prefix: pd.DataFrame,
    fraction: float,
    cut_row: int,
) -> list[dict]:
    if cut_row <= 0 or cut_row > len(reference):
        raise ValueError(f"cut_row invalido: {cut_row}")
    if len(prefix) != cut_row:
        raise ValueError(
            f"prefixo deve ter exatamente cut_row linhas: {len(prefix)} != {cut_row}"
        )
    ref = reference.iloc[:cut_row]
    ts_ref = ref["timestamp"].to_numpy() if "timestamp" in reference.columns else None
    records: list[dict] = []
    for column in reference.columns:
        if column not in prefix.columns:
            region, classification, explanation = _classify(column, 0, cut_row, False)
            records.append({
                "prefix_fraction": fraction,
                "cut_row": cut_row,
                "cut_timestamp": _cut_timestamp(ref),
                "column": column,
                "row": "",
                "timestamp": "",
                "reference_value": "",
                "prefix_value": "",
                "abs_diff": "",
                "region": region,
                "classification": classification,
                "explanation": explanation,
            })
            continue
        a = ref[column].reset_index(drop=True)
        b = prefix[column].reset_index(drop=True)
        if _is_exact_column(column, a):
            equal = ((a == b) | (a.isna() & b.isna())).fillna(False).astype(bool)
            diverge = ~equal
            if pd.api.types.is_numeric_dtype(a) and pd.api.types.is_numeric_dtype(b):
                av = a.to_numpy(dtype="float64")
                bv = b.to_numpy(dtype="float64")
                abs_diff = pd.Series(np.abs(av - bv), index=a.index)
            else:
                abs_diff = pd.Series(np.nan, index=a.index)
        else:
            av = a.to_numpy(dtype=float)
            bv = b.to_numpy(dtype=float)
            close = np.isclose(av, bv, rtol=RTOL, atol=ATOL, equal_nan=True)
            diverge = pd.Series(~close, index=a.index)
            with np.errstate(invalid="ignore"):
                abs_diff = pd.Series(np.abs(av - bv), index=a.index)
        idx_rows = np.flatnonzero(diverge.to_numpy())
        for i in idx_rows:
            i = int(i)
            region, classification, explanation = _classify(column, i, cut_row, True)
            records.append({
                "prefix_fraction": fraction,
                "cut_row": cut_row,
                "cut_timestamp": _cut_timestamp(ref),
                "column": column,
                "row": i,
                "timestamp": str(ts_ref[i]) if ts_ref is not None else str(i),
                "reference_value": _fmt_value(a.iloc[i]),
                "prefix_value": _fmt_value(b.iloc[i]),
                "abs_diff": _fmt_abs(abs_diff.iloc[i]),
                "region": region,
                "classification": classification,
                "explanation": explanation,
            })
    return records


def _cut_timestamp(ref: pd.DataFrame) -> str:
    if "timestamp" in ref.columns and len(ref):
        return str(ref["timestamp"].iloc[-1])
    return str(len(ref))


def _fmt_value(value) -> str:
    if value is None or (isinstance(value, float) and not np.isfinite(value)):
        return str(value)
    if isinstance(value, (np.floating, float)):
        return repr(float(value))
    return str(value)


def _fmt_abs(value) -> str:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return ""
    if not np.isfinite(v):
        return str(v)
    return repr(v)


def decide_verdict(records: list[dict], blocker: str | None) -> str:
    if blocker:
        return VERDICT_INCONCLUSIVE
    if any(r.get("classification") == "REAL" for r in records):
        return VERDICT_LEAK
    if any(r.get("classification") == "INCONCLUSIVO" for r in records):
        return VERDICT_INCONCLUSIVE
    return VERDICT_PASS


def _group_records(records: list[dict]) -> dict:
    groups: dict = {}
    for rec in records:
        key = (rec["prefix_fraction"], rec["cut_row"], rec["column"])
        groups.setdefault(key, []).append(rec)
    return groups


def write_differences_csv(path: Path, records: list[dict], per_prefix: list[dict]) -> None:
    rows: list[dict] = []
    for stats in per_prefix:
        if stats["divergences"] == 0:
            rows.append({
                "record_type": "summary",
                "prefix_fraction": stats["fraction"],
                "cut_row": stats["cut_row"],
                "cut_timestamp": stats["cut_timestamp"],
                "column": "(todas)",
                "count_total_in_group": 0,
                "count_mid_in_group": 0,
                "count_tail_in_group": 0,
                "occurrences_logged": 0,
                "explanation": "nenhuma divergencia nas colunas comparadas",
            })
    groups = _group_records(records)
    for (fraction, cut_row, column), group in sorted(
        groups.items(), key=lambda kv: (kv[0][0], str(kv[0][2]))
    ):
        mid = sum(1 for r in group if r["region"] == "mid")
        tail = sum(1 for r in group if r["region"] == "tail")
        classes = sorted({r["classification"] for r in group})
        rows.append({
            "record_type": "summary",
            "prefix_fraction": fraction,
            "cut_row": cut_row,
            "cut_timestamp": group[0]["cut_timestamp"],
            "column": column,
            "count_total_in_group": len(group),
            "count_mid_in_group": mid,
            "count_tail_in_group": tail,
            "first_timestamp": group[0]["timestamp"],
            "last_timestamp": group[-1]["timestamp"],
            "occurrences_logged": "",
            "explanation": f"classificacoes: {', '.join(classes)}",
        })
        limit = 2000
        if len(group) <= limit:
            logged = list(group)
        else:
            half = limit // 2
            logged = group[:half] + group[-half:]
        for rec in logged:
            out = {"record_type": "occurrence"}
            out.update(rec)
            out["occurrences_logged"] = len(logged)
            rows.append(out)
    with path.open("w", encoding="utf-8", newline="") as stream:
        stream.write(",".join(CSV_FIELDS) + "\n")
        for row in rows:
            cells = []
            for field_name in CSV_FIELDS:
                value = row.get(field_name, "")
                text = "" if value is None else str(value)
                if any(ch in text for ch in ',"\n\r'):
                    text = '"' + text.replace('"', '""') + '"'
                cells.append(text)
            stream.write(",".join(cells) + "\n")


def write_report(
    path: Path,
    verdict: str,
    blocker: str | None,
    meta: dict,
    per_prefix: list[dict],
    records: list[dict],
    columns_compared: list[str],
) -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines: list[str] = []
    lines.append("# Auditoria de look-ahead bias — M15_original (adaptacao Freqtrade)")
    lines.append("")
    lines.append(f"- Gerado (UTC): {now}")
    lines.append(f"- Veredito: **{verdict}**")
    if blocker:
        lines.append(f"- Bloqueio: {blocker}")
    lines.append("")
    lines.append("## Metodo")
    lines.append("")
    lines.append(
        "- Referencia: features calculadas no desenvolvimento inteiro pela interface real "
        "`generate_features(candles, '15m', ORIGINAL_CONFIG)` + `reconcile_full` "
        "(research/run_research.py)."
    )
    lines.append(
        f"- Prefixos recalculados a partir do MESMO inicio: cortes em "
        f"{', '.join(f'{int(f * 100)}%' for f in PREFIX_FRACTIONS)} do desenvolvimento."
    )
    lines.append(
        "- Comparacao nas linhas comuns [0, cut) de TODAS as colunas de "
        "indicadores/features/sinais (mais as colunas de entrada, que sao repassadas)."
    )
    lines.append(
        f"- Tolerancia numerica (floats): rtol={RTOL:g}, atol={ATOL:g} via `np.isclose` "
        "com `equal_nan=True`; **igualdade exata** para colunas discretas/booleanas/"
        "temporais (`signal`, direcoes, flags de confirmacao, timestamps)."
    )
    lines.append(
        f"- Warm-up excluido: {WARMUP_EXCLUDED_ROWS} linhas — todos os recortes "
        "compartilham o inicio identico (linha 0), portanto o aquecimento inicial e "
        "identico em referencia e prefixos; NaN==NaN e tratado como igualdade, sem "
        "falso positivo e sem necessidade de exclusao."
    )
    lines.append(
        f"- Janela de borda (TAIL_WINDOW_ROWS): {TAIL_WINDOW_ROWS} linhas finais de cada "
        "prefixo. Justificativa pelo codigo: a barra 15m do contexto Pai so e "
        "disponivel em `available_at = inicio + 15min` (strategy.py:84) e o prefixo "
        "descarta a barra incompleta (`bar_count == 15`, strategy.py:67); no corte isso "
        "afeta no maximo a ultima linha (minute_available_at igualando o available_at da "
        "barra recem-fechada). Divergencias na borda SAO reportadas (nao escondidas) e "
        "classificadas como BORDA apenas quando ocorrem nas colunas sujeitas a esse "
        "mecanismo: parent_direction, parent_close, signal, buy_confirmations."
    )
    lines.append("")
    lines.append("### Regras de classificacao")
    lines.append("")
    lines.append(
        "- **BORDA**: nas ultimas "
        f"{TAIL_WINDOW_ROWS} linhas E em coluna sujeta ao truncamento do contexto Pai "
        "(mecanismo documentado acima)."
    )
    lines.append(
        "- **REAL (falha real)**: qualquer divergencia com passado identico (regiao mid), "
        "ou divergencia na borda em coluna de janela puramente passada (rolling/EWM/"
        "shift) — truncamento futuro nao pode alterar essas colunas."
    )
    lines.append(
        "- **INCONCLUSIVO**: coluna nao comparavel entre referencia e prefixo, ou "
        "bloqueio ao recalcular pelas interfaces reais do projeto."
    )
    lines.append("")
    lines.append("## Conjunto de dados")
    lines.append("")
    if meta:
        lines.append(f"- CSV: `data/raw/BTCUSDT_1m.csv` SHA-256 `{meta.get('csv_sha256')}`")
        lines.append(
            f"- Desenvolvimento: linhas [0, {meta.get('dev_rows')}) de "
            f"{meta.get('rows_total')} = {meta.get('start_timestamp')} ate "
            f"{meta.get('end_timestamp')}"
        )
        lines.append(
            f"- Bloco de teste [{meta.get('test_block_start')}, {meta.get('rows_total')}): "
            "descartado imediatamente apos a leitura; NENHUM calculo, consulta ou "
            "metrica foi feito sobre essas linhas."
        )
        lines.append("- Offline: nenhuma rede, download, instalacao ou sessao sombra.")
    else:
        lines.append("- Metadados indisponiveis (bloqueio na leitura).")
    lines.append("")
    lines.append("## Colunas auditadas e construcao inspecionada")
    lines.append("")
    lines.append("| coluna | construcao (codigo real) | causal esperada |")
    lines.append("|---|---|---|")
    for column in columns_compared:
        note = CODE_NOTES.get(column, DEFAULT_NOTE)
        lines.append(f"| {column} | {note} | sim |")
    lines.append("")
    lines.append("## Resultados por prefixo")
    lines.append("")
    lines.append("| corte | linha | timestamp do corte | colunas | divergencias | mid | borda | REAL | INCONCLUSIVO |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for stats in per_prefix:
        lines.append(
            f"| {stats['fraction']:.2f} | {stats['cut_row']} | {stats['cut_timestamp']} | "
            f"{stats['columns']} | {stats['divergences']} | {stats['mid']} | "
            f"{stats['tail']} | {stats['real']} | {stats['inconclusive']} |"
        )
    lines.append("")
    lines.append("## Divergencias encontradas")
    lines.append("")
    if not records:
        lines.append(
            "- **Nenhuma divergencia** em nenhuma coluna, em nenhum timestamp comum dos "
            "tres prefixos avaliados."
        )
    else:
        real = [r for r in records if r["classification"] == "REAL"]
        borda = [r for r in records if r["classification"] == "BORDA"]
        incon = [r for r in records if r["classification"] == "INCONCLUSIVO"]
        lines.append(
            f"- Total: {len(records)} divergencias | REAL: {len(real)} | "
            f"BORDA: {len(borda)} | INCONCLUSIVO: {len(incon)}"
        )
        cols = sorted({str(r['column']) for r in records})
        lines.append(f"- Colunas divergentes: {', '.join(cols)}")
        shown = records[:50]
        lines.append("")
        lines.append("| corte | coluna | linha | timestamp | ref | prefixo | regiao | class |")
        lines.append("|---|---|---|---|---|---|---|---|")
        for r in shown:
            lines.append(
                f"| {r['prefix_fraction']:.2f} | {r['column']} | {r['row']} | "
                f"{r['timestamp']} | {r['reference_value']} | {r['prefix_value']} | "
                f"{r['region']} | {r['classification']} |"
            )
        if len(records) > len(shown):
            lines.append("")
            lines.append(
                f"- ... {len(records) - len(shown)} divergencias restantes em "
                "differences.csv (ocorrencias completas ou amostra primeiro/ultimo, "
                "com contagens totais sempre no resumo)."
            )
        lines.append("")
        lines.append("### Explicacoes")
        lines.append("")
        seen = set()
        for r in records:
            key = (r["column"], r["classification"])
            if key in seen:
                continue
            seen.add(key)
            lines.append(f"- `{r['column']}` [{r['classification']}]: {r['explanation']}")
    lines.append("")
    lines.append("## Veredito")
    lines.append("")
    if verdict == VERDICT_PASS:
        lines.append(
            "- **PASSOU**: os tres prefixos do desenvolvimento nao revelaram vazamento "
            "nas colunas verificadas. Significa apenas que os recortes avaliados nao "
            "revelaram vazamento nas colunas verificadas; NAO prova rentabilidade nem "
            "validacao independente."
        )
    elif verdict == VERDICT_LEAK:
        lines.append(
            "- **VAZAMENTO DETECTADO**: existe pelo menos uma divergencia classificada "
            "como REAL — ver lista e explicacoes acima."
        )
    else:
        lines.append(
            "- **INCONCLUSIVO**: o recalculo pelas interfaces reais do projeto falhou ou "
            "ha colunas nao comparaveis; ver bloqueio/detalhes acima. Nao ha conclusao "
            "sobre presenca ou ausencia de vazamento."
        )
    lines.append("")
    lines.append("## Limitacoes")
    lines.append("")
    lines.append(
        "- Metodo adaptado do Freqtrade: detecta colunas cujo valor muda quando o mesmo "
        "passado recebe candles futuros nos cortes 25/50/75% do desenvolvimento; nao "
        "explora todos os tamanhos de corte possiveis."
    )
    lines.append(
        "- Colunas de entrada OHLCV sao repassadas sem transformacao; qualquer "
        "divergencia nelas indicaria problema de preprocessing, nao da estrategia."
    )
    lines.append(
        "- Janela de borda de "
        f"{TAIL_WINDOW_ROWS} linhas baseada no mecanismo de disponibilidade da barra "
        "15m inspecionado no codigo; uma dependencia futura de horizonte <= "
        f"{TAIL_WINDOW_ROWS} linhas em coluna DO CONTEXTO PAI seria classificada como "
        "BORDA (residual teorico documentado)."
    )
    lines.append(
        "- Bloco de teste de 25% nao foi aberto, calculado nem consultado; nenhum "
        "resultado deste relatorio o utiliza."
    )
    lines.append(
        "- PASSOU e apenas ausencia de vazamento nos recortes avaliados; nao e "
        "evidencia de rentabilidade nem validacao da estrategia."
    )
    lines.append(
        "- Janela prospectiva de 30 dias nao foi iniciada; nenhum arquivo preexistente "
        "foi alterado."
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_audit(out_dir: Path, fractions: tuple = PREFIX_FRACTIONS) -> dict:
    blocker: str | None = None
    records: list[dict] = []
    per_prefix: list[dict] = []
    meta: dict = {}
    columns_compared: list[str] = []
    try:
        dev, meta = load_dev_candles()
        reference = compute_features(dev)
        columns_compared = list(reference.columns)
    except Exception as exc:
        blocker = (
            "nao foi possivel recalcular os sinais pelas interfaces reais do projeto: "
            f"{type(exc).__name__}: {exc}"
        )
        verdict = decide_verdict(records, blocker)
        out_dir.mkdir(parents=True, exist_ok=False)
        write_differences_csv(out_dir / "differences.csv", records, per_prefix)
        write_report(
            out_dir / "report.md", verdict, blocker, meta, per_prefix, records,
            columns_compared,
        )
        return {"verdict": verdict, "blocker": blocker, "records": records,
                "per_prefix": per_prefix, "meta": meta, "out_dir": out_dir}

    for fraction in fractions:
        cut_row = int(len(dev) * fraction)
        try:
            prefix_feats = compute_features(dev.iloc[:cut_row].reset_index(drop=True))
        except Exception as exc:
            blocker = (
                "nao foi possivel recalcular os sinais para o prefixo "
                f"{fraction:.2f} pelas interfaces reais do projeto: "
                f"{type(exc).__name__}: {exc}"
            )
            break
        recs = compare_frames(reference, prefix_feats, fraction, cut_row)
        records.extend(recs)
        per_prefix.append({
            "fraction": fraction,
            "cut_row": cut_row,
            "cut_timestamp": str(reference["timestamp"].iloc[cut_row - 1]),
            "columns": len(columns_compared),
            "divergences": len(recs),
            "mid": sum(1 for r in recs if r["region"] == "mid"),
            "tail": sum(1 for r in recs if r["region"] == "tail"),
            "real": sum(1 for r in recs if r["classification"] == "REAL"),
            "inconclusive": sum(
                1 for r in recs if r["classification"] == "INCONCLUSIVO"
            ),
        })

    verdict = decide_verdict(records, blocker)
    out_dir.mkdir(parents=True, exist_ok=False)
    write_differences_csv(out_dir / "differences.csv", records, per_prefix)
    write_report(
        out_dir / "report.md", verdict, blocker, meta, per_prefix, records,
        columns_compared,
    )
    return {"verdict": verdict, "blocker": blocker, "records": records,
            "per_prefix": per_prefix, "meta": meta, "out_dir": out_dir,
            "columns_compared": columns_compared}


def _default_out_dir() -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base = ROOT / "research" / "out"
    candidate = base / f"lookahead_audit_{stamp}"
    suffix = 1
    while candidate.exists():
        suffix += 1
        candidate = base / f"lookahead_audit_{stamp}_{suffix}"
    return candidate


def main() -> int:
    out_dir = _default_out_dir()
    result = run_audit(out_dir)
    print("=" * 100)
    print(f"VEREDITO: {result['verdict']}")
    if result["blocker"]:
        print(f"BLOQUEIO: {result['blocker']}")
    print("=" * 100)
    meta = result["meta"]
    if meta:
        print(
            f"Desenvolvimento: [{0}, {meta['dev_rows']}) de {meta['rows_total']} | "
            f"{meta['start_timestamp']} -> {meta['end_timestamp']}"
        )
        print(f"Bloco de teste [{meta['test_block_start']}, {meta['rows_total']}): NAO tocado.")
    for stats in result["per_prefix"]:
        print(
            f"Prefixo {stats['fraction']:.2f} cut={stats['cut_row']} "
            f"({stats['cut_timestamp']}): {stats['columns']} colunas, "
            f"{stats['divergences']} divergencias "
            f"(mid={stats['mid']}, borda={stats['tail']}, REAL={stats['real']}, "
            f"INCONC={stats['inconclusive']})"
        )
    records = result["records"]
    if records:
        print("-" * 100)
        print(f"DIVERGENCIAS ({len(records)}):")
        for rec in records[:40]:
            print(
                f"  [{rec['classification']}/{rec['region']}] {rec['column']} "
                f"linha {rec['row']} {rec['timestamp']}: ref={rec['reference_value']} "
                f"prefixo={rec['prefix_value']}"
            )
        if len(records) > 40:
            print(f"  ... {len(records) - 40} restantes em differences.csv")
    else:
        print("Nenhuma divergencia em nenhuma coluna comparada.")
    print("-" * 100)
    print(f"Resultados: {result['out_dir']}")
    print("  report.md | differences.csv")
    print(
        "Lembrete: PASSOU = ausencia de vazamento nos recortes avaliados; "
        "nao prova rentabilidade nem validacao independente."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
