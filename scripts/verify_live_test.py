from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit a completed single-channel live test run")
    parser.add_argument("--report", default="live_test_output/last_run_report.json")
    parser.add_argument("--expected-videos", type=int, default=9)
    parser.add_argument("--output", default="live_test_output/ISAACVERSE_LIVE_TEST_AUDIT.md")
    args = parser.parse_args()
    source = Path(args.report)
    if not source.is_file():
        raise SystemExit(f"Missing runner report: {source}")
    payload = json.loads(source.read_text(encoding="utf-8"))
    results = payload.get("results") or []
    match = next((x for x in results if "isaacverse" in str(x.get("channel_url", "")).lower()), None)
    if match is None and results:
        match = results[0]
    if not match:
        raise SystemExit("No channel result was present in last_run_report.json")
    video_count = int(match.get("video_count", 0))
    short_count = int(match.get("short_count", 0))
    saved_total = int(match.get("saved_total", 0))
    known = int(match.get("known_items", 0))
    unresolved = int(match.get("unresolved_items", max(0, known - saved_total)))
    folder = Path(str(match.get("folder", "")))
    if not folder.is_absolute():
        folder = Path.cwd() / folder
    manifest_path = folder / "transcript_manifest.json"
    manifest = {}
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    rows = []
    for video_id, item in manifest.items():
        if not isinstance(item, dict):
            continue
        rows.append((str(item.get("type", "VIDEO")), str(item.get("title", video_id)).replace("|", "\\|"),
                     video_id, str(item.get("status", "UNKNOWN")), str(item.get("language", "")),
                     str(item.get("filename", "")).replace("|", "\\|")))
    rows.sort(key=lambda row: (row[0], row[2]))
    video_status = "PASS" if video_count == args.expected_videos else "MISMATCH"
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    lines = ["# Isaacverse live transcript test", "", f"- Test time (UTC): {now}",
             f"- Channel: {match.get('channel_url', 'https://www.youtube.com/@isaacverse')}",
             f"- Overall run status: **{match.get('status', 'UNKNOWN')}**",
             f"- Regular video count: **{video_count}** (expected {args.expected_videos}: **{video_status}**)",
             f"- Shorts count: **{short_count}**", f"- Total unique manifest items: **{known}**",
             f"- Transcripts saved: **{saved_total}/{known}**", f"- Unresolved items: **{unresolved}**",
             f"- Scan errors: {json.dumps(match.get('scan_errors', []), ensure_ascii=False)}",
             f"- Output folder: `{folder}`", "", "## Per-video transcript audit", "",
             "| Type | Video title | Video ID | Status | Language | Transcript filename |",
             "|---|---|---|---|---|---|"]
    lines.extend(f"| {kind} | {title} | `{vid}` | {status} | {language} | `{filename}` |"
                 for kind, title, vid, status, language, filename in rows)
    if not rows:
        lines.append("| — | No manifest entries found | — | — | — | — |")
    lines += ["", "## Interpretation", "",
              (f"The live enumeration returned exactly {args.expected_videos} regular videos." if video_count == args.expected_videos
               else f"The live enumeration returned {video_count} regular videos, not {args.expected_videos}. Shorts are counted separately; inspect the per-video table and scan status before concluding the channel's current total."),
              "A transcript counts as saved only when the runner records `SAVED` and finds a valid transcript file. Private, deleted, restricted, or captionless videos can remain unresolved; a count match alone is not proof that every transcript was extracted.", ""]
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines), encoding="utf-8")
    print(f"LIVE_TEST_CHANNEL={match.get('channel_url')}")
    print(f"LIVE_TEST_STATUS={match.get('status')}")
    print(f"LIVE_TEST_REGULAR_VIDEOS={video_count}; EXPECTED={args.expected_videos}; CHECK={video_status}")
    print(f"LIVE_TEST_SHORTS={short_count}; UNIQUE_ITEMS={known}")
    print(f"LIVE_TEST_TRANSCRIPTS_SAVED={saved_total}/{known}; UNRESOLVED={unresolved}")
    print(f"LIVE_TEST_AUDIT_FILE={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
