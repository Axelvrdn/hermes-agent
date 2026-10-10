"""Behavior contracts for custom fork maintenance (#1)."""
import subprocess
from pathlib import Path

import pytest

from scripts.custom_maintenance import validate_rebase, promote


def git(path, *args):
    return subprocess.check_output(['git', '-C', str(path), *args], text=True).strip()


def setup(tmp_path):
    repo = tmp_path / 'repo'
    repo.mkdir()
    subprocess.run(['git', 'init', '-q', str(repo)], check=True)
    git(repo, 'config', 'user.email', 'test@example.com')
    git(repo, 'config', 'user.name', 'Test')
    (repo / 'file').write_text('base\n')
    git(repo, 'add', 'file')
    git(repo, 'commit', '-qm', 'base')
    git(repo, 'branch', 'upstream')
    git(repo, 'branch', 'custom')
    return repo


def commit(repo, branch, text):
    git(repo, 'switch', '-q', branch)
    (repo / 'file').write_text(text)
    git(repo, 'commit', '-qam', text.strip())
    return git(repo, 'rev-parse', 'HEAD')


def test_validation_reports_conflict_without_moving_custom(tmp_path):
    repo = setup(tmp_path)
    custom = commit(repo, 'custom', 'custom\n')
    commit(repo, 'upstream', 'upstream\n')
    result = validate_rebase(repo, 'custom', 'upstream', tmp_path / 'report')
    assert result['status'] == 'conflict'
    assert 'file' in result['conflicts']
    assert git(repo, 'rev-parse', 'custom') == custom
    assert not (repo / '.git' / 'rebase-merge').exists()


def test_validation_clean_candidate_keeps_refs_unchanged(tmp_path):
    repo = setup(tmp_path)
    custom = commit(repo, 'custom', 'custom\n')
    git(repo, 'switch', '-q', 'upstream')
    upstream = git(repo, 'rev-parse', 'HEAD')
    result = validate_rebase(repo, 'custom', 'upstream', tmp_path / 'report.json')
    assert result['status'] == 'clean'
    assert result['candidate'] == custom
    assert git(repo, 'rev-parse', 'custom') == custom
    assert git(repo, 'rev-parse', 'upstream') == upstream
    assert (tmp_path / 'report.json').is_file()


def test_validation_runs_tests_on_rebased_candidate(tmp_path):
    repo = setup(tmp_path)
    git(repo, 'switch', '-q', 'custom')
    (repo / 'custom-file').write_text('ready')
    git(repo, 'add', 'custom-file')
    git(repo, 'commit', '-qm', 'custom feature')
    commit(repo, 'upstream', 'upstream\n')
    result = validate_rebase(repo, 'custom', 'upstream', tmp_path / 'report.json',
                             tests=['test -f custom-file', 'test "$(cat file)" = upstream'])
    assert result['status'] == 'clean'
    assert result['tests_passed'] is True
    assert git(repo, 'show', 'custom:file') == 'base'


def test_validation_reports_failed_candidate_test(tmp_path):
    repo = setup(tmp_path)
    result = validate_rebase(repo, 'custom', 'upstream', tmp_path / 'report.json', tests=['false'])
    assert result['status'] == 'tests_failed'
    assert result['tests_passed'] is False


def test_promotion_dry_run_does_not_touch_live(tmp_path):
    repo = setup(tmp_path)
    original = git(repo, 'rev-parse', 'HEAD')
    target = commit(repo, 'custom', 'candidate\n')
    git(repo, 'switch', '-q', 'upstream')
    backup = tmp_path / 'backup'
    result = promote(repo, 'custom', backup, apply=False)
    assert result['candidate'] == target
    assert git(repo, 'rev-parse', 'HEAD') == original
    assert not backup.exists()


def test_promotion_creates_verified_backup_and_rollback(tmp_path):
    repo = setup(tmp_path)
    original = git(repo, 'rev-parse', 'HEAD')
    target = commit(repo, 'custom', 'candidate\n')
    git(repo, 'switch', '-q', 'upstream')
    backup = tmp_path / 'backup'
    result = promote(repo, 'custom', backup, apply=True, tests=['test -f file'])
    assert git(repo, 'rev-parse', 'HEAD') == target
    assert git(repo, 'rev-parse', result['tag']) == original
    assert Path(result['bundle']).is_file()
    assert git(repo, 'bundle', 'verify', result['bundle'])
    rollback = Path(result['rollback'])
    assert rollback.is_file()
    subprocess.run(['sh', str(rollback)], check=True)
    assert git(repo, 'rev-parse', 'HEAD') == original


def test_promotion_rejects_non_fast_forward(tmp_path):
    repo = setup(tmp_path)
    commit(repo, 'custom', 'candidate\n')
    live = commit(repo, 'upstream', 'live\n')
    with pytest.raises(RuntimeError, match='fast-forward'):
        promote(repo, 'custom', tmp_path / 'backup', apply=True)
    assert git(repo, 'rev-parse', 'HEAD') == live
    assert not (tmp_path / 'backup').exists()


def test_failed_test_leaves_live_untouched(tmp_path):
    repo = setup(tmp_path)
    original = git(repo, 'rev-parse', 'HEAD')
    commit(repo, 'custom', 'candidate\n')
    git(repo, 'switch', '-q', 'upstream')
    with pytest.raises(RuntimeError, match='test command failed'):
        promote(repo, 'custom', tmp_path / 'backup', apply=True, tests=['false'])
    assert git(repo, 'rev-parse', 'HEAD') == original


def test_promotion_checks_candidate_not_old_checkout(tmp_path):
    repo = setup(tmp_path)
    git(repo, 'switch', '-q', 'custom')
    (repo / 'new-file').write_text('ok')
    git(repo, 'add', 'new-file')
    git(repo, 'commit', '-qm', 'new file')
    git(repo, 'switch', '-q', 'upstream')
    result = promote(repo, 'custom', tmp_path / 'backup', apply=True,
                     tests=['test -f new-file'])
    assert git(repo, 'rev-parse', 'HEAD') == result['candidate']
