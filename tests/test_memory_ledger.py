import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "memory" / "hypotheses_ledger.jsonl"
JOURNAL = ROOT / "memory" / "journal.md"

VALID_TYPES = {"hipotese", "protocolo", "fato"}
VALID_STATUS = {
    "hipotese": {"confirmada", "refutada", "pendente", "queimada", "nao_executada"},
    "protocolo": {"ativo"},
    "fato": {"registrado"},
}
REQUIRED_FIELDS = {"record_type", "id", "statement", "source", "status", "recorded_at"}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
PATH_RE = re.compile(r"^(?P<path>[A-Za-z0-9_./\\-]+\.[A-Za-z0-9]+)(?::\d+(?:-\d+)?)?")


def _load():
    assert LEDGER.exists(), f"Ledger ausente: {LEDGER}"
    records = []
    for lineno, line in enumerate(
        LEDGER.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise AssertionError(f"linha {lineno} nao e JSON valido: {exc}") from exc
    assert records, "Ledger vazio"
    return records


def test_ledger_has_hypotheses_and_protocol_records():
    records = _load()
    types = {r["record_type"] for r in records}
    assert types <= VALID_TYPES, f"record_type desconhecido: {types - VALID_TYPES}"
    ids = [r["id"] for r in records]
    assert len(ids) == len(set(ids)), f"IDs duplicados: {ids}"
    assert any(r["record_type"] == "hipotese" for r in records)
    assert any(r["record_type"] == "protocolo" for r in records)
    assert any(r["record_type"] == "fato" for r in records)


def test_ledger_required_fields_and_enums():
    for rec in _load():
        missing = REQUIRED_FIELDS - set(rec)
        assert not missing, f"{rec.get('id')}: campos ausentes {missing}"
        assert DATE_RE.match(rec["recorded_at"]), rec["id"]
        allowed = VALID_STATUS[rec["record_type"]]
        assert rec["status"] in allowed, (
            f"{rec['id']}: status {rec['status']!r} fora de {sorted(allowed)}"
        )
        assert rec["statement"].strip(), f"{rec['id']}: statement vazio"
        assert rec["source"].strip(), f"{rec['id']}: source vazio"


def test_hypotheses_have_scope_evidence_and_decision():
    for rec in _load():
        if rec["record_type"] != "hipotese":
            continue
        assert rec.get("data_scope", "").strip(), f"{rec['id']}: data_scope ausente"
        assert rec.get("evidence"), f"{rec['id']}: evidence ausente"
        assert rec.get("decision", "").strip(), f"{rec['id']}: decision ausente"


def test_sources_reference_existing_files():
    checked = 0
    for rec in _load():
        token = rec["source"].split()[0]
        match = PATH_RE.match(token)
        if not match:
            continue
        path = ROOT / match.group("path").replace("\\", "/")
        assert path.exists(), f"{rec['id']}: arquivo citado nao existe: {path}"
        checked += 1
    assert checked >= 8, f"poucos sources validados como caminho: {checked}"


def test_final_test_block_exposure_is_locked_as_burned():
    records = _load()
    fatos = [r for r in records if r["record_type"] == "fato"]
    assert fatos, "nenhum registro fato (regra do bloco final ausente)"
    texto = " ".join(r["statement"] for r in fatos).lower()
    assert "queimado" in texto, "regra de bloco final queimado nao registrada"
    assert "25%" in texto, "fracao do bloco final nao registrada"


def test_h10_parity_divergence_is_recorded_as_refuted():
    alvo = [r for r in _load() if r["id"] == "H10"]
    assert alvo, "H10 (paridade motor vs lab v2) ausente"
    rec = alvo[0]
    assert rec["status"] == "refutada"
    joined = json.dumps(rec, ensure_ascii=False)
    assert "0,9887" in joined, "delta medido (+0,9887 p.p.) nao registrado"


def test_journal_exists_and_records_this_cycle():
    assert JOURNAL.exists(), f"Journal ausente: {JOURNAL}"
    texto = JOURNAL.read_text(encoding="utf-8")
    assert "## 2026-10-22" in texto, "data do ciclo ausente"
    assert "hypotheses_ledger" in texto, "journal nao referencia o ledger"
    assert "git add" in texto, "decisao de versionamento nao registrada"
