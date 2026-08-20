"""Boundary tests: analysis orchestration must not create workflow actions."""

from pathlib import Path

_SERVICES = Path(__file__).resolve().parents[3] / "app" / "application" / "services"
_ANALYSIS_MODULES = (
    "communication_analysis.py",
    "communication_analysis_workflow.py",
    "communication_ingestion.py",
    "analysis_history.py",
)


def test_analysis_services_do_not_import_workflow_action() -> None:
    """Analyze, persist-after-analyze, and ingestion must not create workflow actions."""
    for name in _ANALYSIS_MODULES:
        source = (_SERVICES / name).read_text(encoding="utf-8")
        assert "WorkflowAction" not in source, f"{name} must not reference WorkflowAction"
        assert "WorkflowActionStatus" not in source
        assert "WorkflowActionType" not in source
