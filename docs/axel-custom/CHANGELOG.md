# Customization changelog

All notable changes carried by Axel's Hermes fork are documented here. Dates use UTC.

## 2026-10-09

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
