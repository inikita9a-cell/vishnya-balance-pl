"""The platform's run_checks import must delegate to the real adapter."""
from pathlib import Path
import engine.platform_checks_adapter as adapter
from engine.checks_runner import run_checks


def test_platform_checks_runner_delegates_unchanged_state(monkeypatch, tmp_path):
    state = {'cfg': {'checks': ['ar_drop_by_product']}, 'run_dir': str(tmp_path)}
    seen = []

    def fake_adapter(received):
        seen.append(received)
        return str(Path(received['run_dir']) / 'checks.json')

    monkeypatch.setattr(adapter, 'run_checks', fake_adapter)
    assert run_checks(state) == str(tmp_path / 'checks.json')
    assert seen == [state]
