from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / ".agents" / "skills" / "trader-skill" / "SKILL.md"
NOTICE = ROOT / ".agents" / "skills" / "trader-skill" / "UPSTREAM.md"


def test_trader_skill_has_valid_agent_skill_metadata_and_boundaries():
    content = SKILL.read_text(encoding="utf-8")
    assert content.startswith("---\nname: trader-skill\n")
    assert "\ndescription:" in content
    assert "EXPLORATÓRIO — NÃO É PROVA" in content
    assert ".github/workflows/p6-mom-cloud-live.yml" in content
    assert "memory/hypotheses_ledger.jsonl" in content
    assert "p6-mom-runtime" in content
    assert "Do not dispatch, re-enable, or restart" in content
    assert "src/convergencia/backtest.py" in content
    assert "src/convergencia/data.py" in content


def test_trader_skill_source_attribution_is_present():
    content = NOTICE.read_text(encoding="utf-8")
    assert "HKUDS/Vibe-Trading" in content
    assert "strategy-generate/SKILL.md" in content
    assert "MIT" in content
