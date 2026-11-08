"""Atomic job updates survive transient Windows reader locks."""
import json

import pytest

from engine import check_jobs


def windows_lock(code):
    error = PermissionError('file is in use')
    error.winerror = code
    return error


@pytest.mark.parametrize('code', [5, 32, 33])
def test_transient_lock_keeps_previous_json_until_atomic_replace(tmp_path, monkeypatch, code):
    path = tmp_path / 'job.json'
    path.write_text('{"status": "queued"}', encoding='utf-8')
    replace = check_jobs.os.replace
    attempts, sleeps = [], []

    def locked(source, target):
        attempts.append(source)
        assert json.loads(source.read_text(encoding='utf-8')) == {'status': 'running'}
        assert json.loads(target.read_text(encoding='utf-8')) == {'status': 'queued'}
        if len(attempts) < 4:
            raise windows_lock(code)
        replace(source, target)

    monkeypatch.setattr(check_jobs.os, 'replace', locked)
    monkeypatch.setattr(check_jobs.time, 'sleep', sleeps.append)
    check_jobs._write_json(path, {'status': 'running'})
    assert json.loads(path.read_text(encoding='utf-8')) == {'status': 'running'}
    assert len(attempts) == 4
    assert sleeps == [0.01, 0.02, 0.04]
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize('code, expected_attempts', [(5, 12), (32, 12), (33, 12), (None, 1), (2, 1)])
def test_permanent_error_is_raised_and_temporary_file_cleaned(tmp_path, monkeypatch, code, expected_attempts):
    path = tmp_path / 'job.json'
    original = '{"status": "queued"}'
    path.write_text(original, encoding='utf-8')
    error = windows_lock(code)
    attempts, sleeps = [], []

    def denied(source, target):
        attempts.append(source)
        raise error

    monkeypatch.setattr(check_jobs.os, 'replace', denied)
    monkeypatch.setattr(check_jobs.time, 'sleep', sleeps.append)
    with pytest.raises(PermissionError) as caught:
        check_jobs._write_json(path, {'status': 'running'})
    assert caught.value is error
    assert len(attempts) == expected_attempts
    assert len(sleeps) == expected_attempts - 1
    assert sum(sleeps) < 2
    assert path.read_text(encoding='utf-8') == original
    assert list(tmp_path.iterdir()) == [path]


def test_publication_retries_reader_lock(tmp_path, monkeypatch):
    staged, root = tmp_path / 'staged', tmp_path / 'run'
    staged.mkdir()
    root.mkdir()
    for name in check_jobs.PUBLISHED:
        (staged / name).write_text('new', encoding='utf-8')
        (root / name).write_text('old', encoding='utf-8')
    replace = check_jobs.os.replace
    blocked = set()

    def locked(source, target):
        if target.name not in blocked:
            blocked.add(target.name)
            assert target.read_text(encoding='utf-8') == 'old'
            raise windows_lock(32)
        replace(source, target)

    monkeypatch.setattr(check_jobs.os, 'replace', locked)
    monkeypatch.setattr(check_jobs.time, 'sleep', lambda delay: None)
    check_jobs._publish(staged, root)
    assert blocked == set(check_jobs.PUBLISHED)
    assert all((root / name).read_text(encoding='utf-8') == 'new' for name in check_jobs.PUBLISHED)
