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


def test_channel_url_normalization_and_parser():
    import youtube_channel_transcripts as engine

    assert engine.normalize_channel_url("https://www.youtube.com/@Example/videos") == "https://www.youtube.com/@Example"
    vtt = "WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nhello everyone\n\n00:00:01.000 --> 00:00:02.000\nhello everyone welcome\n"
    assert engine.parse_vtt(vtt) == "hello everyone welcome"


def test_completed_channel_is_updated_in_place(tmp_path, monkeypatch):
    import youtube_channel_transcripts as engine

    root = tmp_path
    completed = root / "completed"
    updates = root / "updated"
    channel = completed / "Example Channel"
    channel.mkdir(parents=True)
    updates.mkdir()
    channel_url = "https://www.youtube.com/@Example"
    video_id = "abc12345678"
    filename = f"VIDEO - Existing [{video_id}].txt"
    (channel / filename).write_text("Transcript content " * 20, encoding="utf-8")
    (channel / "transcript_manifest.json").write_text(json.dumps({
        video_id: {"video_id": video_id, "type": "VIDEO", "title": "Existing", "url": f"https://www.youtube.com/watch?v={video_id}",
                  "channel": "Example Channel", "status": "SAVED", "filename": filename, "source": "captions", "language": "en"}
    }), encoding="utf-8")
    (channel / "collection_summary.txt").write_text(f"Channel URL: {channel_url}\\n", encoding="utf-8")

    monkeypatch.setattr(engine, "discover_channel", lambda *args, **kwargs: (
        "Example Channel", [{"id": video_id, "url": f"https://www.youtube.com/watch?v={video_id}", "title": "Existing", "kind": "VIDEO", "channel": "Example Channel"}], [], []
    ))
    copy_calls = []
    original_copytree = runner.shutil.copytree
    def record_copytree(*args, **kwargs):
        copy_calls.append((str(args[0]), str(args[1])))
        return original_copytree(*args, **kwargs)
    monkeypatch.setattr(runner.shutil, "copytree", record_copytree)

    state = {"channels": {}}
    result = runner.process_channel(channel_url, root, completed, updates, state, "deno", "/usr/bin/deno", set(), False, "small", None)

    assert result["status"] == "COMPLETED"
    assert result["folder"] == str(channel)
    assert channel.is_dir()
    assert not (root / "Example Channel").exists()
    assert copy_calls == []
