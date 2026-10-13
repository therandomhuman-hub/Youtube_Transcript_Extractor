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
    assert "\n  bundle:\n    name: Bundle all 20 channels when complete\n    needs: collect\n    if: always()" in workflow
    assert "timeout-minutes: 90" in workflow
    assert workflow.index("python scripts/package_all_channels.py") > workflow.index("\n  bundle:")
    assert "completed/*.zip" in workflow
    assert "last_run_report.md" in workflow
    assert 'python scripts/finalize_run_report.py --status "$ARCHIVE_STEP_OUTCOME" || true' not in workflow
    assert "git push origin HEAD:main" in workflow
    assert "git push --force" not in workflow


def test_archive_collection_push_trigger_is_limited_to_recovery_relevant_files():
    workflow = (ROOT / ".github" / "workflows" / "transcript-archive.yml").read_text(encoding="utf-8")
    triggers = workflow.split("permissions:", 1)[0]

    # Changes to collector configuration/code recover the archive immediately,
    # while transcript/state commits cannot recursively launch another collector.
    assert "\\n  push:" in triggers
    assert "branches: [main]" in triggers
    for path in (
        '"channels.txt"',
        '".github/workflows/transcript-archive.yml"',
        '"multi_channel_runner.py"',
        '"youtube_channel_transcripts.py"',
        '"scripts/finalize_run_report.py"',
        '"scripts/package_completed.py"',
        '"scripts/package_all_channels.py"',
        '"requirements.txt"',
    ):
        assert path in triggers
    assert '"channel_state.json"' not in triggers
    assert '"last_run_report.json"' not in triggers
    assert '"completed/**"' not in triggers
    assert "  schedule:" in triggers
    assert "  workflow_dispatch:" in triggers


def test_archive_watchdog_recovers_missed_schedule_without_duplicate_runs():
    watchdog = (ROOT / ".github" / "workflows" / "archive-watchdog.yml").read_text(encoding="utf-8")

    assert 'cron: "43 * * * *"' in watchdog
    assert "actions: write" in watchdog
    assert "thresholdHours = 8" in watchdog
    assert "activeStatuses" in watchdog
    assert "github.rest.actions.listWorkflowRuns" in watchdog
    assert "github.rest.actions.createWorkflowDispatch" in watchdog
    assert 'workflow_id: workflowId' in watchdog
    assert 'max_items_per_channel: "12"' in watchdog
    assert "cancel-in-progress: false" in watchdog


def test_channel_list_has_exactly_twenty_unique_channels_including_new_requests():
    channels_file = ROOT / "channels.txt"
    urls = [
        line.strip()
        for line in channels_file.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    normalized = [url.rstrip("/").casefold() for url in urls]

    assert len(urls) == 20
    assert len(set(normalized)) == 20
    assert "https://www.youtube.com/@alexpdfbusiness" in normalized
    assert "https://www.youtube.com/@iammoneyguy" in normalized
