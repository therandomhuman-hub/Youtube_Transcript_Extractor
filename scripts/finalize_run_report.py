#!/usr/bin/env python3
"""Finalize the checkpointed archive report after a GitHub Actions collection step."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback


def write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temp.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--status", choices=("success", "failure", "cancelled", "skipped"), required=True)
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args()
    root = args.root.resolve()
    report_path = root / "last_run_report.json"
    state_path = root / "channel_state.json"
    report = read_json(report_path, {})
    if not isinstance(report, dict):
        report = {}
    state = read_json(state_path, {})
    channels = state.get("channels", {}) if isinstance(state, dict) else {}
    if not isinstance(channels, dict):
        channels = {}

    started_at = str(report.get("run_started_at") or report.get("run_at") or "")
    checkpoints = []
    saved_checkpoint_total = 0
    for key, record in channels.items():
        if not isinstance(record, dict):
            continue
        checked = str(record.get("last_checked_at") or "")
        if started_at and checked and checked < started_at:
            continue
        if not checked:
            continue
        checkpoints.append({
            "channel_url": record.get("channel_url") or key,
            "channel_name": record.get("channel_name") or "",
            "status": record.get("status") or "UNKNOWN",
            "folder": record.get("folder") or "",
            "saved_this_run": int(record.get("saved_this_run", 0) or 0),
            "attempted_this_run": int(record.get("attempted_this_run", 0) or 0),
            "saved_total": int(record.get("saved_total", 0) or 0),
            "known_items": int(record.get("known_items", 0) or 0),
            "unresolved_items": int(record.get("unresolved_items", 0) or 0),
            "no_caption_items": int(record.get("no_caption_items", 0) or 0),
            "last_checked_at": checked,
        })
        saved_checkpoint_total += int(record.get("saved_this_run", 0) or 0)

    report["workflow_step_outcome"] = args.status
    report["finalized_at"] = utc_now()
    report["partial_channel_checkpoints"] = sorted(checkpoints, key=lambda item: item.get("channel_url", ""))
    report["checkpoint_channel_count"] = len(checkpoints)
    report["checkpoint_saved_this_run_total"] = saved_checkpoint_total
    results = report.get("results", [])
    if not isinstance(results, list):
        results = []
        report["results"] = results
    report["processed_channels"] = len(results)
    report["completed_channels"] = sum(isinstance(item, dict) and item.get("status") == "COMPLETED" for item in results)
    report["in_progress_channels"] = sum(isinstance(item, dict) and item.get("status") == "IN_PROGRESS" for item in results)
    report["error_channels"] = sum(isinstance(item, dict) and item.get("status") in {"ERROR", "SCAN_FAILED"} for item in results)
    configured = int(report.get("configured_channels", len(results)) or len(results))
    report["remaining_channels"] = max(0, configured - len(results))
    if args.status == "success":
        report["run_status"] = "COMPLETED"
        report["failure_reason"] = None
    elif results or checkpoints:
        report["run_status"] = "PARTIAL_FAILURE"
        report["failure_reason"] = "The transcript collection step failed or timed out; saved files, manifests, channel state, and partial checkpoints were preserved."
    else:
        report["run_status"] = "FAILED"
        report["failure_reason"] = "The transcript collection step did not complete and produced no channel checkpoints."
    write_json_atomic(report_path, report)
    print(json.dumps({
        "run_status": report["run_status"],
        "workflow_step_outcome": args.status,
        "processed_channels": report["processed_channels"],
        "checkpoint_channel_count": report["checkpoint_channel_count"],
        "partial_saved_transcripts": saved_checkpoint_total,
        "remaining_channels": report["remaining_channels"],
    }, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
