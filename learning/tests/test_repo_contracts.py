import re
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
    assert "refs/heads/learning-state:refs/remotes/origin/learning-state" in workflow
    assert 'git -C "$state_dir" push origin "HEAD:refs/heads/learning-state"' in workflow
    assert "GITHUB_REF_NAME" not in workflow
    assert 'git -C "$state_dir" add -- learning/data/ learning/reports/ learning/experiments/' in workflow
    assert 'rsync -a --delete "$state_dir/learning/data/" learning/data/' in workflow
    assert 'rsync -a --delete "$state_dir/learning/reports/" learning/reports/' in workflow
    assert 'cp "$state_dir/learning/experiments/latest_backtest.md" learning/experiments/latest_backtest.md' in workflow
    assert 'cp learning/experiments/latest_backtest.md "$state_dir/learning/experiments/latest_backtest.md"' in workflow
    assert "permissions:\n      contents: write\n    runs-on:" in workflow
    assert "contents: write" not in workflow.split("jobs:", 1)[0]
    assert "hypotheses_ledger" not in collector_source
    assert "manifest.json" not in collector_source


def test_dashboard_restores_learning_state_and_links_to_dedicated_branch():
    workflow = (ROOT / ".github" / "workflows" / "fvt-dashboard.yml").read_text(encoding="utf-8")
    dashboard = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
    feed = __import__("json").loads((ROOT / "dashboard" / "data.json").read_text(encoding="utf-8"))
    assert "refs/heads/learning-state:refs/remotes/origin/learning-state" in workflow
    assert 'state_dir="$RUNNER_TEMP/fvt-learning-state"' in workflow
    assert 'git worktree add --detach "$state_dir" refs/remotes/origin/learning-state' in workflow
    assert 'rsync -a --delete "$state_dir/learning/data/" learning/data/' in workflow
    assert 'rsync -a --delete "$state_dir/learning/reports/" learning/reports/' in workflow
    assert 'cp "$state_dir/learning/experiments/latest_backtest.json" learning/experiments/latest_backtest.json' in workflow
    assert 'blob/learning-state/learning/reports/latest.md' in workflow
    assert feed["learning"]["state_branch"] == "learning-state"
    assert feed["learning"]["latest_report_url"] == "https://github.com/aquinoares/fvt-quant-research/blob/learning-state/learning/reports/latest.md"
    assert "branch de estado:" in dashboard


def test_upstream_attribution_contains_project_link_and_mit_license_text():
    upstream = (ROOT / ".agents" / "skills" / "trader-skill" / "UPSTREAM.md").read_text(encoding="utf-8")
    assert "HKUDS/Vibe-Trading" in upstream
    assert "https://github.com/HKUDS/Vibe-Trading" in upstream
    assert "MIT License" in upstream
    assert "Permission is hereby granted, free of charge" in upstream
    assert 'THE SOFTWARE IS PROVIDED "AS IS"' in upstream

def test_state_branch_docs_and_upstream_license_are_complete():
    upstream = (ROOT / ".agents" / "skills" / "trader-skill" / "UPSTREAM.md").read_text(encoding="utf-8")
    state_doc = (ROOT / "docs" / "LEARNING_STATE_BRANCH.md").read_text(encoding="utf-8")
    login_doc = (ROOT / "docs" / "LOGIN_DECISAO.md").read_text(encoding="utf-8")
    assert "The above copyright notice and this permission notice" in upstream
    assert 'THE SOFTWARE IS PROVIDED "AS IS"' in upstream
    assert "não cria commits em `main`" in state_doc
    assert "`p6-mom-runtime`" in state_doc
    assert "snapshot inicial contém apenas este README de estado e placeholders" in state_doc
    assert "A opção (a) foi escolhida: não ter login por enquanto." in login_doc




def test_learning_collector_uses_fixed_non_cancelling_concurrency_and_safe_push_retries():
    workflow = (ROOT / ".github" / "workflows" / "learning-collect.yml").read_text(encoding="utf-8")
    assert "concurrency:\n  group: learning-public-candle-collector\n  cancel-in-progress: false" in workflow
    assert "for attempt in 1 2 3; do" in workflow
    assert 'git -C "$state_dir" push origin "HEAD:refs/heads/learning-state"' in workflow
    assert 'git -C "$state_dir" fetch --depth=1 origin refs/heads/learning-state' in workflow
    assert 'git -C "$state_dir" reset --hard FETCH_HEAD' in workflow
    assert 'python -m learning.state_persistence --source-root learning --target-root "$state_dir/learning"' in workflow
    assert "failed after 3 attempts" in workflow
    assert not re.search(r"git\\s+[^\\n]*push[^\\n]*(?:--force|(?:^|\\s)-f(?:\\s|$))", workflow)


def test_all_repository_workflows_are_safe_for_pull_requests_from_forks():
    workflow_dir = ROOT / ".github" / "workflows"
    workflow_files = sorted(workflow_dir.glob("*.yml")) + sorted(workflow_dir.glob("*.yaml"))
    assert workflow_files, "nenhum workflow localizado"
    for path in workflow_files:
        content = path.read_text(encoding="utf-8")
        assert not re.search(r"(?m)^\s*pull_request_target\s*:", content), f"pull_request_target encontrado em {path.name}"
        if not re.search(r"(?m)^  pull_request\s*:", content):
            continue
        global_block = content.split("jobs:", 1)[0]
        assert not re.search(r"(?m)^\s+contents:\s*write\s*$", global_block), f"contents: write global em workflow de PR: {path.name}"
        jobs_block = content.split("jobs:", 1)[1]
        job_starts = list(re.finditer(r"(?m)^  ([A-Za-z0-9_-]+):\s*$", jobs_block))
        for index, match in enumerate(job_starts):
            end = job_starts[index + 1].start() if index + 1 < len(job_starts) else len(jobs_block)
            job_name = match.group(1)
            job_text = jobs_block[match.start():end]
            has_write = bool(re.search(r"(?m)^\s+(?:contents|packages|pages|id-token):\s*write\s*$", job_text))
            if has_write:
                assert re.search(r"github\.event_name\s*!=\s*'pull_request'", job_text), (
                    f"job {job_name} com permissão de escrita sem guarda contra pull_request: {path.name}"
                )


def test_dashboard_validates_quality_report_and_never_reuses_stale_metrics():
    workflow = (ROOT / ".github" / "workflows" / "fvt-dashboard.yml").read_text(encoding="utf-8")
    helper = (ROOT / "learning" / "report_feed.py").read_text(encoding="utf-8")
    assert "from learning.report_feed import read_quality_report" in workflow
    assert 'quality_result = read_quality_report(quality_path)' in workflow
    assert 'Path("site/learning-report.json").unlink(missing_ok=True)' in workflow
    assert "Relatório de qualidade ausente na branch learning-state" in helper
    assert "Relatório de qualidade vazio na branch learning-state" in helper
    assert "corrompido em learning-state" in helper
    assert "learningReportView(l)" in (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")

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
