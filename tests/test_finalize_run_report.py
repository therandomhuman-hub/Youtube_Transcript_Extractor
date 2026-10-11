import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import finalize_run_report


def _write_inputs(root: Path, report: dict, channels: dict | None = None) -> None:
    (root / "last_run_report.json").write_text(json.dumps(report), encoding="utf-8")
    (root / "channel_state.json").write_text(json.dumps({"channels": channels or {}}), encoding="utf-8")


def _finalize(root: Path, monkeypatch, status: str) -> dict:
    monkeypatch.setattr(sys, "argv", [
        "finalize_run_report.py", "--status", status, "--root", str(root)
    ])
    assert finalize_run_report.main() == 0
    return json.loads((root / "last_run_report.json").read_text(encoding="utf-8"))


def test_successful_workflow_with_channel_error_is_not_reported_clean(tmp_path, monkeypatch):
    _write_inputs(tmp_path, {
        "run_started_at": "2026-10-11T00:00:00+00:00",
        "configured_channels": 1,
        "results": [{
            "channel_url": "https://www.youtube.com/@Example",
            "channel_name": "Example",
            "status": "ERROR",
            "saved_this_run": 2,
            "attempted_this_run": 3,
            "auth_required_count": 0,
            "no_caption_items": 0,
        }],
    })

    report = _finalize(tmp_path, monkeypatch, "success")

    assert report["run_status"] == "COMPLETED_WITH_ERRORS"
    assert report["error_channels"] == 1
    assert report["processed_channels"] == 1
    assert report["remaining_channels"] == 0
    assert report["finished_at"]


def test_auth_blocked_channel_is_surfaced_even_when_runner_step_succeeds(tmp_path, monkeypatch):
    _write_inputs(tmp_path, {
        "run_started_at": "2026-10-11T00:00:00+00:00",
        "configured_channels": 1,
        "results": [{
            "channel_url": "https://www.youtube.com/@Example",
            "channel_name": "Example",
            "status": "IN_PROGRESS",
            "saved_this_run": 1,
            "auth_required_count": 1,
        }],
    })

    report = _finalize(tmp_path, monkeypatch, "success")

    assert report["run_status"] == "COMPLETED_WITH_AUTH_BLOCKS"
    assert report["auth_blocked_channels"] == 1
    assert "authentication challenges" in report["failure_reason"]


def test_cancelled_run_includes_active_channel_checkpoint_without_double_counting(tmp_path, monkeypatch):
    _write_inputs(tmp_path, {
        "run_started_at": "2026-10-11T00:00:00+00:00",
        "configured_channels": 2,
        "results": [{
            "channel_url": "https://www.youtube.com/@A",
            "channel_name": "A",
            "status": "COMPLETED",
            "saved_this_run": 2,
            "no_caption_items": 0,
            "last_checked_at": "2026-10-11T00:03:00+00:00",
        }],
    }, {
        "https://www.youtube.com/@a": {
            "channel_url": "https://www.youtube.com/@A",
            "channel_name": "A",
            "status": "COMPLETED",
            "saved_this_run": 2,
            "known_items": 2,
            "last_checked_at": "2026-10-11T00:03:00+00:00",
        },
        "https://www.youtube.com/@b": {
            "channel_url": "https://www.youtube.com/@B",
            "channel_name": "B",
            "status": "IN_PROGRESS",
            "saved_this_run": 3,
            "known_items": 8,
            "video_count": 7,
            "short_count": 1,
            "auth_required_count": 0,
            "no_caption_items": 0,
            "unresolved_items": 5,
            "last_checked_at": "2026-10-11T00:04:00+00:00",
        },
    })

    report = _finalize(tmp_path, monkeypatch, "cancelled")

    assert report["run_status"] == "CANCELLED_PARTIAL"
    assert report["processed_channels"] == 2
    assert report["completed_channels"] == 1
    assert report["in_progress_channels"] == 1
    assert report["remaining_channels"] == 0
    assert report["saved_transcripts_this_run"] == 5
    assert report["checkpoint_channel_count"] == 2
    assert len(report["partial_channel_checkpoints"]) == 2


def test_failed_run_without_any_checkpoint_is_reported_failed(tmp_path, monkeypatch):
    _write_inputs(tmp_path, {
        "run_started_at": "2026-10-11T00:00:00+00:00",
        "configured_channels": 18,
        "results": [],
    })

    report = _finalize(tmp_path, monkeypatch, "failure")

    assert report["run_status"] == "FAILED"
    assert report["processed_channels"] == 0
    assert report["remaining_channels"] == 18

def test_successful_run_with_remaining_backfill_is_not_reported_as_fully_complete(tmp_path, monkeypatch):
    _write_inputs(tmp_path, {
        "run_started_at": "2026-10-11T00:00:00+00:00",
        "configured_channels": 2,
        "results": [
            {
                "channel_url": "https://www.youtube.com/@A",
                "channel_name": "A",
                "status": "COMPLETED",
                "saved_this_run": 0,
                "attempted_this_run": 0,
                "auth_required_count": 0,
                "unresolved_items": 0,
            },
            {
                "channel_url": "https://www.youtube.com/@B",
                "channel_name": "B",
                "status": "IN_PROGRESS",
                "saved_this_run": 12,
                "attempted_this_run": 12,
                "auth_required_count": 0,
                "unresolved_items": 40,
            },
        ],
    })

    report = _finalize(tmp_path, monkeypatch, "success")

    assert report["run_status"] == "RUN_SUCCEEDED_BACKFILL_INCOMPLETE"
    assert report["completed_channels"] == 1
    assert report["in_progress_channels"] == 1
    assert report["remaining_channels"] == 0
    assert "full backfill is not complete" in report["failure_reason"]

