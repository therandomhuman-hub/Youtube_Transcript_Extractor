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
    assert "python scripts/package_all_channels.py --root . --expected-count 20" in workflow
    assert "all-20-channel-archives-${{ github.run_id }}" in workflow
    assert "${{ runner.temp }}/all_20_channel_archives.zip" in workflow
    assert "if-no-files-found: ignore" in workflow
    assert "completed/*.zip" in workflow
    assert "last_run_report.md" in workflow
    assert 'python scripts/finalize_run_report.py --status "$ARCHIVE_STEP_OUTCOME" || true' not in workflow
    assert "git push origin HEAD:main" in workflow
    assert "git push --force" not in workflow


def test_archive_collection_is_schedule_or_manual_only():
    workflow = (ROOT / ".github" / "workflows" / "transcript-archive.yml").read_text(encoding="utf-8")
    triggers = workflow.split("permissions:", 1)[0]

    # Source changes should run the fast validation workflow, not start a costly
    # full-channel collection that competes with the scheduled backfill.
    assert "\n  push:" not in triggers
    assert "  schedule:" in triggers
    assert "  workflow_dispatch:" in triggers
