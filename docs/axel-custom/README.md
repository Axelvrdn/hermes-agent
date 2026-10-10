# Axel's Hermes fork

This fork keeps local Hermes improvements reviewable, testable, and easy to rebase onto `NousResearch/hermes-agent`.

## Repository model

- `upstream`: official Hermes repository.
- `origin`: `Axelvrdn/hermes-agent`, the durable backup and collaboration fork.
- `frflo`: `FRFlo/hermes-agent`, used as a source of Discord design ideas.
- `main`: mirrors upstream; do not put local changes directly on it.
- `axel-custom`: integration branch containing the changes intended for Axel's Hermes deployment.
- Feature branches: one focused change each, merged or cherry-picked into `axel-custom` after tests.

A GitHub fork is created once. Regular protection comes from pushing branches/tags and synchronizing them, not from creating repeated forks.

## Current customization

### Discord calendar approval buttons

Commit: `480ad3997e` (`feat(discord): add cron calendar approval buttons`)

A cron result may end with this reserved final line:

```text
[HERMES_DISCORD_CALENDAR_CONFIRM_V1:REV-<opaque-id>]
```

For an authenticated Discord origin, Hermes removes the marker from the visible message and adds **Autoriser** / **Refuser** buttons to the last Discord fragment. A click is injected through the normal authenticated inbound-message path; the marker contains no calendar arguments or personal data.

Tests:

```bash
scripts/run_tests.sh \
  tests/cron/test_discord_cron_authorization.py \
  tests/gateway/test_discord_cron_authorization_buttons.py
```

## Porting policy

1. Reproduce the behavior on current upstream before changing code.
2. Prefer plugins, skills, MCP servers, and existing extension seams over core patches.
3. Keep each core modification in an isolated commit with behavior-contract tests.
4. Rebase `axel-custom` onto `upstream/main`; never merge a stale feature branch over newer upstream code.
5. Run targeted tests, then `python scripts/check`, then the relevant broader test directory.
6. Deploy to the live installation only after review and a rollback point.
7. Record every deployed customization in `docs/axel-custom/CHANGELOG.md`.

## Safe update workflow

```bash
git fetch --prune upstream origin frflo
git switch axel-custom
git rebase upstream/main
scripts/run_tests.sh \
  tests/cron/test_discord_cron_authorization.py \
  tests/gateway/test_discord_cron_authorization_buttons.py
git push --force-with-lease origin axel-custom
```

`--force-with-lease` is required after a rebase. It refuses to overwrite remote work that was not fetched locally.

## Deployment rule

The development checkout is `/home/axel/projects/hermes-agent-custom`. The running installation is `/home/axel/.hermes/hermes-agent`. Development and rebases happen in the former. Updating the running installation is a separate, explicit deployment step. For scheduled drift checks, report routing to the Discord inbox, tagged backups, safe promotion, and rollback, see [UPSTREAM-DEPLOYMENT.md](UPSTREAM-DEPLOYMENT.md).

## Integration direction

- **Discord:** interaction components, cron continuation, message/session reconciliation, media and voice UX.
- **Voicebox:** prefer a service-gated plugin or MCP integration that detects the local service and exposes narrow synthesis/voice-management operations.
- **ComfyUI:** prefer a plugin/skill around its HTTP/WebSocket API, with workflow templates, job polling, artifact delivery, and strict allowed output directories.
- **External services:** no credentials in Git; configuration in `config.yaml`, secrets in the profile `.env`, and profile-aware paths via `get_hermes_home()`.
