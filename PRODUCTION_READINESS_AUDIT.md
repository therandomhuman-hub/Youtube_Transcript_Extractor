# Full Production Audit — YouTube Transcript Extractor

**Audit date:** 2026-10-11  
**Repository:** [therandomhuman-hub/Youtube_Transcript_Extractor](https://github.com/therandomhuman-hub/Youtube_Transcript_Extractor)  
**Audit scope:** channel discovery, transcript extraction, manifest integrity, completion semantics, checkpoint recovery, scheduling/concurrency, report accuracy, ZIP packaging, CI, secrets, and current live repository state.

## Executive verdict

**Status: operational, with the full backfill still incomplete.** The repository has resumable transcript manifests, per-item checkpoints, deterministic ZIP packaging, a four-times-daily schedule, an authorized-session option, and CI tests. The live state snapshot below is from `channel_state.json` last updated at **2026-10-11 09:36:53 UTC**; a newer archive run was still active when this audit was prepared, so these totals are a published snapshot, not a claim about its uncommitted progress.

### Current published inventory snapshot

| Metric | Value |
|---|---:|
| Configured channels | 18 |
| Channels marked completed | 4 |
| Channels still being backfilled | 14 |
| Transcript files saved | 784 |
| Discovered items recorded | 5,471 |
| Unresolved items | 4,684 |
| Explicit no-caption outcomes | 3 |
| Authentication-blocked items recorded | 0 |
| Regular videos in inventory | 2,944 |
| Shorts in inventory | 2,527 |

The accounting reconciles: 784 saved + 4,684 unresolved + 3 no-caption outcomes = 5,471 known items. “Completed” means each discovered item has a valid transcript or a terminal `NO_CAPTIONS` result and channel enumeration did not fail; it does **not** mean 100% transcript coverage. No-caption outcomes remain visible and never count as saved transcripts.

## Current per-channel state

Source: committed `channel_state.json`, snapshot last checked 2026-10-11 09:36:53 UTC.

| Channel | Status | Saved / known | Unresolved | No captions |
|---|---|---:|---:|---:|
| One Person Business | COMPLETED | 123 / 124 | 0 | 1 |
| Jad M.H — AI Automation | COMPLETED | 185 / 186 | 0 | 1 |
| Jason Wardrop | IN_PROGRESS | 132 / 326 | 194 | 0 |
| Tim Danilov Biz | IN_PROGRESS | 30 / 110 | 80 | 0 |
| Everygen AI | COMPLETED | 4 / 4 | 0 | 0 |
| Deven Seenath | IN_PROGRESS | 30 / 732 | 702 | 0 |
| AIpreneur | IN_PROGRESS | 29 / 55 | 25 | 1 |
| Joshua Elder | IN_PROGRESS | 26 / 1,737 | 1,711 | 0 |
| Isaac | COMPLETED | 9 / 9 | 0 | 0 |
| Shawn Builds AI | IN_PROGRESS | 24 / 67 | 43 | 0 |
| E'Calm | IN_PROGRESS | 24 / 32 | 8 | 0 |
| Airyzen AI | IN_PROGRESS | 24 / 26 | 2 | 0 |
| Udo Onyekwere | IN_PROGRESS | 24 / 63 | 39 | 0 |
| Victor Bigbro | IN_PROGRESS | 24 / 86 | 62 | 0 |
| Jack Neel | IN_PROGRESS | 24 / 991 | 967 | 0 |
| Bahaa AI | IN_PROGRESS | 24 / 33 | 9 | 0 |
| Learn with Lukas | IN_PROGRESS | 24 / 328 | 304 | 0 |
| Sunny Lenarduzzi | IN_PROGRESS | 24 / 562 | 538 | 0 |

## Current workflow policy

The canonical workflow is [`.github/workflows/transcript-archive.yml`](https://github.com/therandomhuman-hub/Youtube_Transcript_Extractor/blob/main/.github/workflows/transcript-archive.yml).

- **Schedule:** `17 0,6,12,18 * * *` — 00:17, 06:17, 12:17 and 18:17 UTC; 05:47, 11:47, 17:47 and 23:47 India Standard Time.
- **Trigger policy:** scheduled and explicit manual dispatch only. Source-code changes run the short validation workflow rather than unexpectedly launching a full, long-running collector.
- **Concurrency:** `cancel-in-progress: false`, so a new run does not intentionally cancel active collection. GitHub concurrency allows only one pending run in a group; repeated manual triggers can replace the pending run.
- **Default per-channel budget:** 12 attempts per channel per run. This distributes work across channels and avoids letting a single very large channel monopolize a run. Manual dispatch can set `max_items_per_channel=0` for an unlimited attempt budget, but this is not recommended for routine scheduled runs.
- **Runtime limits:** collection step 340 minutes; job 350 minutes. This is below the six-hour schedule interval, but slow requests and GitHub queue delays can still affect cadence.
- **Publishing:** the workflow fetches and rebases against the latest `main`, retries safe pushes, and never force-pushes.
- **Artifacts:** run report, channel state, summaries and completed ZIPs are uploaded for 14 days.
- **Secrets:** `YOUTUBE_COOKIES_BASE64`, when configured, is decoded into a temporary runner file; cookie contents must never be committed or uploaded.

GitHub can delay scheduled events during high load; a cron schedule is not an exact-start guarantee. See [GitHub's scheduled-workflow documentation](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows).

## Reliability findings and implemented improvements

| Finding | Resolution / current behavior |
|---|---|
| A run appeared to stop early | Previous default was six attempts per channel. The routine budget was changed to 12 per channel; the collection timeout is 340 minutes. |
| An active run could be cancelled by a new push/schedule | Concurrency now uses `cancel-in-progress: false`. |
| Every workflow/report edit could launch another full collection | Removed the archive workflow's push trigger. Use schedule or **Actions → YouTube Transcript Archive → Run workflow** for collection; CI validates source changes. |
| Git push could fail after another commit advanced `main` | Safe fetch/rebase/push retry loop added; force push is prohibited. |
| A timeout could leave only partial run metadata | Per-item manifests/state checkpoints and a finalization step preserve available progress and mark cancellation/failure. |
| A successful Python exit could be mistaken for a completed full backfill | The report finalizer now distinguishes a successful run with remaining work as `RUN_SUCCEEDED_BACKFILL_INCOMPLETE`; error/auth outcomes are reported separately. |
| No-caption items could be retried forever or incorrectly counted as transcripts | `NO_CAPTIONS` is a terminal auditable outcome, not a saved transcript. |
| Stale manifest entries could claim a transcript exists when the file is missing | Completion validates transcript files; missing saved files are requeued, and recoverable files can repair stale manifest metadata. |
| ZIPs could change byte-for-byte across identical runs | Packaging uses stable ordering/timestamps, temporary output plus atomic replacement, excludes symlinks and `.part` files, and avoids replacing unchanged ZIPs. |
| Reports were hard to read | JSON plus Markdown run reports are generated; artifacts include reports and completed ZIPs. |

## Completed ZIP archives

The repository currently contains four completed channel ZIPs:

- [Jad M.H _ AI Automation.zip](https://github.com/therandomhuman-hub/Youtube_Transcript_Extractor/raw/refs/heads/main/completed/Jad%20M.H%20_%20AI%20Automation.zip)
- [One Person Business.zip](https://github.com/therandomhuman-hub/Youtube_Transcript_Extractor/raw/refs/heads/main/completed/One%20Person%20Business.zip)
- [Everygen AI.zip](https://github.com/therandomhuman-hub/Youtube_Transcript_Extractor/raw/refs/heads/main/completed/Everygen%20AI.zip)
- [Isaac.zip](https://github.com/therandomhuman-hub/Youtube_Transcript_Extractor/raw/refs/heads/main/completed/Isaac.zip)

[Browse the completed archive directory](https://github.com/therandomhuman-hub/Youtube_Transcript_Extractor/tree/main/completed). Repository access requires GitHub authentication because the repository is private.

## Live tests and CI

- [Isolated Isaacverse live test](https://github.com/therandomhuman-hub/Youtube_Transcript_Extractor/actions/runs/37965713278) passed for nine regular videos in that session. This validates one channel/session, not all channels or future runs.
- [Latest validation after the audit changes](https://github.com/therandomhuman-hub/Youtube_Transcript_Extractor/actions/runs/38135712779) passed at commit `3cf40da9170cefbee41d44b9c2af3214b2e2ba88`; compilation succeeded and **26 tests passed**.
- The current workflow policy, report-finalization changes, and refreshed audit document are covered by this passing CI run.

## Remaining risks / next checks

1. **Full backfill is not finished:** 14 channels still have unresolved items. Largest backlogs in the published snapshot are Joshua Elder (1,711), Jack Neel (967), Deven Seenath (702), and Sunny Lenarduzzi (538).
2. **Current run may be on an older workflow revision:** run #10 began before the latest policy changes and was still reported as active at audit time. Its eventual report should be checked; the new routine budget and trigger policy apply to subsequent scheduled/manual runs.
3. **YouTube access can change:** cookies expire, challenges can occur, and some videos may not expose parseable captions. The collector must record these outcomes and not attempt to bypass access controls.
4. **One pending run may be a legacy push-triggered run:** old events already queued before the trigger policy was changed can still appear in Actions history. Future source-only commits should no longer launch the collector.
5. **Long-run publication must be confirmed:** a workflow step producing a ZIP locally is not proof it was committed. Confirm the ZIP exists under `completed/` on `main` before sharing a download link.

## Production acceptance criteria

- [ ] All 18 channels have a recent, complete inventory scan.
- [ ] Every known item is either a valid saved transcript or an explicit terminal no-caption result; unresolved failures block channel completion.
- [ ] Each completed channel folder has a valid ZIP on `main`.
- [ ] Scheduled runs complete or preserve checkpointed partial progress and publish an accurate Markdown/JSON report.
- [ ] The latest CI run passes after all audit commits.
- [ ] A later scheduled run demonstrates that pending work resumes without duplicating saved transcripts or repeatedly retrying terminal no-caption items.
