"""Исполнение пользовательского кода в subprocess с таймаутом.

Контракт процедуры/проверки: модуль с одной из функций:
  - step_<name>(*args, **kwargs)  для override шага
  - check(mart, params)           для проверки
  - entry(mart, params)           универсальная точка входа
"""
from __future__ import annotations
import json, subprocess, sys, tempfile, textwrap, pathlib, os, time

_TIMEOUT_DEFAULT = 30

RUNNER = textwrap.dedent("""
import json, sys, pathlib, importlib.util
code_path, entry, payload_path, out_path = sys.argv[1:5]
spec = importlib.util.spec_from_file_location("usermod", code_path)
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
payload = json.loads(pathlib.Path(payload_path).read_text())
fn = getattr(mod, entry)
result = fn(**payload)
pathlib.Path(out_path).write_text(json.dumps(result, default=str))
""")

def execute_user_code(code: str, entry: str, payload: dict, timeout: int = _TIMEOUT_DEFAULT):
    """Возвращает (ok: bool, result|error: dict)."""
    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td)
        code_p = td / "usermod.py"
        payload_p = td / "payload.json"
        out_p = td / "out.json"
        code_p.write_text(code)
        payload_p.write_text(json.dumps(payload, default=str))
        try:
            proc = subprocess.run(
                [sys.executable, "-c", RUNNER, str(code_p), entry, str(payload_p), str(out_p)],
                capture_output=True, timeout=timeout, env={**os.environ, "PYTHONHASHSEED": "0"},
            )
        except subprocess.TimeoutExpired:
            return False, {"error": f"timeout>{timeout}s"}
        if proc.returncode != 0:
            return False, {"error": proc.stderr.decode()[-4000:]}
        return True, json.loads(out_p.read_text())