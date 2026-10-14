# YouTube Transcript Extractor — Multi-Channel Archive

Scheduled, resumable transcript collection for every channel listed in [`channels.txt`](channels.txt).

## Features

- Automatically scheduled four times per day by GitHub Actions (00:17, 06:17, 12:17 and 18:17 UTC), with an watchdog that checks twice per hour and dispatches a recovery run if no archive run has started for 5 hours and no run is active.
- Tracks old and new uploads per configured channel, including Shorts.
- Deduplicates videos, uses YouTube manual captions first and original-language automatic captions as a fallback.
- Resumes incomplete work from each channel's `transcript_manifest.json` and skips transcripts already saved.
- Stores transcripts in a folder named after the channel while a full backfill is in progress.
- Moves a channel directory to `completed/<Channel Name>/` when every known item has either a valid saved transcript or an explicit terminal `NO_CAPTIONS` outcome and discovery has no fatal errors.
- Generates or refreshes a deterministic `completed/<Channel Name>.zip` beside each completed channel folder; the ZIP contains the transcript files, manifest, audit CSV, and collection summary.
- When all 20 configured channels are marked `COMPLETED` and all 20 individual ZIPs exist, generates one `all_20_channel_archives.zip` bundle containing the 20 ZIP files plus a JSON manifest. It is uploaded as a downloadable GitHub Actions artifact (14-day retention); it is not generated while any channel remains incomplete.
- Copies newly found transcripts into `updated/<Channel Name>/`, with a `new_transcripts.json` index.
- Reports channel/video state in `channel_state.json`, machine-readable `last_run_report.json`, human-readable `last_run_report.md`, per-channel audit CSV and `collection_summary.txt`.
- Persists rate-limit cooldown state to reduce repeat requests after HTTP 429 responses.

## Add channels

Edit [`channels.txt`](channels.txt), adding one URL per line (for example `https://www.youtube.com/@yourchannel`), then commit. The next scheduled run includes it automatically. The initial file includes all 20 configured channel URLs. You can also run now from **Actions → YouTube Transcript Archive → Run workflow**.

## Folder organization

```text
channels.txt
multi_channel_runner.py
youtube_channel_transcripts.py
channel_state.json
last_run_report.json
last_run_report.md
completed/<Channel Name>/*transcripts + manifest/audit/summary*
completed/<Channel Name>.zip (generated ZIP snapshot of the matching channel folder)\nall_20_channel_archives.zip (workflow artifact, created only when all 20 channels and all 20 individual ZIPs are complete)
updated/<Channel Name>/*new transcript copies + new_transcripts.json*
<Channel Name>/*working transcript backfill until complete*
```

`completed/` is the canonical archive. After completion, future scheduled runs inspect the channel again; they add newly found transcripts to its completed archive and copy those new files into `updated/`. Update-feed copies are convenient to browse and do not replace the canonical archive.

## Schedule

The workflow uses UTC cron `17 0,6,12,18 * * *`: 00:17, 06:17, 12:17 and 18:17 UTC (four runs per day). That is 05:47, 11:47, 17:47 and 23:47 India Standard Time. GitHub may delay scheduled runs during periods of high load. Manual runs support an optional `max_channels` test limit and `max_items_per_channel`; the scheduled default is 12 attempts per channel per run to balance channel coverage against job timeout. Set `max_items_per_channel=0` for an explicitly unlimited manual collection run.

## Install and run locally

Requires Python 3.12+, Deno 2.3+ (recommended) or Node.js 22+, and `yt-dlp[default]`:

```bash
python -m pip install -r requirements.txt
python multi_channel_runner.py
```

Optional settings: `USE_WHISPER_FALLBACK=true` enables local faster-whisper fallback after installing `faster-whisper`; `WHISPER_MODEL=small` selects the model. The scheduled workflow defaults to captions-only to keep runs practical.

## How completion works

A channel is not labeled complete if enumeration failed, a transcript file is missing/corrupt, or an item is unresolved after an extraction failure or authentication challenge. An item with no parseable caption tracks can be recorded explicitly as `NO_CAPTIONS`; that terminal outcome remains in the manifest and audit, does not count as a saved transcript, and does not by itself block channel completion. Failed work remains in its manifest so a later run can retry it. Large channel histories can take several scheduled cycles because GitHub Actions has a finite run-time limit. The tool cannot guarantee access to private/deleted/restricted videos or the availability of captions; it does not bypass access controls.

## State files

- `channels.txt`: channel URLs you control.
- `channel_state.json`: latest status for each normalized URL.
- `last_run_report.json`: machine-readable summary of the most recent run.
- `last_run_report.md`: human-readable summary with per-channel counts and errors, also shown in the GitHub Actions step summary.
- `<channel>/transcript_manifest.json`: durable per-video processing state.
- `<channel>/transcript_audit.csv`: per-video audit.
- `<channel>/collection_summary.txt`: human-readable totals and scan results.
- `.youtube_rate_limit_state.json`: persisted YouTube 429 cooldown.

For private/account-required videos, authorized browser cookies can be configured locally. Do not commit cookies or credentials to this repository.


## Authentication for hosted runners

The Isaacverse live test could enumerate the public channel tabs but YouTube returned `Sign in to confirm you're not a bot` for video metadata/transcript extraction from the GitHub-hosted runner. That is an access challenge, not proof that transcripts are unavailable. The runner now stops further video requests after that response rather than repeatedly requesting the same channel.

If you have permission to use an authenticated YouTube session, you may configure an optional repository Actions secret named `YOUTUBE_COOKIES_BASE64` containing the Base64 encoding of a current Netscape-format cookies.txt exported from your own browser session. The workflow writes it only into the runner's temporary directory, passes it to yt-dlp, and does not add it to the repository or test artifact. On Windows PowerShell, you can copy the Base64 value using:

```powershell
[Convert]::ToBase64String([IO.File]::ReadAllBytes(".\\youtube-cookies.txt")) | Set-Clipboard
```

Add the secret under **Settings → Secrets and variables → Actions → New repository secret**. Treat cookies as login credentials: do not paste them into chat, source files, logs, or artifacts; use only a session you are authorized to use, and revoke/refresh the session if needed. Cookies may expire or still be challenged by YouTube. If that happens, run from a local or self-hosted machine where you can use your own authorized browser session. This project intentionally does not bypass YouTube access controls.


## Automation resilience and execution policy (2026-10-11)

- The collector is scheduled four times per day: 00:17, 06:17, 12:17 and 18:17 UTC.
- A newer scheduled or manually started run does not cancel an active collection. Only one collector uses the shared concurrency group at a time; GitHub can keep a single pending run.
- The scheduled default is a 12-item attempt budget per channel. This keeps progress distributed across configured channels instead of allowing a channel with hundreds of pending items to consume the entire runtime. For an intentional full-channel test/backfill, manual dispatch can use `max_items_per_channel=0`; the job still has a finite runtime ceiling.
- Collection is capped at 340 minutes inside a 350-minute job timeout. The run checkpoint and finalization steps record partial progress and package already-completed channels even when collection fails or times out.
- Routine collection is scheduled four times per day. A watchdog checks twice per hour and dispatches a recovery run if the archive has been quiet for over 5 hours and no run is active. Narrow push filters also launch collection after changes to channel configuration or collector code; transcript/state commits are excluded from those paths, preventing recursive runs. Ordinary test/docs edits run validation only.
- The publish step fetches and rebases against the latest `main`, retries safe pushes, and never force-pushes over newer commits.
- Run JSON and Markdown reports record channel errors/auth challenges rather than calling a run completely clean solely because the Python process exited successfully.

## Production readiness status (2026-10-09)

The latest isolated live test for [@isaacverse](https://www.youtube.com/@isaacverse) **passed** after the authorized cookie secret `YOUTUBE_COOKIES_BASE64` was configured in repository Actions secrets.

- Workflow: [Isaacverse live test](https://github.com/therandomhuman-hub/Youtube_Transcript_Extractor/actions/runs/37956540873)
- Regular videos discovered: **9/9**
- Transcript files saved: **9/9**
- Unresolved items: **0**
- Authentication-blocked items: **0**
- Channel status: `COMPLETED`
- Acceptance gate: **PASS**
- Results artifact: [download transcript output and audit](https://github.com/therandomhuman-hub/Youtube_Transcript_Extractor/actions/runs/37956540873/artifacts/11632157521)

The live runner successfully decoded the authorized cookie secret into its temporary workspace. Cookie contents are never included in the repository or test artifacts. The test validates this channel and this session only; it does not guarantee access to all 18 configured channels or future runs. YouTube may expire or challenge a session, and the workflow is designed to stop rather than evade access controls.

Every scheduled archive run now refreshes deterministic ZIP snapshots for completed channel folders before committing archive/state changes. The isolated live-test workflow also includes a ZIP snapshot in its uploaded results artifact.


## Long-run safety and completion policy

The scheduled archive attempts a bounded number of transcript items per channel (default: 12 per run), so a large channel cannot monopolize a run. Adjust the workflow-dispatch input `max_items_per_channel`; `0` means unlimited and is intended only for controlled runs.

Run reports are checkpointed after each channel. Channel state, transcript manifests, audit CSV, and collection summaries are checkpointed after each attempted item. A finalization step records the collection-step outcome and preserves partial checkpoints on timeout or failure. Run reports and channel state are also uploaded as a GitHub Actions artifact for 14 days.

A channel is archived as completed when each discovered item is either `SAVED` (valid transcript exists) or `NO_CAPTIONS` (no parseable captions; explicitly recorded in manifest and audit). **Completed means every discovered item has a resolved collection outcome, not 100% transcript coverage.** No-caption items never count as saved transcripts. Authentication blocks, unresolved failures, and missing/corrupt transcript files still prevent completion.
