"""Run trusted user-provided Python code in a timed subprocess.

IMPORTANT: this is NOT a security sandbox. The subprocess can access the
filesystem, environment and network as the application user.
"""
from __future__ import annotations

import json
import os
import pathlib
import pickle
import subprocess
import sys
import tempfile
import textwrap

_TIMEOUT_DEFAULT = 30

RUNNER = textwrap.dedent("""
import json, sys, pathlib, importlib.util, pickle
code_path, entry, payload_path, objs_path, out_path = sys.argv[1:6]
spec = importlib.util.spec_from_file_location("usermod", code_path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
payload = json.loads(pathlib.Path(payload_path).read_text(encoding="utf-8"))
objs_path = pathlib.Path(objs_path)
objs = pickle.loads(objs_path.read_bytes()) if objs_path.stat().st_size else {}
fn = getattr(mod, entry)
result = fn(**payload, **objs)
pathlib.Path(out_path).write_text(json.dumps(result, ensure_ascii=False, default=str), encoding="utf-8")
""")


def _is_jsonable(value) -> bool:
    try:
        json.dumps(value)
        return True
    except (TypeError, ValueError, OverflowError):
        return False


def execute_user_code(code: str, entry: str, payload: dict, timeout: int = _TIMEOUT_DEFAULT):
    """Return (ok, result_or_error), never trying to read missing result output."""
    if os.getenv("APP_ENV", "development") != "development":
        return False, {"error": "User Python execution is disabled in staging"}
    json_args, obj_args = {}, {}
    for name, value in payload.items():
        (json_args if _is_jsonable(value) else obj_args)[name] = value

    with tempfile.TemporaryDirectory() as dirname:
        td = pathlib.Path(dirname)
        code_path = td / "usermod.py"
        payload_path = td / "payload.json"
        objects_path = td / "objs.pkl"
        out_path = td / "out.json"
        code_path.write_text(code, encoding="utf-8")
        payload_path.write_text(json.dumps(json_args, ensure_ascii=False), encoding="utf-8")
        try:
            objects_path.write_bytes(pickle.dumps(obj_args) if obj_args else b"")
        except (pickle.PickleError, TypeError, AttributeError) as exc:
            return False, {"error": f"Cannot serialize user-code arguments: {exc}"}

        env = {**os.environ, "PYTHONHASHSEED": "0", "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
        try:
            proc = subprocess.run(
                [sys.executable, "-c", RUNNER, str(code_path), entry,
                 str(payload_path), str(objects_path), str(out_path)],
                capture_output=True,
                timeout=timeout,
                env=env,
            )
        except subprocess.TimeoutExpired:
            return False, {"error": f"timeout>{timeout}s"}
        except (OSError, ValueError) as exc:
            return False, {"error": f"subprocess failed: {exc}"}

        if proc.returncode != 0:
            err = proc.stderr.decode("utf-8", errors="replace")[-4000:]
            return False, {"error": err or f"process exited with status {proc.returncode}"}

        if not out_path.is_file():
            return False, {"error": "User code exited without producing a result"}
        try:
            return True, json.loads(out_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            return False, {"error": f"Failed to read user-code result: {exc}"}
