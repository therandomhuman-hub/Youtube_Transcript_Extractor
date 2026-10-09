import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import multi_channel_runner as runner


def test_channel_list_reads_and_deduplicates(tmp_path):
    file = tmp_path / "channels.txt"
    file.write_text("# comment\nhttps://www.youtube.com/@Example/videos\n@Example\ninvalid.example/path\n", encoding="utf-8")
    assert runner.read_channels(file) == ["https://www.youtube.com/@Example"]


def test_manifest_completion_requires_transcript_file(tmp_path):
    folder = tmp_path / "channel"
    folder.mkdir()
    transcript_name = "VIDEO - title [abc12345678].txt"
    (folder / "transcript_manifest.json").write_text(json.dumps({
        "abc12345678": {"status": "SAVED", "filename": transcript_name}
    }), encoding="utf-8")
    assert runner.manifest_complete(folder) == (False, 0, 1, 1)
    (folder / transcript_name).write_text("x" * 200, encoding="utf-8")
    assert runner.manifest_complete(folder) == (True, 1, 0, 1)
