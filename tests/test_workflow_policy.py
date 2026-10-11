from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_archive_workflow_has_four_daily_runs_and_does_not_cancel_active_work():
    workflow = (ROOT / ".github" / "workflows" / "transcript-archive.yml").read_text(encoding="utf-8")

    assert 'cron: "17 0,6,12,18 * * *"' in workflow
    assert "cancel-in-progress: false" in workflow
    assert "timeout-minutes: 340" in workflow
    assert 'default: "12"' in workflow
    assert "github.event.inputs.max_items_per_channel || '12'" in workflow


def test_archive_workflow_reports_failures_and_publishes_zips():
    workflow = (ROOT / ".github" / "workflows" / "transcript-archive.yml").read_text(encoding="utf-8")

    assert "python scripts/finalize_run_report.py --status \"$ARCHIVE_STEP_OUTCOME\"" in workflow
    assert "python scripts/package_completed.py --root ." in workflow
    assert "completed/*.zip" in workflow
    assert "last_run_report.md" in workflow
    assert 'python scripts/finalize_run_report.py --status "$ARCHIVE_STEP_OUTCOME" || true' not in workflow
    assert "git push origin HEAD:main" in workflow
    assert "git push --force" not in workflow


def test_report_only_or_workflow_only_edits_do_not_trigger_full_collector():
    workflow = (ROOT / ".github" / "workflows" / "transcript-archive.yml").read_text(encoding="utf-8")
    push_paths = workflow.split("  schedule:", 1)[0]

    assert '"multi_channel_runner.py"' in push_paths
    assert '"youtube_channel_transcripts.py"' in push_paths
    assert '".github/workflows/transcript-archive.yml"' not in push_paths
    assert '"scripts/finalize_run_report.py"' not in push_paths
