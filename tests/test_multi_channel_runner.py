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
    (channel / "collection_summary.txt").write_text(f"Channel URL: {channel_url}\n", encoding="utf-8")

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


def test_saved_manifest_entry_with_missing_file_is_requeued(tmp_path):
    import youtube_channel_transcripts as engine

    video_id = "zxy98765432"
    manifest = {video_id: {"status": "SAVED", "filename": "missing.txt", "type": "VIDEO", "title": "Lost file"}}
    pending = engine.merge_pending_manifest_entries([], manifest, output_dir=tmp_path)
    assert len(pending) == 1
    assert pending[0]["id"] == video_id


def test_channel_home_scan_failure_does_not_block_video_tab(monkeypatch, tmp_path):
    import youtube_channel_transcripts as engine

    channel_id = "UC" + "1" * 22
    video_id = "abc12345678"

    class FakeYDL:
        def __init__(self, params):
            self.params = params
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def extract_info(self, url, download=False):
            if url == "https://www.youtube.com/@Example":
                raise RuntimeError("temporary root page error")
            return {"channel_id": channel_id, "uploader": "Example", "entries": ([{"id": video_id, "title": "One video", "webpage_url": f"https://www.youtube.com/watch?v={video_id}"}] if url.endswith("/videos") else [])}

    class FastRateLimiter:
        def run(self, operation, **kwargs):
            return operation()

    monkeypatch.setattr(engine.yt_dlp, "YoutubeDL", FakeYDL)
    name, entries, scan_results, fatal_errors = engine.discover_channel(
        "https://www.youtube.com/@Example", None, None, None, set(), FastRateLimiter()
    )
    assert name == "Example"
    assert [item["id"] for item in entries] == [video_id]
    assert any(item["type"] == "CHANNEL" and item["status"] == "FAILED" for item in scan_results)
    assert not any(error.startswith("CHANNEL:") for error in fatal_errors)


def test_missing_shorts_tab_is_nonfatal(monkeypatch):
    import youtube_channel_transcripts as engine

    channel_id = "UC" + "2" * 22
    video_id = "abc12345678"
    class FakeYDL:
        def __init__(self, params): pass
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def extract_info(self, url, download=False):
            if url.endswith("/shorts"):
                raise RuntimeError("ERROR: [youtube:tab] This channel does not have a shorts tab")
            return {"channel_id": channel_id, "uploader": "Example", "entries": [{"id": video_id, "title": "One video"}]}
    class FastRateLimiter:
        def run(self, operation, **kwargs): return operation()
    monkeypatch.setattr(engine.yt_dlp, "YoutubeDL", FakeYDL)
    _, entries, scans, fatal_errors = engine.discover_channel("https://www.youtube.com/@Example", None, None, None, set(), FastRateLimiter())
    assert len(entries) == 1
    assert any(row.get("status") == "NO_TAB" for row in scans)
    assert fatal_errors == []


def test_auth_challenge_is_detected_without_retrying_all_videos():
    import youtube_channel_transcripts as engine
    assert engine.is_auth_required("Sign in to confirm you're not a bot")
    assert engine.is_auth_required("ERROR: confirm you’re not a bot")
    assert not engine.is_auth_required("No captions found")
