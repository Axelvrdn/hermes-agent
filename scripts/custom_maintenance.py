"""Non-mutating rebase probe and opt-in, sequential live promotion for the custom fork."""

import argparse
import json
import re
import shlex
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def _git(repo, *args, check=True):
    return subprocess.run(['git', '-C', str(repo), *map(str, args)], text=True, encoding='utf-8',
                          errors='replace', timeout=120,
                          capture_output=True, check=check)


def _sha(repo, ref):
    return _git(repo, 'rev-parse', '--verify', f'{ref}^{{commit}}').stdout.strip()


def _run_checks(worktree, tests):
    for command in tests:
        result = subprocess.run(command, cwd=worktree, shell=True, timeout=1800,
                                text=True, encoding='utf-8', errors='replace',
                                capture_output=True, check=False)
        if result.returncode:
            return f'{command}: {(result.stdout + result.stderr)[-6000:]}'
    return None


def validate_rebase(repo, custom, upstream, report, *, tests=()):
    """Replay in a disposable worktree; never move the source refs."""
    repo = Path(repo).resolve()
    custom_sha, upstream_sha = _sha(repo, custom), _sha(repo, upstream)
    report = Path(report)
    with tempfile.TemporaryDirectory(prefix='custom-rebase-') as temp:
        worktree = Path(temp) / 'probe'
        _git(repo, 'worktree', 'add', '--detach', worktree, custom_sha)
        try:
            result = _git(worktree, 'rebase', '--no-gpg-sign', '--no-autostash',
                          '--onto', upstream_sha, _git(repo, 'merge-base', custom_sha, upstream_sha).stdout.strip(),
                          check=False)
            conflicts = _git(worktree, 'diff', '--name-only', '--diff-filter=U').stdout.splitlines()
            outcome = {'status': 'clean' if result.returncode == 0 else 'conflict',
                       'custom': custom_sha, 'upstream': upstream_sha,
                       'candidate': _sha(worktree, 'HEAD') if result.returncode == 0 else None,
                       'conflicts': conflicts,
                       'details': (result.stdout + result.stderr)[-6000:] if result.returncode else ''}
            if result.returncode == 0:
                failure = _run_checks(worktree, tests)
                outcome['tests_passed'] = failure is None
                if failure:
                    outcome.update(status='tests_failed', details=failure)
            if result.returncode:
                _git(worktree, 'rebase', '--abort', check=False)
        finally:
            _git(repo, 'worktree', 'remove', '--force', worktree)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(outcome, indent=2) + '\n', encoding='utf-8')
    return outcome


def promote(repo, candidate, backup, *, apply=False, tests=()):
    """Backup and fast-forward an explicit candidate, without restarting anything."""
    repo, backup = Path(repo).resolve(), Path(backup).resolve()
    if _git(repo, 'status', '--porcelain').stdout.strip():
        raise RuntimeError('live checkout is not clean')
    old, new = _sha(repo, 'HEAD'), _sha(repo, candidate)
    if _git(repo, 'merge-base', '--is-ancestor', old, new, check=False).returncode:
        raise RuntimeError('candidate is not a fast-forward of live HEAD')
    result = {'original': old, 'candidate': new}
    if not apply:
        return result
    # Exercise the candidate outside the live checkout before touching it.
    with tempfile.TemporaryDirectory(prefix='custom-promote-check-') as temp:
        worktree = Path(temp) / 'candidate'
        _git(repo, 'worktree', 'add', '--detach', worktree, new)
        try:
            failure = _run_checks(worktree, tests)
        finally:
            _git(repo, 'worktree', 'remove', '--force', worktree)
    if failure:
        raise RuntimeError(f'test command failed: {failure}')
    if backup.exists():
        raise RuntimeError('backup directory already exists')
    backup.mkdir(parents=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    tag = f'axel-deploy-backup-{stamp}-{old[:12]}'
    if not re.fullmatch(r'[0-9a-f]{40,64}', old):
        raise RuntimeError('invalid git commit')
    bundle = backup / 'before.bundle'
    rollback = backup / 'rollback.sh'
    _git(repo, 'tag', tag, old)
    _git(repo, 'bundle', 'create', bundle, tag, new)
    _git(repo, 'bundle', 'verify', bundle)
    rollback.write_text('#!/bin/sh\nset -eu\ncd ' + shlex.quote(str(repo)) +
                        '\ntest "$(git rev-parse HEAD)" = "' + new + '" || { echo "unexpected HEAD; refusing rollback" >&2; exit 1; }\n'
                        'test -z "$(git status --porcelain)" || { echo "dirty checkout; refusing rollback" >&2; exit 1; }\n'
                        'git switch --detach ' + old + '\n', encoding='utf-8')
    rollback.chmod(0o700)
    result.update(tag=tag, bundle=str(bundle), rollback=str(rollback))
    _git(repo, 'merge-base', '--is-ancestor', old, new)
    _git(repo, 'switch', '--detach', new)
    if _sha(repo, 'HEAD') != new:
        raise RuntimeError('promotion verification failed; use generated rollback')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    probe = sub.add_parser('validate')
    probe.add_argument('--repo', default='.')
    probe.add_argument('--custom', default='origin/axel-custom')
    probe.add_argument('--upstream', default='upstream/main')
    probe.add_argument('--report', required=True)
    probe.add_argument('--test', action='append', default=[])
    deploy = sub.add_parser('promote')
    deploy.add_argument('--repo', required=True)
    deploy.add_argument('--candidate', required=True)
    deploy.add_argument('--backup', required=True)
    deploy.add_argument('--apply', action='store_true')
    deploy.add_argument('--test', action='append', default=[])
    args = parser.parse_args()
    if args.action == 'validate':
        result = validate_rebase(args.repo, args.custom, args.upstream, args.report, tests=args.test)
        print(json.dumps(result, indent=2))
        raise SystemExit(0 if result['status'] == 'clean' else 1)
    print(json.dumps(promote(args.repo, args.candidate, args.backup,
                             apply=args.apply, tests=args.test), indent=2))


if __name__ == '__main__':
    main()
