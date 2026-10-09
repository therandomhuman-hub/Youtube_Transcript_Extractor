# Production Readiness Audit — YouTube Transcript Extractor

**Audit date:** 2026-10-09  
**Repository:** [therandomhuman-hub/Youtube_Transcript_Extractor](https://github.com/therandomhuman-hub/Youtube_Transcript_Extractor)  
**Scope:** repository code, GitHub Actions scheduling/state persistence, deterministic ZIP packaging, and isolated live transcript extraction for `https://www.youtube.com/@isaacverse`.

## Verdict

**The isolated Isaacverse live-test acceptance criteria passed.** The successful rerun used the authorized `YOUTUBE_COOKIES_BASE64` Actions secret; GitHub Actions decoded it into a temporary runner file and the runner saved all nine discovered regular-video transcripts. The test does not prove every configured channel or future run will succeed, particularly if YouTube expires or challenges the session.

## Verified live test

- **Workflow run:** [Isaacverse live test](https://github.com/therandomhuman-hub/Youtube_Transcript_Extractor/actions/runs/37956540873)
- **Git revision tested:** `3b0e51f8e7ceb4b38b0889c92a2c0c1f01e78250`
- **Target channel:** `https://www.youtube.com/@isaacverse`
- **Channel status:** `COMPLETED`
- **Regular videos discovered:** 9 / 9 expected
- **Shorts discovered:** 0 (the channel did not expose a Shorts tab during this run)
- **Transcript files saved:** **9 / 9**
- **Unresolved items:** 0
- **Authentication-blocked items:** 0
- **Fatal scan errors:** 0
- **Acceptance gate:** **PASS**
- **Artifact:** [download test transcripts and audit output](https://github.com/therandomhuman-hub/Youtube_Transcript_Extractor/actions/runs/37956540873/artifacts/11632157521)

The successful logs explicitly show that the secret was available to the cookie-configuration step, the cookie file was written to the runner's temporary directory, all nine video operations were processed, the channel was marked `COMPLETED`, and the acceptance checks passed. Cookie contents were masked in logs and were not uploaded as an artifact.

## Video inventory from the passing run

| # | Video title | Video ID | Result |
|---:|---|---|---|
| 1 | I Blew Up a Shorts Channel in 7 Days! | `QXfugR3ZIAs` | Transcript saved |
| 2 | How I Blew Up My Youtube Channel | `82Mpsgc8cLM` | Transcript saved |
| 3 | How I Actually Write Viral Scripts | `cX8c3R2LFd4` | Transcript saved |
| 4 | How I Actually Make AI Voice Sound Real | `KhQTKG3Xtbs` | Transcript saved |
| 5 | How I Actually Edit Viral Videos | `ciAywjey0cY` | Transcript saved |
| 6 | I Tried Making a Viral AI Video! | `_rXj297vYYs` | Transcript saved |
| 7 | How I Actually Make Viral Thumbnails | `mI7cq4uHCZ4` | Transcript saved |
| 8 | How I Broke Youtube with 1 Video | `GPoti7DZsME` | Transcript saved |
| 9 | I Tried Youtube Shorts for 365 Days! | `X1WJlNUJOgg` | Transcript saved |

The inventory represents the channel's public regular-video items observed during this run, not private, unlisted, deleted, or otherwise inaccessible material.

## Implemented safeguards and features

| Area | Implementation/status |
|---|---|
| Six-hour scheduling | Configured in `.github/workflows/transcript-archive.yml` with UTC cron `17 */6 * * *`. |
| Multi-channel configuration | `channels.txt` accepts one YouTube channel URL per line; duplicate normalized URLs are removed. |
| Resume/reconciliation | Per-channel manifest records are resumed, missing transcript files are retried, and existing transcript files can repair stale manifest entries. |
| Completion rules | A channel is moved into `completed/<Channel>/` only when known items have valid saved transcripts and discovery has no fatal errors. |
| Update feed | New transcript copies and `new_transcripts.json` are stored under `updated/<Channel>/`. |
| Rate-limit behavior | HTTP 429 responses persist cooldown information; bot/sign-in challenges stop additional video requests for that channel in the run. |
| Secret handling | Authorized cookie data is passed as a GitHub Actions secret and written only to runner temporary storage. No cookie value is tracked in Git. |
| ZIP snapshots | `scripts/package_completed.py` creates deterministic `completed/<Channel>.zip` packages from completed channel folders. Both the scheduled archive workflow and isolated live-test workflow invoke the packager. |
| Acceptance test | The isolated live-test gate checks expected video count, completion status, saved transcript coverage, unresolved items, and scan errors. |

## ZIP package contents

The canonical folder remains `completed/<Channel>/`. The sibling `completed/<Channel>.zip` contains a top-level folder named after the channel, with its transcript text files, `transcript_manifest.json`, `transcript_audit.csv`, and `collection_summary.txt`. ZIP timestamps and ordering are normalized to avoid rewriting unchanged packages on every scheduled run. Temporary `.part` files and symlinks are excluded.

## Remaining production considerations

1. **One channel is validated end to end, not every channel.** Run the full scheduled archive job and review its report before claiming the whole 18-channel list is fully backfilled.
2. **Authentication can expire.** The successful run confirms this current authorized session worked for the isolated test. A future challenge should stop requests and be handled by refreshing an authorized session or running locally/self-hosted—not by rotating sessions to bypass a restriction.
3. **Captions are not guaranteed for every video.** Videos with unavailable captions, access restrictions, deletion, or other limitations can remain unresolved and must be tracked rather than counted as completed.
4. **ZIP behavior is covered by unit tests and CI.** The live-test workflow also packages the completed channel output into its artifact for easy downloading.

## Recommended verification links

- [Latest live-test workflow](https://github.com/therandomhuman-hub/Youtube_Transcript_Extractor/actions/runs/37956540873)
- [Live-test ZIP/results artifact](https://github.com/therandomhuman-hub/Youtube_Transcript_Extractor/actions/runs/37956540873/artifacts/11632157521)
- [Repository Actions](https://github.com/therandomhuman-hub/Youtube_Transcript_Extractor/actions)
