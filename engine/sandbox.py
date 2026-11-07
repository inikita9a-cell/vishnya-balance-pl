"""Исполнение пользовательского кода в subprocess с таймаутом."""
from __future__ import annotations
import json, pickle, subprocess, sys, tempfile, textwrap, pathlib, os

_TIMEOUT_DEFAULT = 30

RUNNER = textwrap.dedent("""
import json, sys, pathlib, importlib.util, pickle
code_path, entry, payload_path, objs_path, out_path = sys.argv[1:6]
spec = importlib.util.spec_from_file_location("usermod", code_path)
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)

payload = json.loads(pathlib.Path(payload_path).read_text())
objs_path = pathlib.Path(objs_path)
objs = pickle.loads(objs_path.read_bytes()) if objs_path.stat().st_size else {}

fn = getattr(mod, entry)
result = fn(**payload, **objs)
pathlib.Path(out_path).write_text(json.dumps(result, default=str))
""")

def _is_jsonable(v) -> bool:
    try:
        json.dumps(v); return True
    except Exception:
        return False

def execute_user_code(code: str, entry: str, payload: dict, timeout: int = _TIMEOUT_DEFAULT):
    """payload: dict с аргументами. JSON-совместимые -> JSON; остальные -> pickle."""
    json_args, obj_args = {}, {}
    for k, v in payload.items():
        if _is_jsonable(v):
            json_args[k] = v
        else:
            obj_args[k] = v

    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td)
        (td / "usermod.py").write_text(code)
        (td / "payload.json").write_text(json.dumps(json_args, default=str))
        objs_path = td / "objs.pkl"
        objs_path.write_bytes(pickle.dumps(obj_args) if obj_args else b"")
        out_path = td / "out.json"

        try:
            proc = subprocess.run(
                [sys.executable, "-c", RUNNER,
                 str(td / "usermod.py"), entry,
                 str(td / "payload.json"), str(objs_path), str(out_path)],
                capture_output=True, timeout=timeout,
                env={**os.environ, "PYTHONHASHSEED": "0"},
            )
        except subprocess.TimeoutExpired:
            return False, {"error": f"timeout>{timeout}s"}

        if proc.returncode != 0:
            return False, {"error": proc.stderr.decode()[-4000:]}
        return True, json.loads(out_path.read_text())