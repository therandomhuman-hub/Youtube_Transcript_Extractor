#!/usr/bin/env python3
"""Finalize the checkpointed archive report after a GitHub Actions collection step."""
from __future__ import annotations

import argparse
import json
import os
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


def render_markdown_report(report: dict[str, Any]) -> str:
    """Render a human-readable per-run summary alongside the machine-readable JSON."""
    def cell(value: Any) -> str:
        return str(value if value is not None else "").replace("|", "\\|").replace("\n", " ").replace("\r", " ")

    started = report.get("run_started_at") or report.get("run_at") or "Unknown"
    finished = report.get("finished_at") or report.get("finalized_at") or "Unknown"
    rows = report.get("results", [])
    if not isinstance(rows, list):
        rows = []
    lines = [
        "# YouTube Transcript Archive — Run Report",
        "",
        f"- **Run ID:** {cell(report.get('run_id') or 'local/manual')}",
        f"- **Run status:** {cell(report.get('run_status') or 'UNKNOWN')}",
        f"- **Workflow step outcome:** {cell(report.get('workflow_step_outcome') or 'UNKNOWN')}",
        f"- **Started (UTC):** {cell(started)}",
        f"- **Finished/finalized (UTC):** {cell(finished)}",
        "",
        "## Run totals",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Configured channels | {int(report.get('configured_channels', 0) or 0)} |",
        f"| Channels checked/reported | {int(report.get('processed_channels', 0) or 0)} |",
        f"| Completed channels | {int(report.get('completed_channels', 0) or 0)} |",
        f"| In-progress channels | {int(report.get('in_progress_channels', 0) or 0)} |",
        f"| Channels with errors | {int(report.get('error_channels', 0) or 0)} |",
        f"| Authentication-blocked channels | {int(report.get('auth_blocked_channels', 0) or 0)} |",
        f"| Channels not reached in this run | {int(report.get('remaining_channels', 0) or 0)} |",
        f"| Transcript attempts in this run | {int(report.get('attempted_transcripts_this_run', 0) or 0)} |",
        f"| Transcripts saved in this run | {int(report.get('saved_transcripts_this_run', 0) or 0)} |",
        f"| No-caption outcomes recorded in this run snapshot | {int(report.get('no_caption_items', 0) or 0)} |",
    ]
    if report.get("failure_reason"):
        lines.extend(["", f"> **Run note:** {cell(report['failure_reason'])}"])
    lines.extend([
        "",
        "## Per-channel results",
        "",
        "| Channel | Status | Saved / known | No captions | Unresolved | Attempted | Folder |",
        "|---|---|---:|---:|---:|---:|---|",
    ])
    for item in rows:
        if not isinstance(item, dict):
            continue
        name = cell(item.get("channel_name") or item.get("channel_url") or "Unknown channel")
        url = str(item.get("channel_url") or "").strip()
        channel_label = f"[{name}]({url})" if url.startswith("https://www.youtube.com/") else name
        folder = cell(item.get("folder") or "")
        saved = int(item.get("saved_total", 0) or 0)
        known = int(item.get("known_items", 0) or 0)
        lines.append(
            f"| {channel_label} | {cell(item.get('status') or 'UNKNOWN')} | "
            f"{saved} / {known} | {int(item.get('no_caption_items', 0) or 0)} | "
            f"{int(item.get('unresolved_items', 0) or 0)} | "
            f"{int(item.get('attempted_this_run', 0) or 0)} | `{folder}` |"
        )
    lines.extend([
        "",
        "## Interpretation",
        "",
        "Run completion and channel backfill completion are different. A channel marked `IN_PROGRESS` still has unresolved items even if the scheduled run itself succeeded.",
        "An explicit `NO_CAPTIONS` outcome is auditable and may satisfy the channel completion rule, but it is not counted as a saved transcript.",
        "",
    ])
    return "\n".join(lines)


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
            "video_count": int(record.get("video_count", 0) or 0),
            "short_count": int(record.get("short_count", 0) or 0),
            "auth_required_count": int(record.get("auth_required_count", 0) or 0),
            "last_checked_at": checked,
        })
        saved_checkpoint_total += int(record.get("saved_this_run", 0) or 0)

    report["workflow_step_outcome"] = args.status
    finalized_at = utc_now()
    report["finalized_at"] = finalized_at
    report["updated_at"] = finalized_at
    report["finished_at"] = finalized_at
    report["partial_channel_checkpoints"] = sorted(checkpoints, key=lambda item: item.get("channel_url", ""))
    report["checkpoint_channel_count"] = len(checkpoints)
    report["checkpoint_saved_this_run_total"] = saved_checkpoint_total
    results = report.get("results", [])
    if not isinstance(results, list):
        results = []
        report["results"] = results
    results = [item for item in results if isinstance(item, dict)]

    # Merge live checkpoints for a channel whose processing was interrupted before
    # process_channel could append its final result. Existing final results win,
    # preventing duplicate counts when a channel completed normally.
    result_urls = {
        str(item.get("channel_url") or "").strip().casefold()
        for item in results if str(item.get("channel_url") or "").strip()
    }
    checkpoint_only = [
        item for item in checkpoints
        if str(item.get("channel_url") or "").strip().casefold() not in result_urls
    ]
    merged_results = results + checkpoint_only
    report["results"] = merged_results
    report["processed_channels"] = len({
        str(item.get("channel_url") or "").strip().casefold()
        for item in merged_results if str(item.get("channel_url") or "").strip()
    })
    report["completed_channels"] = sum(item.get("status") == "COMPLETED" for item in merged_results)
    report["in_progress_channels"] = sum(item.get("status") == "IN_PROGRESS" for item in merged_results)
    report["error_channels"] = sum(item.get("status") in {"ERROR", "SCAN_FAILED"} for item in merged_results)
    auth_blocked = sum(int(item.get("auth_required_count", 0) or 0) > 0 for item in merged_results)
    report["auth_blocked_channels"] = auth_blocked
    configured = int(report.get("configured_channels", report["processed_channels"]) or report["processed_channels"])
    report["remaining_channels"] = max(0, configured - report["processed_channels"])
    report["attempted_transcripts_this_run"] = sum(int(item.get("attempted_this_run", 0) or 0) for item in merged_results)
    report["saved_transcripts_this_run"] = sum(int(item.get("saved_this_run", 0) or 0) for item in merged_results)
    report["no_caption_items"] = sum(int(item.get("no_caption_items", 0) or 0) for item in merged_results)
    if args.status == "success":
        if report["error_channels"] or auth_blocked:
            report["run_status"] = "COMPLETED_WITH_ERRORS" if not auth_blocked else "COMPLETED_WITH_AUTH_BLOCKS"
            report["failure_reason"] = (
                f"Collection process exited successfully, but {report['error_channels']} channel(s) had errors "
                f"and {auth_blocked} channel(s) had authentication challenges."
            )
        else:
            report["run_status"] = "COMPLETED"
            report["failure_reason"] = None
    elif args.status == "cancelled":
        report["run_status"] = "CANCELLED_PARTIAL" if merged_results or checkpoints else "CANCELLED"
        report["failure_reason"] = "The workflow was cancelled. Any committed/checkpointed results are reported; uncommitted runner files may not have been published."
    elif args.status == "skipped":
        report["run_status"] = "PARTIAL_FAILURE" if merged_results or checkpoints else "SKIPPED_BEFORE_COLLECTION"
        report["failure_reason"] = "The collection step was skipped, so no new transcript requests were made in this run."
    elif merged_results or checkpoints:
        report["run_status"] = "PARTIAL_AUTH_BLOCKED" if auth_blocked else "PARTIAL_FAILURE"
        report["failure_reason"] = "The transcript collection step failed or timed out; saved files, manifests, channel state, and available partial checkpoints were preserved."
    else:
        report["run_status"] = "FAILED"
        report["failure_reason"] = "The transcript collection step did not complete and produced no channel checkpoints."
    write_json_atomic(report_path, report)
    markdown = render_markdown_report(report)
    (root / "last_run_report.md").write_text(markdown, encoding="utf-8")
    step_summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary_path:
        with Path(step_summary_path).open("a", encoding="utf-8") as summary_file:
            summary_file.write(markdown + "\n")
    print(json.dumps({
        "run_status": report["run_status"],
        "workflow_step_outcome": args.status,
        "processed_channels": report["processed_channels"],
        "checkpoint_channel_count": report["checkpoint_channel_count"],
        "saved_transcripts_this_run": report["saved_transcripts_this_run"],
        "remaining_channels": report["remaining_channels"],
        "error_channels": report["error_channels"],
        "auth_blocked_channels": report["auth_blocked_channels"],
    }, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
