from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_pages_permissions_are_job_scoped_and_opt_in_is_unchanged():
    workflow = (ROOT / ".github" / "workflows" / "fvt-dashboard.yml").read_text(encoding="utf-8")
    assert "permissions:\n  contents: none\n\nconcurrency:" in workflow
    assert "  build:\n    name: Build evidence-backed dashboard\n    permissions:\n      contents: read\n      actions: read\n    runs-on:" in workflow
    assert "vars.ENABLE_PUBLIC_PAGES == 'true'" in workflow
    assert "pages: write\n      id-token: write" in workflow.split("  deploy:", 1)[1]
    assert "pages: write\n  id-token: write" not in workflow.split("jobs:", 1)[0]
    assert "actions: read" not in workflow.split("jobs:", 1)[0]


def test_learning_collector_has_no_dependency_on_frozen_track():
    workflow = (ROOT / ".github" / "workflows" / "learning-collect.yml").read_text(encoding="utf-8")
    collector_source = (ROOT / "learning" / "collector" / "__init__.py").read_text(encoding="utf-8")
    assert "schedule:" in workflow and "workflow_dispatch:" in workflow
    assert "\n  push:" not in workflow
    assert "p6-mom-runtime" not in workflow
    assert "p6-mom-cloud-live.yml" not in workflow
    assert "python -m learning.collector --root learning --max-requests 10" in workflow
    assert "permissions:\n      contents: write\n    runs-on:" in workflow
    assert "contents: write" not in workflow.split("jobs:", 1)[0]
    assert "hypotheses_ledger" not in collector_source
    assert "manifest.json" not in collector_source


def test_exploratory_language_is_explicit():
    dashboard = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
    backtest = (ROOT / "learning" / "experiments" / "backtest.py").read_text(encoding="utf-8")
    assert "EXPLORATÓRIO — NÃO É PROVA" in dashboard
    assert "EXPLORATÓRIO — NÃO É PROVA" in backtest


def test_learning_data_and_quality_reports_are_not_ignored():
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "!learning/data/" in ignore
    assert "!learning/data/**" in ignore
    assert "!learning/reports/" in ignore
    assert "!learning/reports/**" in ignore


def test_learning_hypotheses_file_is_empty_and_registry_is_versioned():
    registry = __import__("json").loads((ROOT / "learning" / "experiments" / "registry.json").read_text(encoding="utf-8"))
    assert registry["schema_version"] == 1
    assert registry["experiments"] == []
    hypothesis_lines = (ROOT / "learning" / "hypotheses.jsonl").read_text(encoding="utf-8").splitlines()
    assert not [line for line in hypothesis_lines if line.strip()]
    assert (ROOT / "learning" / "hypotheses.schema.json").is_file()
