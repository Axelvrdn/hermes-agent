# Customization changelog

All notable changes carried by Axel's Hermes fork are documented here. Dates use UTC.

### 2026-10-09

### Planned: Contextual conversation initialization (Turn 1)

- Planned automatic context recovery on new Discord conversations:
  - Multi-signal detection from the initial user prompt, channel/thread title, and Discord forum tags (`applied_tags`).
  - Pre-turn context retrieval combining Obsidian vault notes (MCP) and past session history (`session_search` / `state.db`).
  - Clean prologue injection preserving role alternation and prefix prompt caching.

### Generic deterministic cron actions

- Added a typed `discord_cron_actions` delivery contract.
- Added a reusable `Relancer` button to continuable Discord cron deliveries.
- The rerun click calls `cron.jobs.trigger_job()` directly and never creates an LLM interaction turn.
- Calendar requests are persisted as profile-local JSON records under `cron/pending_approvals/`.
- Calendar `Autoriser` / `Refuser` clicks now execute `scripts/resolve_cron_calendar_approval.py` instead of reinjecting a chat message into an agent session.
- Authorization checks Google Calendar conflicts, creates the exact stored event, reads it back, and records its event ID; refusal remains fully local.
- Added deterministic tests for parsing, persistence, conflict failure, creation verification, generic actions, authorization and no-LLM dispatch.

### Discord cron in-channel surface and explicit delivery buttons

- Fixed `CronCalendarApprovalView` so action buttons are materialized as real `discord.ui.Button` children via `add_item()`.
- Allowed explicit Discord channel targets (`deliver: discord:<channel_id>`) attached to a session to inherit the trusted origin user and attach authorization buttons.
- Enabled `supports_inchannel_continuable = True` on `DiscordAdapter` so Discord can honor `cron_continuable_surface: in_channel` and post directly to inbox channels without opening a thread.
- Added regression tests covering Discord button child materialization, explicit target approval attachment, and in-channel delivery without thread creation.


### Repository foundation

- Created the GitHub fork `Axelvrdn/hermes-agent`.
- Created a separate development checkout at `/home/axel/projects/hermes-agent-custom`.
- Added remotes for official upstream and `FRFlo/hermes-agent`.
- Established `axel-custom` as the maintained integration branch based on current upstream `main`.

### Discord cron calendar approvals

- Ported the existing local commit onto current upstream.
- Resolved the scheduler metadata conflict by preserving current upstream origin-discriminator handling and adding the Discord authorization metadata afterward.
- Verified 6 targeted tests across 2 test files.

### FRFlo reference branches

Pinned for analysis:

- `frflo/discord-improvements` — adapter decomposition.
- `frflo/discord-modernisation-messages` — Discord Components V2 compatibility layer.
- `frflo/discord-message-session-sync` — message edit/delete session reconciliation.

These branches are historical design inputs, not branches to merge wholesale. Their base predates many current upstream changes.

### FRFlo porting analysis

- Documented the five Discord commits in `FRFLO-DISCORD-PORTING.md`.
- Confirmed that the final FRFlo session-rewind schema consistently uses `target_message`.
- Chose progressive redesign over a wholesale merge: limited adapter extraction, incremental Components V2, then opt-in message/session synchronization with persistent per-generation correlation.
