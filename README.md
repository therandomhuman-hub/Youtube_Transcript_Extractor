# YouTube Transcript Extractor — Multi-Channel Archive

Scheduled, resumable transcript collection for every channel listed in [`channels.txt`](channels.txt).

## Features

- Automatically scheduled every six hours by GitHub Actions.
- Tracks old and new uploads per configured channel, including Shorts.
- Deduplicates videos, uses YouTube manual captions first and original-language automatic captions as a fallback.
- Resumes incomplete work from each channel's `transcript_manifest.json` and skips transcripts already saved.
- Stores transcripts in a folder named after the channel while a full backfill is in progress.
- Moves a channel directory to `completed/<Channel Name>/` only when every known video has a valid saved transcript and no channel-scan errors remain.
- Copies newly found transcripts into `updated/<Channel Name>/`, with a `new_transcripts.json` index.
- Reports channel/video state in `channel_state.json`, `last_run_report.json`, per-channel audit CSV and `collection_summary.txt`.
- Persists rate-limit cooldown state to reduce repeat requests after HTTP 429 responses.

## Add channels

Edit [`channels.txt`](channels.txt), adding one URL per line (for example `https://www.youtube.com/@yourchannel`), then commit. The next scheduled run includes it automatically. The initial file includes all 18 URLs from the provided channel list. You can also run now from **Actions → YouTube Transcript Archive → Run workflow**.

## Folder organization

```text
channels.txt
multi_channel_runner.py
youtube_channel_transcripts.py
channel_state.json
last_run_report.json
completed/<Channel Name>/*transcripts + manifest/audit/summary*
updated/<Channel Name>/*new transcript copies + new_transcripts.json*
<Channel Name>/*working transcript backfill until complete*
```

`completed/` is the canonical archive. After completion, future scheduled runs inspect the channel again; they add newly found transcripts to its completed archive and copy those new files into `updated/`. Update-feed copies are convenient to browse and do not replace the canonical archive.

## Schedule

The workflow uses UTC cron `17 */6 * * *` (four runs per day, about six hours apart). GitHub may delay scheduled runs during periods of high load. `workflow_dispatch` supports manual starts and an optional `max_channels` test limit.

## Install and run locally

Requires Python 3.12+, Deno 2.3+ (recommended) or Node.js 22+, and `yt-dlp[default]`:

```bash
python -m pip install -r requirements.txt
python multi_channel_runner.py
```

Optional settings: `USE_WHISPER_FALLBACK=true` enables local faster-whisper fallback after installing `faster-whisper`; `WHISPER_MODEL=small` selects the model. The scheduled workflow defaults to captions-only to keep runs practical.

## How completion works

A channel is not labeled complete if enumeration failed, a transcript is missing, or an item is unresolved due to unavailable captions or an extraction failure. Failed work remains in its manifest so a later run can retry it. Large channel histories can take several scheduled cycles, because GitHub Actions has a finite run-time limit. The tool cannot guarantee access to private/deleted/restricted videos or availability of captions; it does not bypass access controls.

## State files

- `channels.txt`: channel URLs you control.
- `channel_state.json`: latest status for each normalized URL.
- `last_run_report.json`: summary of the most recent run.
- `<channel>/transcript_manifest.json`: durable per-video processing state.
- `<channel>/transcript_audit.csv`: per-video audit.
- `<channel>/collection_summary.txt`: human-readable totals and scan results.
- `.youtube_rate_limit_state.json`: persisted YouTube 429 cooldown.

For private/account-required videos, authorized browser cookies can be configured locally. Do not commit cookies or credentials to this repository.
