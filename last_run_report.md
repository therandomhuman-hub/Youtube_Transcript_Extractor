# YouTube Transcript Archive — Run Report

- **Run ID:** 38160639084
- **Run status:** RUN_SUCCEEDED_BACKFILL_INCOMPLETE
- **Workflow step outcome:** success
- **Started (UTC):** 2026-10-11T17:40:55+00:00
- **Finished/finalized (UTC):** 2026-10-11T19:16:52+00:00

## Run totals

| Metric | Value |
|---|---:|
| Configured channels | 18 |
| Channels checked/reported | 18 |
| Completed channels | 9 |
| In-progress channels | 9 |
| Channels with errors | 0 |
| Authentication-blocked channels | 0 |
| Channels not reached in this run | 0 |
| Transcript attempts in this run | 108 |
| Transcripts saved in this run | 108 |
| No-caption outcomes recorded in this run snapshot | 7 |

> **Run note:** The collection step exited successfully, but the full backfill is not complete: 9 channel(s) remain in progress and 0 configured channel(s) were not reached. Checkpointed work will resume in a later scheduled run.

## Per-channel results

| Channel | Status | Saved / known | No captions | Unresolved | Attempted | Folder |
|---|---|---:|---:|---:|---:|---|
| [One Person Business](https://www.youtube.com/@One-Person-Business) | COMPLETED | 123 / 124 | 1 | 0 | 0 | `completed/One Person Business` |
| [Jad M.H  \| AI Automation](https://www.youtube.com/@JadM.H) | COMPLETED | 185 / 186 | 1 | 0 | 0 | `completed/Jad M.H _ AI Automation` |
| [Jason Wardrop](https://www.youtube.com/@JasonWardrop) | COMPLETED | 325 / 326 | 1 | 0 | 0 | `completed/Jason Wardrop` |
| [Tim Danilov Biz](https://www.youtube.com/@timdanilovhi) | COMPLETED | 110 / 110 | 0 | 0 | 0 | `completed/Tim Danilov Biz` |
| [Everygen AI](https://www.youtube.com/@EverygenAI) | COMPLETED | 4 / 4 | 0 | 0 | 0 | `completed/Everygen AI` |
| [Deven Seenath](https://www.youtube.com/@DevenSeenath) | IN_PROGRESS | 172 / 732 | 0 | 560 | 12 | `Deven Seenath` |
| [AIpreneur](https://www.youtube.com/@AIpreneur2176) | IN_PROGRESS | 53 / 55 | 1 | 1 | 12 | `AIpreneur` |
| [Joshua Elder](https://www.youtube.com/@JoshuaElderLive) | IN_PROGRESS | 50 / 1737 | 0 | 1687 | 12 | `Joshua Elder` |
| [Isaac](https://www.youtube.com/@isaacverse) | COMPLETED | 9 / 9 | 0 | 0 | 0 | `completed/Isaac` |
| [Shawn Builds AI](https://www.youtube.com/@shawnbuildsai) | IN_PROGRESS | 48 / 67 | 0 | 19 | 12 | `Shawn Builds AI` |
| [E'Calm](https://www.youtube.com/@emmiescalm) | COMPLETED | 32 / 32 | 0 | 0 | 0 | `completed/E'Calm` |
| [Airyzen AI](https://www.youtube.com/@airyzenai) | COMPLETED | 26 / 26 | 0 | 0 | 0 | `completed/Airyzen AI` |
| [Udo Onyekwere](https://www.youtube.com/@udo_dagreat) | IN_PROGRESS | 48 / 63 | 0 | 15 | 12 | `Udo Onyekwere` |
| [Victor Bigbro](https://www.youtube.com/@VictorBigbro) | IN_PROGRESS | 48 / 86 | 0 | 38 | 12 | `Victor Bigbro` |
| [Jack Neel](https://www.youtube.com/@jackneel) | IN_PROGRESS | 48 / 991 | 0 | 943 | 12 | `Jack Neel` |
| [Bahaa AI](https://www.youtube.com/@BahaaAI) | COMPLETED | 30 / 33 | 3 | 0 | 0 | `completed/Bahaa AI` |
| [Learn with Lukas](https://www.youtube.com/@learnwithlukas) | IN_PROGRESS | 48 / 328 | 0 | 280 | 12 | `Learn with Lukas` |
| [Sunny Lenarduzzi](https://www.youtube.com/@SunnyLenarduzzi) | IN_PROGRESS | 48 / 562 | 0 | 514 | 12 | `Sunny Lenarduzzi` |

## Interpretation

Run completion and channel backfill completion are different. A channel marked `IN_PROGRESS` still has unresolved items even if the scheduled run itself succeeded.
An explicit `NO_CAPTIONS` outcome is auditable and may satisfy the channel completion rule, but it is not counted as a saved transcript.
