# YouTube Transcript Archive — Run Report

- **Run ID:** 38512637386
- **Run status:** RUN_SUCCEEDED_BACKFILL_INCOMPLETE
- **Workflow step outcome:** success
- **Started (UTC):** 2026-10-14T04:41:07+00:00
- **Finished/finalized (UTC):** 2026-10-14T05:40:38+00:00

## Run totals

| Metric | Value |
|---|---:|
| Configured channels | 20 |
| Channels checked/reported | 20 |
| Completed channels | 15 |
| In-progress channels | 5 |
| Channels with errors | 0 |
| Authentication-blocked channels | 0 |
| Channels not reached in this run | 0 |
| Transcript attempts in this run | 61 |
| Transcripts saved in this run | 60 |
| No-caption outcomes recorded in this run snapshot | 10 |

> **Run note:** The collection step exited successfully, but the full backfill is not complete: 5 channel(s) remain in progress and 0 configured channel(s) were not reached. Checkpointed work will resume in a later scheduled run.

## Per-channel results

| Channel | Status | Saved / known | No captions | Unresolved | Attempted | Folder |
|---|---|---:|---:|---:|---:|---|
| [One Person Business](https://www.youtube.com/@One-Person-Business) | COMPLETED | 123 / 124 | 1 | 0 | 0 | `completed/One Person Business` |
| [Jad M.H  \| AI Automation](https://www.youtube.com/@JadM.H) | COMPLETED | 189 / 190 | 1 | 0 | 0 | `completed/Jad M.H _ AI Automation` |
| [Jason Wardrop](https://www.youtube.com/@JasonWardrop) | COMPLETED | 326 / 327 | 1 | 0 | 0 | `completed/Jason Wardrop` |
| [Tim Danilov Biz](https://www.youtube.com/@timdanilovhi) | COMPLETED | 111 / 111 | 0 | 0 | 0 | `completed/Tim Danilov Biz` |
| [Everygen AI](https://www.youtube.com/@EverygenAI) | COMPLETED | 4 / 5 | 1 | 0 | 0 | `completed/Everygen AI` |
| [Deven Seenath](https://www.youtube.com/@DevenSeenath) | IN_PROGRESS | 268 / 732 | 0 | 464 | 12 | `Deven Seenath` |
| [AIpreneur](https://www.youtube.com/@AIpreneur2176) | COMPLETED | 55 / 56 | 1 | 0 | 0 | `completed/AIpreneur` |
| [Joshua Elder](https://www.youtube.com/@JoshuaElderLive) | IN_PROGRESS | 146 / 1737 | 0 | 1591 | 12 | `Joshua Elder` |
| [Isaac](https://www.youtube.com/@isaacverse) | COMPLETED | 9 / 9 | 0 | 0 | 0 | `completed/Isaac` |
| [Shawn Builds AI](https://www.youtube.com/@shawnbuildsai) | COMPLETED | 68 / 68 | 0 | 0 | 0 | `completed/Shawn Builds AI` |
| [E'Calm](https://www.youtube.com/@emmiescalm) | COMPLETED | 32 / 32 | 0 | 0 | 0 | `completed/E'Calm` |
| [Airyzen AI](https://www.youtube.com/@airyzenai) | COMPLETED | 26 / 26 | 0 | 0 | 0 | `completed/Airyzen AI` |
| [Udo Onyekwere](https://www.youtube.com/@udo_dagreat) | COMPLETED | 63 / 63 | 0 | 0 | 0 | `completed/Udo Onyekwere` |
| [Victor Bigbro](https://www.youtube.com/@VictorBigbro) | COMPLETED | 85 / 86 | 1 | 0 | 0 | `completed/Victor Bigbro` |
| [Jack Neel](https://www.youtube.com/@jackneel) | IN_PROGRESS | 144 / 1000 | 0 | 856 | 12 | `Jack Neel` |
| [Bahaa AI](https://www.youtube.com/@BahaaAI) | COMPLETED | 31 / 34 | 3 | 0 | 0 | `completed/Bahaa AI` |
| [Learn with Lukas](https://www.youtube.com/@learnwithlukas) | IN_PROGRESS | 144 / 331 | 0 | 187 | 12 | `Learn with Lukas` |
| [Sunny Lenarduzzi](https://www.youtube.com/@SunnyLenarduzzi) | IN_PROGRESS | 143 / 563 | 1 | 419 | 12 | `Sunny Lenarduzzi` |
| [Alex](https://www.youtube.com/@alexpdfbusiness) | COMPLETED | 49 / 49 | 0 | 0 | 1 | `completed/Alex` |
| [Money Guy](https://www.youtube.com/@IamMoneyGuy) | COMPLETED | 42 / 42 | 0 | 0 | 0 | `completed/Money Guy` |

## Interpretation

Run completion and channel backfill completion are different. A channel marked `IN_PROGRESS` still has unresolved items even if the scheduled run itself succeeded.
An explicit `NO_CAPTIONS` outcome is auditable and may satisfy the channel completion rule, but it is not counted as a saved transcript.
