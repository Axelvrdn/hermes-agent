# Upstream maintenance and explicit deployment

`axel-custom` is the integration branch; the live checkout at `/home/axel/.hermes/hermes-agent` is never changed by CI. The scheduled GitHub workflow (`.github/workflows/axel-custom-upstream.yml`) checks drift every Monday, and also validates pushes to `axel-custom` or manual dispatches. It fetches current official `main`, rebases in a disposable worktree, runs the calendar/Discord custom contracts and `python scripts/check` on the rebased candidate, uploads a JSON conflict/check report, and leaves every branch untouched. A failure is not a force-push request: inspect the report, resolve conflicts in a development worktree, rerun tests, and review before updating `axel-custom`. **GitHub scheduled workflows run only from the repository default branch**: merge the workflow onto the fork's default `main` to activate the schedule. It checks out `axel-custom` explicitly.

Scheduled reports post status and the Actions report link to the Discord **inbox** via the `DISCORD_INBOX_WEBHOOK_URL` GitHub Actions secret. Create an incoming webhook specifically in that channel and store its URL as a repository Actions secret; do not commit or print the webhook URL. Missing secret fails the notification job. Workflow dispatches and pushes do not post to Discord. The CI job has read-only repository permission and no branch update permission. GitHub Actions results and the uploaded JSON artifact are the conflict report; no automatic merge, deploy, or service restart occurs.

Local probe (fetch and check only; fetch affects development refs, not live):

```sh
git fetch upstream main
git fetch origin axel-custom
python scripts/custom_maintenance.py validate --repo . --custom origin/axel-custom \
  --upstream upstream/main --report /path/outside-repo/report.json \
  --test 'scripts/run_tests.sh tests/cron/test_calendar_approvals.py tests/cron/test_discord_cron_authorization.py tests/gateway/test_discord_cron_authorization_buttons.py tests/scripts/test_custom_maintenance.py' \
  --test 'python scripts/check'
```

## Manual tagged deployment (operator only)

Promote only after reviewing a validated SHA in development. The promotion script refuses dirty live trees and non-fast-forward candidates; it runs operator-supplied tests in a disposable worktree of the candidate. Dry-run is default and makes no backups or mutations. On explicit `--apply`, it creates a tag, a verified Git bundle, and a rollback script **before** switching the live checkout to a detached exact SHA. It checks the final HEAD; it does not install dependencies or restart the gateway. Supply a unique backup path outside the checkout on each run. A rebased SHA that is not descendant of live HEAD needs a separately reviewed manual migration; the script intentionally refuses it rather than rewriting history.

```sh
LIVE=/home/axel/.hermes/hermes-agent
BACKUP=/path/outside-live/deployments/unique-deployment-id
SHA=<reviewed-and-validated-full-commit-sha>
python scripts/custom_maintenance.py promote --repo "$LIVE" --candidate "$SHA" --backup "$BACKUP" \
  --test 'scripts/run_tests.sh tests/cron/test_calendar_approvals.py tests/cron/test_discord_cron_authorization.py tests/gateway/test_discord_cron_authorization_buttons.py'
# After examining dry-run output and obtaining deployment authorization:
python scripts/custom_maintenance.py promote --repo "$LIVE" --candidate "$SHA" --backup "$BACKUP" \
  --test 'scripts/run_tests.sh tests/cron/test_calendar_approvals.py tests/cron/test_discord_cron_authorization.py tests/gateway/test_discord_cron_authorization_buttons.py' --apply
# Check output SHA/tag/bundle and perform dependency sync/restart separately under supervision.
```

Rollback is explicit: inspect the emitted `rollback.sh`, verify it names the correct checkout and previous SHA, then execute it from an external shell (`sh "$BACKUP/rollback.sh"`). It refuses an unexpected HEAD or dirty checkout. It switches to the old detached SHA; synchronize dependencies and restart the gateway separately under supervision. The bundle preserves the original commit even if branch refs move later. Never run promotion from a gateway process that it would need to restart itself.
