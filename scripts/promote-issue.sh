#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat << 'USAGE'
Usage:
  scripts/promote-issue.sh <issue_number> [--apply]

Exemples:
  scripts/promote-issue.sh 1          # Dry-run et vérifications
  scripts/promote-issue.sh 1 --apply  # Sauvegarde, bundle, tests et déploiement live
USAGE
  exit 1
}

if [ $# -lt 1 ]; then
  usage
fi

ISSUE_NUM="$1"
APPLY_FLAG=""
if [ "${2:-}" = "--apply" ]; then
  APPLY_FLAG="--apply"
fi

case "$ISSUE_NUM" in
  1) SLUG="upstream-sync" ;;
  2) SLUG="discord-modularize" ;;
  3) SLUG="discord-components-v2" ;;
  4) SLUG="discord-message-sync" ;;
  5) SLUG="voicebox-integration" ;;
  6) SLUG="comfyui-integration" ;;
  7) SLUG="context-turn1" ;;
  8) SLUG="discord-modals-obsidian" ;;
  *)
    echo "Numéro d'issue inconnu: $ISSUE_NUM (attendu: 1 à 8)" >&2
    exit 1
    ;;
esac

BRANCH="axel/issue-${ISSUE_NUM}-${SLUG}"
REPO_DEV="/home/axel/projects/hermes-agent-custom"
REPO_LIVE="/home/axel/.hermes/hermes-agent"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_DIR="/home/axel/.hermes/backups/deployments/promote-issue-${ISSUE_NUM}-${TIMESTAMP}"

echo "=== Promotion pour l'issue #${ISSUE_NUM} (${BRANCH}) ==="
echo "Dépôt dev : $REPO_DEV"
echo "Dépôt live : $REPO_LIVE"

# 1. Vérifier la présence du commit
CANDIDATE_SHA="$(git -C "$REPO_DEV" rev-parse --verify "refs/heads/$BRANCH^{commit}")"
echo "Commit candidat : $CANDIDATE_SHA"

# 2. Synchroniser le commit candidat dans le dépôt live
git -C "$REPO_LIVE" fetch "$REPO_DEV" "$BRANCH:refs/remotes/dev/$BRANCH"

# 3. Lancer la promotion avec vérification, tests et rollback automatique
python3 "$REPO_DEV/scripts/custom_maintenance.py" promote \
  --repo "$REPO_LIVE" \
  --candidate "$CANDIDATE_SHA" \
  --backup "$BACKUP_DIR" \
  $APPLY_FLAG \
  --test 'scripts/run_tests.sh tests/cron/test_calendar_approvals.py tests/cron/test_discord_cron_authorization.py tests/gateway/test_discord_cron_authorization_buttons.py'

if [ -n "$APPLY_FLAG" ]; then
  echo "✓ Déploiement réussi sur $REPO_LIVE vers $CANDIDATE_SHA"
  echo "✓ Sauvegarde et script de rollback disponibles dans : $BACKUP_DIR"
else
  echo "✓ Dry-run validé sans modification du live. Ajoute --apply pour déployer."
fi
