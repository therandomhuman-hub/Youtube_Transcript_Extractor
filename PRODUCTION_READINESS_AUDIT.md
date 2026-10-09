# Production Readiness Audit — YouTube Transcript Extractor

**Audit date:** 2026-10-09  
**Repository:** [therandomhuman-hub/Youtube_Transcript_Extractor](https://github.com/therandomhuman-hub/Youtube_Transcript_Extractor)  
**Scope:** repository/code review, GitHub Actions configuration, state recovery, and live test of `https://www.youtube.com/@isaacverse`.

## Verdict

**NOT PRODUCTION READY for unattended transcript extraction on GitHub-hosted runners yet.** The scheduling, discovery, recovery, status reporting, and acceptance checks are in place, and the code validation suite passes. The blocking end-to-end issue is external authentication: the hosted runner can enumerate the public channel but YouTube returns “Sign in to confirm you're not a bot” when the collector requests video metadata. No `YOUTUBE_COOKIES_BASE64` secret was configured during the live test, so no transcript could be saved. The live workflow correctly fails rather than reporting a false success.

## Live test results

- **Run:** [Isaacverse Live Transcript Test #6](https://github.com/therandomhuman-hub/Youtube_Transcript_Extractor/actions/runs/37956540873)
- **Target:** `https://www.youtube.com/@isaacverse`
- **Channel-root entries:** 9
- **Videos-tab entries:** 9, all duplicates of the root entries
- **Unique regular videos:** **9 — PASS** against the expected count
- **Shorts tab:** absent; marked as optional `NO_TAB`, not a fatal scan error
- **Shorts discovered:** 0
- **Unique items:** 9
- **Transcripts saved:** **0/9 — FAIL**
- **Unresolved:** 9
- **Authentication-blocked item count:** 1 before the runner intentionally stopped additional requests for the channel
- **Scan errors:** none after the absent Shorts tab was handled
- **Reason for transcript failure:** YouTube returned a bot/sign-in challenge for video `QXfugR3ZIAs`. The workflow then stopped further requests to avoid repeatedly hitting the same challenge.

### Video inventory observed

| # | Video title | Video ID | Outcome in live run |
|---:|---|---|---|
| 1 | I Blew Up a Shorts Channel in 7 Days! | `QXfugR3ZIAs` | `AUTH_REQUIRED` |
| 2 | How I Blew Up My Youtube Channel | `82Mpsgc8cLM` | `DISCOVERED`; not attempted after auth stop |
| 3 | How I Actually Write Viral Scripts | `cX8c3R2LFd4` | `DISCOVERED`; not attempted after auth stop |
| 4 | How I Actually Make AI Voice Sound Real | `KhQTKG3Xtbs` | `DISCOVERED`; not attempted after auth stop |
| 5 | How I Actually Edit Viral Videos | `ciAywjey0cY` | `DISCOVERED`; not attempted after auth stop |
| 6 | I Tried Making a Viral AI Video! | `_rXj297vYYs` | `DISCOVERED`; not attempted after auth stop |
| 7 | How I Actually Make Viral Thumbnails | `mI7cq4uHCZ4` | `DISCOVERED`; not attempted after auth stop |
| 8 | How I Broke Youtube with 1 Video | `GPoti7DZsME` | `DISCOVERED`; not attempted after auth stop |
| 9 | I Tried Youtube Shorts for 365 Days! | `X1WJlNUJOgg` | `DISCOVERED`; not attempted after auth stop |

The count of nine is confirmed for the public video listings observed during this run. This does **not** prove every transcript is accessible or that there are no private, unlisted, deleted, or separately inaccessible items.

## Findings and fixes made

| Severity | Finding | Status |
|---|---|---|
| **Blocker** | GitHub-hosted runner receives a YouTube bot/sign-in challenge without authorized cookies. | **Unresolved external dependency.** Workflow accepts an optional GitHub Actions secret; no credentials were provided/configured during the test. |
| High | A channel with no Shorts tab could remain permanently incomplete due to yt-dlp logging an error while returning no metadata. | **Fixed.** Diagnostics are captured and a missing optional Shorts tab becomes `NO_TAB`. |
| High | A manifest could say `SAVED` after its transcript file was missing, causing a channel to stay incomplete. | **Fixed.** Unresolved records are retried; found alternate files are reconciled to the manifest. |
| High | A bot challenge could lead to repeated requests for every remaining video. | **Fixed.** The channel run stops additional video requests on an authentication challenge and records the blocked state. |
| Medium | Repeated scans rewrote `last_discovered_at` on every existing item, creating unnecessary manifest/CSV churn and repository growth. | **Fixed.** Stable metadata no longer refreshes that timestamp on every scan. |
| Medium | A corrupted or edited manifest filename could point outside the channel folder and falsely count an unrelated file as a transcript. | **Fixed.** Transcript-path checks require a filename located directly inside the channel folder. |
| Medium | The manual workflow input was interpolated into a shell command. | **Fixed.** Input is passed through an environment variable and validated as a non-negative integer. |
| Medium | Existing transcripts written just before an interrupted manifest update could be left unregistered. | **Fixed.** Existing files are reconciled back into the manifest. |
| Medium | Channels with overlapping display names/handles could accidentally reuse a folder. | **Improved.** Preferred folders are validated against the stored channel URL before reuse. |
| Low | Validation workflow used older Node 20-targeting action versions. | **Fixed.** Validation actions upgraded to current Node 24-compatible major releases. |

## Automation and storage review

- Production collection workflow: [`.github/workflows/transcript-archive.yml`](https://github.com/therandomhuman-hub/Youtube_Transcript_Extractor/blob/main/.github/workflows/transcript-archive.yml)
- Schedule: UTC cron `17 */6 * * *` — four scheduled starts per day, approximately six hours apart.
- Channel config: [`channels.txt`](https://github.com/therandomhuman-hub/Youtube_Transcript_Extractor/blob/main/channels.txt) contains 18 configured URLs.
- Channel state and manifests allow unfinished items to resume.
- Completed channels are stored under `completed/<Channel Name>/`; new transcripts are copied to `updated/<Channel Name>/`.
- The live test uploads an audit artifact and enforces acceptance criteria: exactly nine regular videos, completed status, all transcripts saved, no unresolved items, and no scan errors.
- Transcript archives and manifests are committed to the repository. As the number of channels and videos grows, monitor repository size and workflow runtime; Git history retains previously committed versions.
- Caption-based extraction is the default. Local Whisper fallback is opt-in and disabled in the hosted workflows; it cannot bypass YouTube authentication challenges.

## Required action to pass the live transcript test

1. In the repository, open **Settings → Secrets and variables → Actions → New repository secret**.
2. Add a secret named `YOUTUBE_COOKIES_BASE64` containing the Base64 encoding of a current Netscape-format `cookies.txt` exported from a browser session you are authorized to use. The workflow writes it to the runner's temporary directory and does not commit it.
3. Re-run [Isaacverse Live Transcript Test](https://github.com/therandomhuman-hub/Youtube_Transcript_Extractor/actions/workflows/isaacverse-live-test.yml).
4. Require a run with **9/9 transcripts saved** and overall status `COMPLETED`. If YouTube still challenges a hosted runner, use a self-hosted runner or a local run with an authorized browser session.

Treat browser cookies like passwords. Do not commit them or paste them into chat/logs. They can expire, and authorized cookies do not guarantee YouTube will allow every video.

## CI verification

- Latest code validation after the audit hardening: [Validate transcript project](https://github.com/therandomhuman-hub/Youtube_Transcript_Extractor/actions/runs/37957139725) — **passed, 11 tests passed**; validation now uses the upgraded Node 24-compatible checkout/Python actions.
- The live extraction gate is intentionally **failing** while the external authentication prerequisite is missing. That is the truthful result; the project should not be labeled fully production-ready until the live test passes.

## Overall assessment

**Code-validation readiness: PASS. Live inventory/discovery: PASS for the nine public video entries. End-to-end transcript production: BLOCKED pending authorized YouTube access from the scheduled runner.**
