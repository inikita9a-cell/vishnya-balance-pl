"""Checks that the bridge preserves the platform API without serializing Mart."""
from pathlib import Path
from types import SimpleNamespace
import json

import pytest

from engine.platform_checks_adapter import run_checks, _normalize_check_ids


def test_platform_check_list_conversion_and_defaults():
    assert len(_normalize_check_ids({})) == 5
    assert _normalize_check_ids({'checks': ['a', {'id': 'b', 'label': 'B'}]}) == ['a', 'b']
    assert _normalize_check_ids({'checks': []}) == []


def test_adapter_spawns_worker_with_serializable_run_dir(tmp_path, monkeypatch):
    output = tmp_path / 'checks.json'
    seen = {}

    def fake_subprocess_run(command, **kwargs):
        seen['command'] = command
        seen['cwd'] = kwargs['cwd']
        seen['text'] = kwargs['text']
        snap = json.loads(Path(command[command.index('--config') + 1]).read_text(encoding='utf-8'))
        assert snap['checks'] == ['ar_drop_by_product']
        assert 'mart' not in snap
        output.write_text('[]', encoding='utf-8')
        return SimpleNamespace(returncode=0, stderr='')

    monkeypatch.setattr('engine.platform_checks_adapter.subprocess.run', fake_subprocess_run)
    result = run_checks({'cfg': {'checks': ['ar_drop_by_product']}, 'run_dir': str(tmp_path)})
    assert result == str(output)
    assert seen['command'][1:3] == ['-m', 'engine.run_checks']
    assert seen['text'] is True


def test_workspace_check_is_staged_without_fake_pass(tmp_path, monkeypatch):
    def fake_subprocess_run(command, **kwargs):
        checks_dir = Path(command[command.index('--checks-dir') + 1])
        code = (checks_dir / 'check_my_check.py').read_text(encoding='utf-8')
        assert 'def check(mart, params):' in code
        assert "'id': 'my_check'" not in code  # generated CHECK uses JSON-like dict with double quotes
        assert '"id": \'my_check\'' in code
        (tmp_path / 'checks.json').write_text('[]', encoding='utf-8')
        return SimpleNamespace(returncode=0, stderr='')

    monkeypatch.setattr('engine.platform_checks_adapter.subprocess.run', fake_subprocess_run)
    source = 'def check(mart, params):\n    return []\n'
    path = run_checks({'cfg': {'checks': [{'id': 'my_check', 'source': 'workspace',
                                             'code': source, 'label': 'Test'}]},
                       'run_dir': str(tmp_path)})
    assert path == str(tmp_path / 'checks.json')


def test_override_from_file_and_missing_file_error(tmp_path, monkeypatch):
    source = tmp_path / 'source.py'
    source.write_text('def check(mart, params):\n    return []\n', encoding='utf-8')
    def fake_subprocess_run(command, **kwargs):
        checks_dir = Path(command[command.index('--checks-dir') + 1])
        assert 'def check' in (checks_dir / 'check_my_check.py').read_text()
        (tmp_path / 'checks.json').write_text('[]', encoding='utf-8')
        return SimpleNamespace(returncode=0, stderr='')
    monkeypatch.setattr('engine.platform_checks_adapter.subprocess.run', fake_subprocess_run)
    state = {'cfg': {'checks': ['my_check'], 'overrides': {'checks/my_check': str(source)}},
             'run_dir': str(tmp_path)}
    run_checks(state)
    source.unlink()
    with pytest.raises(FileNotFoundError):
        run_checks(state)
