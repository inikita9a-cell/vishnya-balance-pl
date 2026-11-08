"""Old owner-isolation cases explicitly exercise private mode, not launch defaults."""
import pytest


@pytest.fixture(autouse=True)
def explicit_private_policy(monkeypatch):
    monkeypatch.setenv('REPORT_ACCESS', 'private')
