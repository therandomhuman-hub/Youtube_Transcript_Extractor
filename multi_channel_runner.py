from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import youtube_channel_transcripts as extractor  # noqa: E402


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def safe_json_write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    temp.replace(path)


def read_channels(path: Path) -> list[str]:
    if not path.exists():
        return []
    channels: list[str] = []
    seen: set[str] = set()
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#"):
            continue
        try:
            normalized = extractor.normalize_channel_url(raw)
        except ValueError as exc:
            print(f"Skipping invalid channel entry {raw!r}: {exc}", flush=True)
            continue
        key = normalized.casefold()
        if key not in seen:
            seen.add(key)
            channels.append(normalized)
    return channels


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"channels": {}, "updated_at": utc_now()}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(value, dict) and isinstance(value.get("channels", {}), dict):
            value.setdefault("channels", {})
            return value
    except Exception as exc:
        print(f"Warning: state file could not be read; starting safely: {exc}", flush=True)
    return {"channels": {}, "updated_at": utc_now()}


def locate_channel_folder(root: Path, channel_url: str) -> Path | None:
    preferred = root / extractor.fallback_folder_name(channel_url)
    if (preferred / "transcript_manifest.json").is_file():
        # Validate that a display-name folder belongs to this exact channel.
        # This prevents channels with overlapping names/handles from sharing
        # transcripts accidentally.
        summary = preferred / "collection_summary.txt"
        if summary.is_file():
            try:
                for line in summary.read_text(encoding="utf-8", errors="replace").splitlines():
                    if line.lower().startswith("channel url:"):
                        if line.split(":", 1)[1].strip().casefold() == channel_url.casefold():
                            return preferred
                        break
            except OSError:
                pass
        elif preferred.name.casefold() == extractor.fallback_folder_name(channel_url).casefold():
            # Safe for an interrupted first run in a unique handle-named folder.
            return preferred
    for folder in root.iterdir():
        if not folder.is_dir() or folder.name.startswith("."):
            continue
        summary = folder / "collection_summary.txt"
        manifest = folder / "transcript_manifest.json"
        if manifest.is_file() and summary.is_file():
            try:
                for line in summary.read_text(encoding="utf-8", errors="replace").splitlines():
                    if line.lower().startswith("channel url:") and line.split(":", 1)[1].strip().casefold() == channel_url.casefold():
                        return folder
            except OSError:
                pass
    return None


def manifest_complete(folder: Path) -> tuple[bool, int, int, int]:
    """Return (resolved, valid transcript count, unresolved count, manifest total).

    A valid transcript is resolved. NO_CAPTIONS is also an explicit terminal
    outcome, so caption availability must not keep a channel outside completed/.
    Such items remain in manifests/audits and are not counted as saved transcripts.
    Other failures and missing/corrupt saved files still block completion.
    """
    manifest_path = folder / "transcript_manifest.json"
    if not manifest_path.is_file():
        return False, 0, 0, 0
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return False, 0, 0, 0
    if not isinstance(manifest, dict) or not manifest:
        return False, 0, 0, 0
    saved = 0
    unresolved = 0
    resolved = 0
    for record in manifest.values():
        if not isinstance(record, dict):
            unresolved += 1
            continue
        if record.get("status") == "NO_CAPTIONS":
            resolved += 1
            continue
        filename = str(record.get("filename") or "")
        transcript_path = folder / filename if filename and Path(filename).name == filename else None
        file_ok = bool(transcript_path and transcript_path.is_file() and transcript_path.stat().st_size > 100)
        if record.get("status") == "SAVED" and file_ok:
            saved += 1
            resolved += 1
        else:
            unresolved += 1
    return unresolved == 0 and resolved == len(manifest), saved, unresolved, len(manifest)


def archive_completed_channel(folder: Path, archive_root: Path) -> Path:
    destination = archive_root / folder.name
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.resolve() == folder.resolve():
        return destination
    if destination.exists():
        shutil.copytree(folder, destination, dirs_exist_ok=True)
        shutil.rmtree(folder)
    else:
        shutil.move(str(folder), str(destination))
    return destination


def load_runtime_settings() -> tuple[str, str, set[str], bool, str, str | None]:
    ejs_ready = extractor.ensure_yt_dlp_components()
    runtime_name, runtime_path, warning = extractor.find_js_runtime()
    if runtime_name is None or runtime_path is None:
        raise RuntimeError("No supported JavaScript runtime found. Install Deno 2.3+ or Node.js 22+.")
    remote_components: set[str] = set()
    if not ejs_ready:
        remote_components.add("ejs:github")
    use_whisper = os.getenv("USE_WHISPER_FALLBACK", "false").strip().lower() in {"1", "true", "yes"}
    whisper_model = os.getenv("WHISPER_MODEL", "small").strip() or "small"
    if use_whisper and not extractor.whisper_available():
        print("Whisper fallback requested but faster-whisper is absent; continuing caption-only.", flush=True)
        use_whisper = False
    browser = os.getenv("YOUTUBE_COOKIES_BROWSER") or None
    return runtime_name, runtime_path, remote_components, use_whisper, whisper_model, browser


def process_channel(channel_url: str, root: Path, completed_root: Path, updated_root: Path,
                    state: dict[str, Any], runtime_name: str, runtime_path: str,
                    remote_components: set[str], use_whisper: bool, whisper_model_name: str,
                    browser: str | None, max_items_per_channel: int = 0) -> dict[str, Any]:
    key = channel_url.casefold()
    channel_state = state["channels"].setdefault(key, {})
    folder = locate_channel_folder(root, channel_url)
    archived = locate_channel_folder(completed_root, channel_url)
    # Prefer an active working folder if a prior new upload could not be
    # transcribed. Otherwise update the canonical archive in place, avoiding a
    # full copy of every transcript at each six-hour scan.
    if folder is None and archived is not None:
        folder = archived
    prior_manifest: dict[str, Any] = {}
    if folder and (folder / "transcript_manifest.json").is_file():
        try:
            prior_manifest = json.loads((folder / "transcript_manifest.json").read_text(encoding="utf-8"))
        except Exception:
            pass
    prior_ids = set(prior_manifest) if isinstance(prior_manifest, dict) else set()

    rate_limiter = extractor.RateLimitManager(root / ".youtube_rate_limit_state.json")
    rate_limiter.wait_if_blocked("before channel")
    scan_results: list[dict[str, Any]] = []
    fatal_scan_errors: list[str] = []
    discovery_error: Exception | None = None
    try:
        name, entries, scan_results, fatal_scan_errors = extractor.discover_channel(
            channel_url, browser, runtime_name, runtime_path, remote_components, rate_limiter
        )
    except Exception as exc:
        discovery_error = exc
        name = extractor.fallback_folder_name(channel_url)
        entries = []
        fatal_scan_errors.append(extractor.explain_error(exc))
        print(f"CHANNEL SCAN FAILED: {channel_url}: {extractor.explain_error(exc)}", flush=True)

    if folder is None:
        folder = root / extractor.clean_name(name or extractor.fallback_folder_name(channel_url))
    folder.mkdir(parents=True, exist_ok=True)
    manifest_path = folder / "transcript_manifest.json"
    audit_path = folder / "transcript_audit.csv"
    summary_path = folder / "collection_summary.txt"
    manifest = extractor.load_manifest(manifest_path)
    if discovery_error is not None and not entries:
        entries = extractor.merge_pending_manifest_entries([], manifest, output_dir=folder)
        if not entries:
            return {"channel_url": channel_url, "status": "SCAN_FAILED", "error": extractor.explain_error(discovery_error),
                    "folder": str(folder), "saved_this_run": 0, "last_checked_at": utc_now()}

    extractor.seed_manifest_from_entries(manifest_path, manifest, entries)
    entries = extractor.merge_pending_manifest_entries(entries, manifest, output_dir=folder)
    whisper_instance = None
    if use_whisper:
        try:
            whisper_instance = extractor.load_whisper_model(whisper_model_name)
        except Exception as exc:
            print(f"Whisper unavailable; captions only: {extractor.explain_error(exc)}", flush=True)
            use_whisper = False

    saved_now = 0
    attempted_this_run = 0
    batch_limit_reached = False

    def persist_channel_checkpoint() -> None:
        extractor.atomic_csv_write(audit_path, extractor.manifest_rows(manifest))
        extractor.write_summary(summary_path, channel_name=name or folder.name, channel_url=channel_url,
            entries=entries, scan_results=scan_results, fatal_scan_errors=fatal_scan_errors,
            manifest=manifest, whisper_mode=use_whisper, rate_limiter=rate_limiter)
        _, saved_checkpoint, unresolved_checkpoint, total_checkpoint = manifest_complete(folder)
        try:
            folder_label = folder.relative_to(root).as_posix()
        except ValueError:
            folder_label = str(folder)
        channel_state.update({
            "channel_url": channel_url, "channel_name": name or folder.name,
            "status": "IN_PROGRESS", "folder": folder_label,
            "saved_this_run": saved_now, "attempted_this_run": attempted_this_run,
            "saved_total": saved_checkpoint, "known_items": total_checkpoint,
            "unresolved_items": unresolved_checkpoint,
            "no_caption_items": sum(1 for rec in manifest.values() if isinstance(rec, dict) and rec.get("status") == "NO_CAPTIONS"),
            "batch_limit_reached": batch_limit_reached, "scan_errors": fatal_scan_errors,
            "last_checked_at": utc_now()
        })
        state["updated_at"] = utc_now()
        safe_json_write(root / "channel_state.json", state)

    for index, item in enumerate(entries, start=1):
        existing = extractor.item_has_saved_transcript(item, manifest, folder)
        if existing is not None:
            record = manifest.get(item["id"], {})
            if record.get("status") != "SAVED" or record.get("filename") != existing.name:
                extractor.update_manifest(manifest_path, manifest, item, status="SAVED",
                    source=record.get("source") or "Recovered existing transcript",
                    language=record.get("language") or "", filename=existing.name,
                    message="Manifest reconciled to existing transcript file")
                saved_now += 1
            continue
        if manifest.get(item["id"], {}).get("status") == "NO_CAPTIONS":
            continue
        if max_items_per_channel > 0 and attempted_this_run >= max_items_per_channel:
            batch_limit_reached = True
            print(f"Per-channel batch limit reached ({max_items_per_channel} attempts); remaining items will resume in a later run.", flush=True)
            break
        attempted_this_run += 1
        print(f"[{index}/{len(entries)}] {name or folder.name} — {item.get('title', item['id'])}", flush=True)
        try:
            ok, message = extractor.process_item(
                item, folder, manifest, manifest_path, browser, runtime_name, runtime_path,
                remote_components, use_whisper, whisper_instance, rate_limiter
            )
            if ok:
                saved_now += 1
            else:
                print(f"Transcript not obtained for {item['id']}: {message}", flush=True)
                if extractor.is_auth_required(message):
                    print("YouTube requires authentication / is presenting a bot challenge. Stopping further video requests for this channel in this run; refresh the authorized session rather than attempting to bypass the challenge.", flush=True)
                    break
        except Exception as exc:
            extractor.update_manifest(manifest_path, manifest, item, status="FAILED", message=extractor.explain_error(exc))
            print(f"Item failed {item['id']}: {extractor.explain_error(exc)}", flush=True)
        finally:
            persist_channel_checkpoint()

    extractor.atomic_csv_write(audit_path, extractor.manifest_rows(manifest))
    extractor.write_summary(summary_path, channel_name=name or folder.name, channel_url=channel_url,
        entries=entries, scan_results=scan_results, fatal_scan_errors=fatal_scan_errors,
        manifest=manifest, whisper_mode=use_whisper, rate_limiter=rate_limiter)
    complete, saved_total, unresolved, total = manifest_complete(folder)
    status = "COMPLETED" if complete and not fatal_scan_errors and discovery_error is None else "IN_PROGRESS"
    is_update = bool(prior_ids) and saved_now > 0
    is_archived_folder = folder.parent.resolve() == completed_root.resolve()
    if status == "COMPLETED":
        channel_folder = folder if is_archived_folder else archive_completed_channel(folder, completed_root)
        channel_state.update({"status": "COMPLETED", "folder": str(Path("completed") / channel_folder.name),
                              "completed_at": channel_state.get("completed_at") or utc_now()})
    else:
        # A new unresolved upload means this channel is no longer fully archived.
        # Move the updated manifest back to the working area and remove any stale
        # older archive so the latest scan state cannot be lost on the next run.
        if is_archived_folder:
            working_destination = root / folder.name
            if working_destination.exists():
                shutil.copytree(folder, working_destination, dirs_exist_ok=True)
                shutil.rmtree(folder)
            else:
                shutil.move(str(folder), str(working_destination))
            folder = working_destination
        elif archived is not None and archived.exists():
            shutil.rmtree(archived)
        channel_folder = folder
        channel_state.update({"status": "IN_PROGRESS", "folder": folder.name})

    if is_update:
        updated_channel_folder = updated_root / channel_folder.name
        updated_channel_folder.mkdir(parents=True, exist_ok=True)
        update_log = updated_channel_folder / "new_transcripts.json"
        records: list[dict[str, Any]] = []
        if update_log.exists():
            try:
                records = json.loads(update_log.read_text(encoding="utf-8"))
            except Exception:
                records = []
        new_ids = [item["id"] for item in entries if item["id"] not in prior_ids and manifest.get(item["id"], {}).get("status") == "SAVED"]
        records.append({"checked_at": utc_now(), "channel_url": channel_url, "new_transcript_count": len(new_ids), "new_video_ids": new_ids})
        safe_json_write(update_log, records)
        for video_id in new_ids:
            filename = str(manifest[video_id].get("filename", ""))
            if filename and (channel_folder / filename).is_file():
                shutil.copy2(channel_folder / filename, updated_channel_folder / filename)
    manifest_records = [rec for rec in manifest.values() if isinstance(rec, dict)]
    no_caption_count = sum(1 for rec in manifest_records if rec.get("status") == "NO_CAPTIONS")
    # Inventory totals must reflect the durable manifest, not only the subset
    # returned by the most recent channel-tab scan or selected for this run.
    video_count = sum(1 for rec in manifest_records if str(rec.get("type", "VIDEO")).upper() != "SHORT")
    short_count = sum(1 for rec in manifest_records if str(rec.get("type", "")).upper() == "SHORT")
    result = {"channel_url": channel_url, "channel_name": name or folder.name, "status": status,
              "saved_this_run": saved_now, "attempted_this_run": attempted_this_run,
              "batch_limit_reached": batch_limit_reached, "saved_total": saved_total, "known_items": total,
              "video_count": video_count,
              "short_count": short_count,
              "auth_required_count": sum(1 for item in manifest.values() if item.get("status") == "AUTH_REQUIRED"),
              "no_caption_items": no_caption_count, "resolved_without_transcript": no_caption_count,
              "unresolved_items": unresolved, "scan_errors": fatal_scan_errors,
              "folder": str(channel_folder.relative_to(root)) if channel_folder.is_relative_to(root) else str(channel_folder),
              "last_checked_at": utc_now()}
    channel_state.update(result)
    return result


def make_run_report(run_started_at: str, configured_channels: int, results: list[dict[str, Any]],
                    run_status: str, finished_at: str | None = None) -> dict[str, Any]:
    return {
        "run_id": os.getenv("GITHUB_RUN_ID") or None,
        "run_number": os.getenv("GITHUB_RUN_NUMBER") or None,
        "run_status": run_status, "run_at": run_started_at, "run_started_at": run_started_at,
        "updated_at": utc_now(), "finished_at": finished_at,
        "configured_channels": configured_channels, "processed_channels": len(results),
        "remaining_channels": max(0, configured_channels - len(results)),
        "completed_channels": sum(x.get("status") == "COMPLETED" for x in results),
        "in_progress_channels": sum(x.get("status") == "IN_PROGRESS" for x in results),
        "error_channels": sum(x.get("status") in {"ERROR", "SCAN_FAILED"} for x in results),
        "saved_transcripts_this_run": sum(int(x.get("saved_this_run", 0) or 0) for x in results),
        "no_caption_items": sum(int(x.get("no_caption_items", 0) or 0) for x in results),
        "results": results
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Scheduled multi-channel YouTube transcript archive")
    parser.add_argument("--channels-file", default="channels.txt")
    parser.add_argument("--output-dir", default=str(ROOT))
    parser.add_argument("--max-channels", type=int, default=0, help="Optional test limit; 0 processes all")
    parser.add_argument("--max-items-per-channel", type=int,
                        default=int(os.getenv("MAX_ITEMS_PER_CHANNEL", "0") or "0"),
                        help="Max transcript attempts per channel per run; 0 means unlimited")
    args = parser.parse_args()
    if args.max_channels < 0:
        parser.error("--max-channels must be non-negative")
    if args.max_items_per_channel < 0:
        parser.error("--max-items-per-channel must be non-negative")
    root = Path(args.output_dir).resolve()
    channels_file = Path(args.channels_file)
    if not channels_file.is_absolute():
        # Relative config paths are resolved from the caller's working directory,
        # independently of --output-dir (which may not exist yet).
        channels_file = Path.cwd() / channels_file
    channels = read_channels(channels_file)
    if args.max_channels > 0:
        channels = channels[:args.max_channels]
    print(f"Loaded {len(channels)} unique channel(s) from {channels_file}", flush=True)
    if not channels:
        print("No valid channels configured. Add one URL per line in channels.txt.", flush=True)
        return 2
    completed_root, updated_root = root / "completed", root / "updated"
    completed_root.mkdir(parents=True, exist_ok=True)
    updated_root.mkdir(parents=True, exist_ok=True)
    state_path = root / "channel_state.json"
    report_path = root / "last_run_report.json"
    state = load_state(state_path)
    run_started_at = utc_now()
    results: list[dict[str, Any]] = []
    safe_json_write(report_path, make_run_report(run_started_at, len(channels), results, "RUNNING"))
    try:
        runtime_name, runtime_path, remote_components, use_whisper, whisper_model_name, browser = load_runtime_settings()
    except Exception as exc:
        print(f"Cannot start extractor: {exc}", flush=True)
        safe_json_write(report_path, make_run_report(run_started_at, len(channels), results, "STARTUP_FAILED", utc_now()))
        return 2
    for index, channel_url in enumerate(channels, start=1):
        print("\n" + "=" * 76 + f"\nCHANNEL {index}/{len(channels)}: {channel_url}", flush=True)
        try:
            result = process_channel(channel_url, root, completed_root, updated_root, state, runtime_name,
                runtime_path, remote_components, use_whisper, whisper_model_name, browser,
                args.max_items_per_channel)
        except KeyboardInterrupt:
            print("Interrupted; transcripts and manifests are preserved for the next run.", flush=True)
            safe_json_write(report_path, make_run_report(run_started_at, len(channels), results, "INTERRUPTED", utc_now()))
            break
        except Exception as exc:
            traceback.print_exc()
            result = {"channel_url": channel_url, "status": "ERROR", "error": extractor.explain_error(exc), "last_checked_at": utc_now()}
        results.append(result)
        state["channels"][channel_url.casefold()] = {**state["channels"].get(channel_url.casefold(), {}), **result}
        state["updated_at"] = utc_now()
        safe_json_write(state_path, state)
        safe_json_write(report_path, make_run_report(run_started_at, len(channels), results, "RUNNING"))
        print(json.dumps(result, ensure_ascii=False), flush=True)
    auth_blocked = sum(int(x.get("auth_required_count", 0) or 0) > 0 for x in results)
    errors = sum(x.get("status") in {"ERROR", "SCAN_FAILED"} for x in results)
    final_status = "PARTIAL_AUTH_BLOCKED" if auth_blocked else ("FAILED" if results and errors == len(results) else "COMPLETED")
    safe_json_write(report_path, make_run_report(run_started_at, len(channels), results, final_status, utc_now()))
    print("Run summary: " + json.dumps({"processed": len(results),
        "remaining": max(0, len(channels) - len(results)),
        "completed": sum(x.get("status") == "COMPLETED" for x in results),
        "in_progress": sum(x.get("status") == "IN_PROGRESS" for x in results),
        "auth_blocked_channels": auth_blocked, "errors": errors}), flush=True)
    if auth_blocked:
        return 1
    return 1 if results and errors == len(results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
