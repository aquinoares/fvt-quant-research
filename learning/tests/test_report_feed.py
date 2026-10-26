import json
from pathlib import Path

import pytest

from learning.report_feed import read_quality_report

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "learning" / "tests" / "fixtures"


def test_missing_report_has_unknown_metrics_and_explicit_learning_state_reason(tmp_path):
    result = read_quality_report(tmp_path / "learning-state" / "latest.json")
    learning = result["learning"]

    assert result["report"] is None
    assert learning["report_available"] is False
    assert learning["candle_count_1m"] is None
    assert learning["coverage_percent"] is None
    assert learning["new_candles"] is None
    assert learning["quality_report_reason"] is not None
    assert "ausente na branch learning-state" in learning["quality_report_reason"]
    assert learning["latest_report_url"] is None


def test_valid_quality_report_exposes_only_source_backed_numbers():
    result = read_quality_report(FIXTURES / "quality-report-valid.json")
    learning = result["learning"]

    assert result["report"] is not None
    assert learning["report_available"] is True
    assert learning["quality_report_reason"] is None
    assert learning["candle_count_1m"] == 12345
    assert learning["coverage_percent"] == 99.5
    assert learning["coverage_minutes_present"] == 12345
    assert learning["coverage_minutes_expected"] == 12360
    assert learning["new_candles"] == 60
    assert learning["duplicates_removed"] == 1
    assert learning["latest_report_url"].endswith("/blob/learning-state/learning/reports/latest.md")
    assert learning["latest_run_url"].endswith("/40220123456")


@pytest.mark.parametrize(
    ("filename", "reason_fragment"),
    [
        ("quality-report-empty.txt", "Relatório de qualidade vazio"),
        ("quality-report-corrupt.json", "corrompido"),
    ],
)
def test_empty_or_corrupt_report_disables_metrics(filename, reason_fragment):
    result = read_quality_report(FIXTURES / filename)
    learning = result["learning"]

    assert result["report"] is None
    assert learning["report_available"] is False
    assert learning["candle_count_1m"] is None
    assert learning["coverage_percent"] is None
    assert learning["coverage_minutes_present"] is None
    assert learning["quality_report_reason"] is not None
    assert reason_fragment in learning["quality_report_reason"]
    assert learning["latest_report_url"] is None


def test_invalid_numeric_field_marks_report_corrupt(tmp_path):
    payload = json.loads((FIXTURES / "quality-report-valid.json").read_text(encoding="utf-8"))
    payload["candle_count"] = "12345"
    path = tmp_path / "latest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    result = read_quality_report(path)
    assert result["report"] is None
    assert result["learning"]["report_available"] is False
    assert result["learning"]["candle_count_1m"] is None
    assert "candle_count inválido" in result["learning"]["quality_report_reason"]
