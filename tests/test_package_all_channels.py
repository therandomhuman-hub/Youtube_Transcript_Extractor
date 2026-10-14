from pathlib import Path
import json
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.package_all_channels import package_all_channels


def make_fixture(root: Path, count: int = 20, in_progress: int | None = None, missing_zip: int | None = None):
    urls = [f"https://www.youtube.com/@channel{i:02d}" for i in range(count)]
    (root / "channels.txt").write_text(
        "# configured channels\n" + "\n".join(urls) + "\n",
        encoding="utf-8",
    )
    completed = root / "completed"
    completed.mkdir(parents=True)
    records = {}
    for index, url in enumerate(urls):
        name = f"Channel {index:02d}"
        folder = f"completed/{name}"
        status = "IN_PROGRESS" if index == in_progress else "COMPLETED"
        records[url.casefold()] = {
            "channel_url": url,
            "channel_name": name,
            "folder": folder,
            "status": status,
            "saved_total": index + 1,
            "known_items": index + 2,
            "no_caption_items": 0,
        }
        if index != missing_zip:
            with zipfile.ZipFile(completed / f"{name}.zip", "w") as archive:
                archive.writestr(f"{name}/transcript_manifest.json", '{"status":"SAVED"}\n')
    (root / "channel_state.json").write_text(
        json.dumps({"channels": records}),
        encoding="utf-8",
    )
    return urls


def test_bundle_contains_all_channel_zips_and_manifest(tmp_path):
    make_fixture(tmp_path)
    output = tmp_path / "bundle.zip"

    result = package_all_channels(tmp_path, output, expected_count=20)

    assert result == output
    with zipfile.ZipFile(output) as bundle:
        names = sorted(bundle.namelist())
        assert len([name for name in names if name.endswith(".zip")]) == 20
        assert "all_20_channels_manifest.json" in names
        manifest = json.loads(bundle.read("all_20_channels_manifest.json"))
        assert manifest["included_channel_count"] == 20
        assert manifest["expected_channel_count"] == 20
        assert len(manifest["channels"]) == 20
        assert all(channel["status"] == "COMPLETED" for channel in manifest["channels"])


def test_bundle_is_not_created_while_any_channel_is_in_progress(tmp_path):
    make_fixture(tmp_path, in_progress=12)
    output = tmp_path / "bundle.zip"

    assert package_all_channels(tmp_path, output, expected_count=20) is None
    assert not output.exists()


def test_bundle_is_not_created_when_an_individual_zip_is_missing(tmp_path):
    make_fixture(tmp_path, missing_zip=4)
    output = tmp_path / "bundle.zip"

    assert package_all_channels(tmp_path, output, expected_count=20) is None
    assert not output.exists()


def test_bundle_requires_exact_configured_channel_count(tmp_path):
    make_fixture(tmp_path, count=18)
    output = tmp_path / "bundle.zip"

    assert package_all_channels(tmp_path, output, expected_count=20) is None
    assert not output.exists()


def test_incomplete_state_removes_stale_bundle(tmp_path):
    make_fixture(tmp_path, in_progress=0)
    output = tmp_path / "bundle.zip"
    output.write_bytes(b"stale archive")

    assert package_all_channels(tmp_path, output, expected_count=20) is None
    assert not output.exists()


def test_bundle_rejects_corrupt_channel_zip(tmp_path):
    make_fixture(tmp_path)
    corrupt = tmp_path / "completed" / "Channel 07.zip"
    corrupt.write_bytes(b"not a valid zip")
    output = tmp_path / "bundle.zip"

    assert package_all_channels(tmp_path, output, expected_count=20) is None
    assert not output.exists()
