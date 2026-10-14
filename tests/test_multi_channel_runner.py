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
    assert result["folder"] == "completed/Example Channel"
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


def test_seed_manifest_does_not_update_timestamp_on_every_scan(tmp_path):
    import youtube_channel_transcripts as engine

    video_id = "abc12345678"
    manifest_path = tmp_path / "transcript_manifest.json"
    record = {"video_id": video_id, "type": "VIDEO", "title": "Stable", "url": f"https://www.youtube.com/watch?v={video_id}",
              "channel": "Example", "status": "SAVED", "filename": f"VIDEO - Stable [{video_id}].txt",
              "last_discovered_at": "2026-01-01T00:00:00+00:00", "updated_at": "2026-01-01T00:00:00+00:00"}
    manifest = {video_id: dict(record)}
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    before = manifest_path.read_text(encoding="utf-8")
    engine.seed_manifest_from_entries(manifest_path, manifest, [{"id": video_id, "title": "Stable", "url": record["url"], "kind": "VIDEO", "channel": "Example"}])
    assert manifest_path.read_text(encoding="utf-8") == before


def test_manifest_completion_rejects_path_traversal(tmp_path):
    folder = tmp_path / "channel"
    folder.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("x" * 500, encoding="utf-8")
    (folder / "transcript_manifest.json").write_text(json.dumps({
        "abc12345678": {"status": "SAVED", "filename": "../outside.txt"}
    }), encoding="utf-8")
    assert runner.manifest_complete(folder) == (False, 0, 1, 1)


def test_runner_repairs_manifest_when_alternate_transcript_file_exists(tmp_path, monkeypatch):
    import youtube_channel_transcripts as engine

    root = tmp_path
    completed = root / "completed"
    updates = root / "updated"
    completed.mkdir(); updates.mkdir()
    folder = root / "Example"
    folder.mkdir()
    channel_url = "https://www.youtube.com/@Example"
    video_id = "abc12345678"
    good_name = f"VIDEO - Existing [{video_id}].txt"
    (folder / good_name).write_text("Recovered transcript text. " * 20, encoding="utf-8")
    (folder / "collection_summary.txt").write_text(f"Channel URL: {channel_url}\n", encoding="utf-8")
    manifest = {video_id: {"video_id": video_id, "type": "VIDEO", "title": "Existing", "url": f"https://www.youtube.com/watch?v={video_id}",
                           "channel": "Example", "status": "SAVED", "filename": "deleted-file.txt", "source": "captions", "language": "en"}}
    (folder / "transcript_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(engine, "discover_channel", lambda *args, **kwargs: (
        "Example", [{"id": video_id, "url": f"https://www.youtube.com/watch?v={video_id}", "title": "Existing", "kind": "VIDEO", "channel": "Example"}], [], []
    ))
    result = runner.process_channel(channel_url, root, completed, updates, {"channels": {}}, "deno", "/usr/bin/deno", set(), False, "small", None)
    archive = completed / "Example"
    saved_manifest = json.loads((archive / "transcript_manifest.json").read_text(encoding="utf-8"))
    assert result["status"] == "COMPLETED"
    assert saved_manifest[video_id]["filename"] == good_name



def test_manifest_completion_accepts_no_caption_as_terminal_outcome(tmp_path):
    folder = tmp_path / "Jad M.H _ AI Automation"
    folder.mkdir()
    (folder / "transcript_manifest.json").write_text(json.dumps({
        "avtN46IusFU": {"status": "NO_CAPTIONS", "title": "No caption tracks", "filename": ""}
    }), encoding="utf-8")
    assert runner.manifest_complete(folder) == (True, 0, 0, 1)


def test_no_caption_items_are_not_requeued_on_next_scan(tmp_path):
    import youtube_channel_transcripts as engine

    video_id = "avtN46IusFU"
    manifest = {video_id: {"status": "NO_CAPTIONS", "type": "SHORT", "title": "No captions"}}
    assert engine.merge_pending_manifest_entries([], manifest, output_dir=tmp_path) == []
    # Fresh discovery may still list it; the runner recognizes terminal status and skips it.
    assert engine.merge_pending_manifest_entries(
        [{"id": video_id, "title": "No captions", "kind": "SHORT"}], manifest, output_dir=tmp_path
    ) == [{"id": video_id, "title": "No captions", "kind": "SHORT"}]


def test_report_checkpoint_contains_partial_results():
    report = runner.make_run_report(
        "2026-10-10T00:00:00+00:00", 18,
        [{"status": "COMPLETED", "saved_this_run": 123, "no_caption_items": 0},
         {"status": "IN_PROGRESS", "saved_this_run": 184, "no_caption_items": 1}],
        "RUNNING"
    )
    assert report["configured_channels"] == 18
    assert report["processed_channels"] == 2
    assert report["remaining_channels"] == 16
    assert report["completed_channels"] == 1
    assert report["saved_transcripts_this_run"] == 307


def test_per_channel_budget_checkpoints_partial_progress(tmp_path, monkeypatch):
    import youtube_channel_transcripts as engine

    root = tmp_path
    completed = root / "completed"
    updated = root / "updated"
    completed.mkdir()
    updated.mkdir()
    channel_url = "https://www.youtube.com/@Example"
    items = [
        {"id": "abc12345678", "url": "https://www.youtube.com/watch?v=abc12345678", "title": "One", "kind": "VIDEO", "channel": "Example"},
        {"id": "def12345678", "url": "https://www.youtube.com/watch?v=def12345678", "title": "Two", "kind": "VIDEO", "channel": "Example"},
        {"id": "ghi12345678", "url": "https://www.youtube.com/watch?v=ghi12345678", "title": "Three", "kind": "VIDEO", "channel": "Example"},
    ]
    monkeypatch.setattr(engine, "discover_channel", lambda *args, **kwargs: ("Example", items, [], []))

    def fake_process_item(item, folder, manifest, manifest_path, *args, **kwargs):
        filename = f"VIDEO - {item['title']} [{item['id']}].txt"
        (folder / filename).write_text("Transcript text. " * 20, encoding="utf-8")
        engine.update_manifest(manifest_path, manifest, item, status="SAVED", source="test", language="en", filename=filename)
        return True, filename

    monkeypatch.setattr(engine, "process_item", fake_process_item)
    state = {"channels": {}}
    result = runner.process_channel(channel_url, root, completed, updated, state,
        "deno", "/usr/bin/deno", set(), False, "small", None, max_items_per_channel=1)

    assert result["attempted_this_run"] == 1
    assert result["saved_this_run"] == 1
    # Inventory counts all known manifest entries, not only the one attempted.
    assert result["video_count"] == 3
    assert result["short_count"] == 0
    assert result["known_items"] == 3
    assert result["batch_limit_reached"] is True
    assert result["status"] == "IN_PROGRESS"
    checkpoint = json.loads((root / "channel_state.json").read_text(encoding="utf-8"))
    assert checkpoint["channels"][channel_url.casefold()]["saved_total"] == 1



def test_unlimited_channel_budget_processes_all_pending_items(tmp_path, monkeypatch):
    import youtube_channel_transcripts as engine

    root = tmp_path
    completed = root / "completed"
    updated = root / "updated"
    completed.mkdir()
    updated.mkdir()
    channel_url = "https://www.youtube.com/@UnlimitedExample"
    items = [
        {"id": "abc12345678", "url": "https://www.youtube.com/watch?v=abc12345678", "title": "One", "kind": "VIDEO", "channel": "Unlimited Example"},
        {"id": "def12345678", "url": "https://www.youtube.com/watch?v=def12345678", "title": "Two", "kind": "VIDEO", "channel": "Unlimited Example"},
        {"id": "ghi12345678", "url": "https://www.youtube.com/watch?v=ghi12345678", "title": "Three", "kind": "VIDEO", "channel": "Unlimited Example"},
    ]
    monkeypatch.setattr(engine, "discover_channel", lambda *args, **kwargs: ("Unlimited Example", items, [], []))

    def fake_process_item(item, folder, manifest, manifest_path, *args, **kwargs):
        filename = f"VIDEO - {item['title']} [{item['id']}].txt"
        (folder / filename).write_text("Transcript text. " * 20, encoding="utf-8")
        engine.update_manifest(manifest_path, manifest, item, status="SAVED", source="test", language="en", filename=filename)
        return True, filename

    monkeypatch.setattr(engine, "process_item", fake_process_item)
    result = runner.process_channel(
        channel_url, root, completed, updated, {"channels": {}},
        "deno", "/usr/bin/deno", set(), False, "small", None,
        max_items_per_channel=0,
    )

    assert result["attempted_this_run"] == 3
    assert result["saved_this_run"] == 3
    assert result["batch_limit_reached"] is False
    assert result["status"] == "COMPLETED"
    assert result["known_items"] == 3
    assert result["unresolved_items"] == 0
    assert (completed / "Unlimited Example" / "transcript_manifest.json").is_file()
