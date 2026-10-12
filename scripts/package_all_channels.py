#!/usr/bin/env python3
"""Create one downloadable bundle containing every configured channel ZIP.

The bundle is intentionally fail-closed: it is produced only when the configured
channel count matches --expected-count, every configured URL has COMPLETED state,
and every corresponding completed/<Channel>.zip exists and is a valid ZIP.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
import zipfile
from pathlib import Path
from typing import Any

FIXED_ZIP_TIME = (2020, 1, 1, 0, 0, 0)
CHUNK_SIZE = 1024 * 1024


def normalize_url(value: Any) -> str:
    return str(value or "").strip().rstrip("/").casefold()


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def configured_urls(root: Path) -> list[str]:
    path = root / "channels.txt"
    if not path.is_file():
        return []
    urls: list[str] = []
    seen: set[str] = set()
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        url = raw_line.strip()
        if not url or url.startswith("#"):
            continue
        normalized = normalize_url(url)
        if normalized and normalized not in seen:
            urls.append(url)
            seen.add(normalized)
    return urls


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def _zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=FIXED_ZIP_TIME)
    info.compress_type = zipfile.ZIP_STORED
    info.create_system = 3
    info.external_attr = (0o100644 & 0xFFFF) << 16
    return info


def package_all_channels(
    root: Path,
    output: Path,
    expected_count: int = 20,
) -> Path | None:
    """Return the bundle path when fully ready; otherwise remove stale output."""
    root = Path(root).resolve()
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    def not_ready(reason: str) -> None:
        output.unlink(missing_ok=True)
        print(f"ALL_CHANNEL_BUNDLE_NOT_READY: {reason}", flush=True)

    urls = configured_urls(root)
    if len(urls) != expected_count:
        not_ready(f"expected {expected_count} configured URLs, found {len(urls)}")
        return None

    state = read_json(root / "channel_state.json")
    raw_channels = state.get("channels", {})
    if not isinstance(raw_channels, dict):
        not_ready("channel_state.json has no valid channels object")
        return None

    state_by_url: dict[str, dict[str, Any]] = {}
    for key, record in raw_channels.items():
        if not isinstance(record, dict):
            continue
        state_by_url[normalize_url(key)] = record
        recorded_url = normalize_url(record.get("channel_url"))
        if recorded_url:
            state_by_url[recorded_url] = record

    completed_dir = root / "completed"
    entries: list[tuple[str, dict[str, Any], Path]] = []
    used_zip_names: set[str] = set()

    for url in urls:
        record = state_by_url.get(normalize_url(url))
        if not record:
            not_ready(f"no state entry for {url}")
            return None
        if str(record.get("status", "")).upper() != "COMPLETED":
            not_ready(f"{record.get('channel_name') or url} status is {record.get('status', 'UNKNOWN')}")
            return None

        folder = Path(str(record.get("folder") or record.get("channel_name") or "")).name
        if not folder or folder in {".", ".."}:
            not_ready(f"no valid completed folder recorded for {url}")
            return None
        zip_name = f"{folder}.zip"
        folded_name = zip_name.casefold()
        if folded_name in used_zip_names:
            not_ready(f"duplicate channel ZIP name would collide: {zip_name}")
            return None
        used_zip_names.add(folded_name)
        zip_path = completed_dir / zip_name
        if not zip_path.is_file() or not zipfile.is_zipfile(zip_path):
            not_ready(f"missing or invalid channel ZIP: completed/{zip_name}")
            return None

        entries.append((url, record, zip_path))

    fd, temp_name = tempfile.mkstemp(prefix=f".{output.name}.", suffix=".part", dir=output.parent)
    os.close(fd)
    temp_path = Path(temp_name)
    manifest_channels = []
    try:
        with zipfile.ZipFile(temp_path, "w", allowZip64=True) as bundle:
            for url, record, zip_path in entries:
                arcname = zip_path.name
                info = _zip_info(arcname)
                info.file_size = zip_path.stat().st_size
                digest = hashlib.sha256()
                with zip_path.open("rb") as source, bundle.open(info, "w", force_zip64=True) as target:
                    while chunk := source.read(CHUNK_SIZE):
                        digest.update(chunk)
                        target.write(chunk)
                manifest_channels.append({
                    "channel_name": str(record.get("channel_name") or zip_path.stem),
                    "channel_url": url,
                    "status": "COMPLETED",
                    "zip_file": arcname,
                    "zip_size_bytes": zip_path.stat().st_size,
                    "zip_sha256": digest.hexdigest(),
                    "saved_transcripts": int(record.get("saved_total", 0) or 0),
                    "known_items": int(record.get("known_items", 0) or 0),
                    "no_caption_items": int(record.get("no_caption_items", 0) or 0),
                })

            manifest = {
                "package": output.name,
                "expected_channel_count": expected_count,
                "included_channel_count": len(manifest_channels),
                "completion_rule": "All configured channels have COMPLETED state and a valid individual channel ZIP.",
                "channels": manifest_channels,
            }
            manifest_bytes = (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
            bundle.writestr(_zip_info("all_20_channels_manifest.json"), manifest_bytes)

        if output.exists() and output.read_bytes() == temp_path.read_bytes():
            temp_path.unlink()
        else:
            os.replace(temp_path, output)
    finally:
        temp_path.unlink(missing_ok=True)

    print(f"ALL_CHANNEL_BUNDLE_READY: {output} ({len(entries)} channel ZIPs)", flush=True)
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."), help="Repository root")
    parser.add_argument("--output", type=Path, default=Path("all_20_channel_archives.zip"))
    parser.add_argument("--expected-count", type=int, default=20)
    args = parser.parse_args()
    if args.expected_count < 1:
        parser.error("--expected-count must be positive")
    result = package_all_channels(args.root, args.output, args.expected_count)
    # An incomplete backfill is an expected state, not a workflow failure.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
