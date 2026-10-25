from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_pages_permissions_are_job_scoped_and_opt_in_is_unchanged():
    workflow = (ROOT / ".github" / "workflows" / "fvt-dashboard.yml").read_text(encoding="utf-8")
    assert "permissions:\n  contents: read\n\nconcurrency:" in workflow
    assert "  build:\n    name: Build evidence-backed dashboard\n    permissions:\n      contents: read\n    runs-on:" in workflow
    assert "vars.ENABLE_PUBLIC_PAGES == 'true'" in workflow
    assert "pages: write\n      id-token: write" in workflow.split("  deploy:", 1)[1]
    assert "pages: write\n  id-token: write" not in workflow.split("jobs:", 1)[0]


def test_learning_collector_has_no_dependency_on_frozen_track():
    workflow = (ROOT / ".github" / "workflows" / "learning-collect.yml").read_text(encoding="utf-8")
    collector_source = (ROOT / "learning" / "collector.py").read_text(encoding="utf-8")
    assert "schedule:" in workflow and "workflow_dispatch:" in workflow
    assert "\n  push:" not in workflow
    assert "p6-mom-runtime" not in workflow
    assert "p6-mom-cloud-live.yml" not in workflow
    assert "hypotheses_ledger" not in collector_source
    assert "manifest.json" not in collector_source


def test_exploratory_language_is_explicit():
    dashboard = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
    backtest = (ROOT / "learning" / "experiments" / "backtest.py").read_text(encoding="utf-8")
    assert "EXPLORATÓRIO — NÃO É PROVA" in dashboard
    assert "EXPLORATÓRIO — NÃO É PROVA" in backtest
