"""Regression tests for the subprocess runner (no optional deps)."""
import pathlib
import sys

# Run under pytest from repository root.
from engine.sandbox import execute_user_code


def test_sandbox_success_unicode_roundtrip():
    ok, result = execute_user_code(
        "def entry(value):\n    return {'ответ': value + ' ✅'}\n",
        "entry", {"value": "Проверка"}, timeout=5,
    )
    assert ok, result
    assert result == {"ответ": "Проверка ✅"}


def test_sandbox_user_exception_returns_error_without_file_not_found():
    ok, result = execute_user_code(
        "def entry():\n    raise RuntimeError('Ошибка в процедуре')\n",
        "entry", {}, timeout=5,
    )
    assert not ok
    assert "RuntimeError" in result["error"]
    assert "FileNotFoundError" not in result["error"]


def test_sandbox_exit_without_result_is_reported():
    ok, result = execute_user_code(
        "import os\ndef entry():\n    os._exit(0)\n",
        "entry", {}, timeout=5,
    )
    assert not ok
    assert "without producing" in result["error"]


def test_sandbox_timeout_is_reported():
    ok, result = execute_user_code(
        "import time\ndef entry():\n    time.sleep(5)\n",
        "entry", {}, timeout=1,
    )
    assert not ok
    assert "timeout>1s" == result["error"]


def test_sandbox_python_object_argument():
    ok, result = execute_user_code(
        "def entry(values):\n    return {'sorted': sorted(values)}\n",
        "entry", {"values": {2, 1}}, timeout=5,
    )
    assert ok, result
    assert result["sorted"] == [1, 2]


def test_sandbox_unpicklable_payload_becomes_error():
    ok, result = execute_user_code(
        "def entry(callback):\n    return 1\n",
        "entry", {"callback": lambda: None}, timeout=5,
    )
    assert not ok
    assert "Cannot serialize" in result["error"]
