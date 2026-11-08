"""Smoke the closed production image, without datasets or credentials."""
import time
import urllib.request
import urllib.error
for attempt in range(60):
    try:
        assert urllib.request.urlopen("http://127.0.0.1:8000/healthz", timeout=2).status == 200
        break
    except Exception:
        time.sleep(1)
else:
    raise RuntimeError("Health check failed")
for path in ("/", "/api/me", "/api/login", "/docs", "/api/procedures/1/try"):
    try:
        urllib.request.urlopen("http://127.0.0.1:8000" + path, timeout=3)
    except urllib.error.HTTPError as exc:
        assert exc.code == 503, (path, exc.code)
    else:
        raise AssertionError("Staging unexpectedly open: " + path)
