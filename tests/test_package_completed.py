from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.package_completed import package_completed


def test_completed_channel_is_zipped_and_contains_channel_folder(tmp_path):
    channel = tmp_path / "completed" / "Example"
    channel.mkdir(parents=True)
    (channel / "VIDEO - Intro [abc1234567].txt").write_text("Transcript line one\nTranscript line two\n", encoding="utf-8")
    (channel / "transcript_manifest.json").write_text('{"abc1234567": {"status": "SAVED"}}\n', encoding="utf-8")
    (channel / "transcript_audit.csv").write_text("video_id,status\nabc1234567,SAVED\n", encoding="utf-8")

    archives = package_completed(tmp_path)
    archive = tmp_path / "completed" / "Example.zip"
    assert archives == [archive]
    assert archive.is_file()

    with zipfile.ZipFile(archive) as zipped:
        assert sorted(zipped.namelist()) == [
            "Example/VIDEO - Intro [abc1234567].txt",
            "Example/transcript_audit.csv",
            "Example/transcript_manifest.json",
        ]
        assert "Transcript line one" in zipped.read("Example/VIDEO - Intro [abc1234567].txt").decode("utf-8")


def test_completed_channel_zip_is_deterministic_when_content_is_unchanged(tmp_path):
    channel = tmp_path / "completed" / "Example"
    channel.mkdir(parents=True)
    (channel / "collection_summary.txt").write_text("saved=1/1\n", encoding="utf-8")

    archive = package_completed(tmp_path)[0]
    original = archive.read_bytes()
    second_results = package_completed(tmp_path)

    assert second_results == [archive]
    assert archive.read_bytes() == original
    assert not list((tmp_path / "completed").glob("*.part"))


def test_empty_completed_root_has_no_zip_outputs(tmp_path):
    (tmp_path / "completed").mkdir()
    assert package_completed(tmp_path) == []
