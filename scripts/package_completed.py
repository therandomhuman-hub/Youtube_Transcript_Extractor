#!/usr/bin/env python3
"""Build deterministic ZIP snapshots for completed channel archives.

The ZIPs live beside their source folders, e.g. completed/Isaac.zip contains
Isaac/<transcripts and manifest files>. Temporary files and symlinks are ignored.
"""
from __future__ import annotations

import argparse
import os
import tempfile
import zipfile
from pathlib import Path


FIXED_ZIP_TIME = (2020, 1, 1, 0, 0, 0)


def package_completed(root: Path) -> list[Path]:
    root = Path(root).resolve()
    completed = root / "completed"
    if not completed.is_dir():
        return []

    generated: list[Path] = []
    for channel_dir in sorted(
        (p for p in completed.iterdir() if p.is_dir() and not p.is_symlink() and not p.name.startswith(".")),
        key=lambda p: p.name.casefold(),
    ):
        source_files = sorted(
            (
                p for p in channel_dir.rglob("*")
                if p.is_file()
                and not p.is_symlink()
                and not p.name.endswith(".part")
                and p.suffix.lower() != ".zip"
            ),
            key=lambda p: p.relative_to(channel_dir.parent).as_posix().casefold(),
        )
        if not source_files:
            continue

        archive_path = completed / f"{channel_dir.name}.zip"
        fd, tmp_name = tempfile.mkstemp(prefix=f".{channel_dir.name}.", suffix=".zip.part", dir=completed)
        os.close(fd)
        tmp_path = Path(tmp_name)
        try:
            with zipfile.ZipFile(tmp_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9, strict_timestamps=True) as archive:
                for source in source_files:
                    arcname = (Path(channel_dir.name) / source.relative_to(channel_dir)).as_posix()
                    info = zipfile.ZipInfo(arcname, date_time=FIXED_ZIP_TIME)
                    info.compress_type = zipfile.ZIP_DEFLATED
                    info.create_system = 3
                    info.external_attr = (0o100644 & 0xFFFF) << 16
                    info._compresslevel = 9
                    with source.open("rb") as source_handle, archive.open(info, "w", force_zip64=True) as archive_handle:
                        while True:
                            chunk = source_handle.read(1024 * 1024)
                            if not chunk:
                                break
                            archive_handle.write(chunk)

            # Avoid dirtying Git on every scheduled run when source content is unchanged.
            if archive_path.exists() and archive_path.read_bytes() == tmp_path.read_bytes():
                tmp_path.unlink()
            else:
                os.replace(tmp_path, archive_path)
            generated.append(archive_path)
        finally:
            tmp_path.unlink(missing_ok=True)

    return generated


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."), help="Directory containing completed/")
    args = parser.parse_args()
    archives = package_completed(args.root)
    for archive in archives:
        print(f"PACKAGED {archive.relative_to(Path(args.root).resolve())}")
    print(f"Completed channel ZIPs ready: {len(archives)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
