# Customization changelog

All notable changes carried by Axel's Hermes fork are documented here. Dates use UTC.

### 2026-10-09

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
