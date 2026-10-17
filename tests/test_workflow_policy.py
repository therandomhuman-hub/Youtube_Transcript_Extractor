from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]


def test_no_workflow_has_scheduled_trigger():
    workflow_dir = ROOT / ".github" / "workflows"
    workflow_files = sorted(workflow_dir.glob("*.yml"))
    assert workflow_files, "Expected GitHub Actions workflow files to exist."

    scheduled = [
        path.name
        for path in workflow_files
        if re.search(r"(?m)^  schedule:\s*$", path.read_text(encoding="utf-8"))
    ]
    assert not scheduled, f"Scheduled workflows must remain disabled: {scheduled}"


def test_archive_workflow_is_manual_only_and_does_not_cancel_active_work():
    workflow = (ROOT / ".github" / "workflows" / "transcript-archive.yml").read_text(encoding="utf-8")
    triggers = workflow.split("permissions:", 1)[0]

    assert "\n  schedule:" not in triggers
    assert "\n  push:" not in triggers
    assert "\n  workflow_dispatch:" in triggers
    assert "cancel-in-progress: false" in workflow
    assert "timeout-minutes: 340" in workflow
    assert 'default: "0"' in workflow
    assert "github.event.inputs.max_items_per_channel || '0'" in workflow
    assert "channel_workers:" in workflow
    assert 'default: "3"' in workflow
    assert "github.event.inputs.channel_workers || '3'" in workflow
    assert "CHANNEL_WORKERS_INPUT:" in workflow
    assert '--channel-workers "$CHANNEL_WORKERS_INPUT"' in workflow


def test_archive_workflow_reports_failures_and_publishes_zips():
    workflow = (ROOT / ".github" / "workflows" / "transcript-archive.yml").read_text(encoding="utf-8")

    assert "python scripts/finalize_run_report.py --status \"$ARCHIVE_STEP_OUTCOME\"" in workflow
    assert "python scripts/package_completed.py --root ." in workflow
    assert "python scripts/package_all_channels.py --root . --expected-count 20" in workflow
    assert "all-20-channel-archives-${{ github.run_id }}" in workflow
    assert "${{ runner.temp }}/all_20_channel_archives.zip" in workflow
    assert "if-no-files-found: ignore" in workflow
    assert "\n  bundle:" not in workflow
    assert "      - name: Package combined ZIP when all 20 channels are complete" in workflow
    assert "      - name: Upload combined ZIP when ready" in workflow
    assert workflow.index("python scripts/package_all_channels.py") > workflow.index("python scripts/package_completed.py")
    assert workflow.index("python scripts/package_all_channels.py") < workflow.index("      - name: Upload run report and channel state")
    assert workflow.index("      - name: Upload combined ZIP when ready") < workflow.index("      - name: Upload run report and channel state")
    assert "completed/*.zip" in workflow
    assert "last_run_report.md" in workflow
    assert 'python scripts/finalize_run_report.py --status "$ARCHIVE_STEP_OUTCOME" || true' not in workflow
    assert "git push origin HEAD:main" in workflow
    assert "git push --force" not in workflow


def test_archive_watchdog_is_manual_only_and_keeps_safe_dispatch_logic():
    watchdog = (ROOT / ".github" / "workflows" / "archive-watchdog.yml").read_text(encoding="utf-8")
    triggers = watchdog.split("permissions:", 1)[0]

    assert "\n  schedule:" not in triggers
    assert "\n  workflow_dispatch:" in triggers
    assert "actions: write" in watchdog
    assert "thresholdHours = 5" in watchdog
    assert "activeStatuses" in watchdog
    assert "github.rest.actions.listWorkflowRuns" in watchdog
    assert "github.rest.actions.createWorkflowDispatch" in watchdog
    assert "workflow_id: workflowId" in watchdog
    assert 'max_items_per_channel: "0"' in watchdog
    assert 'channel_workers: "3"' in watchdog
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
