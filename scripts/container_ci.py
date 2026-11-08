"""Docker integration: closed default, authenticated same-origin, persistent volume."""
import base64
import hashlib
import json
import os
import re
import subprocess
import time
import urllib.request
import urllib.error
import uuid
suffix = uuid.uuid4().hex[:10]
name, volume = "sl-" + suffix, "sl-data-" + suffix
password = uuid.uuid4().hex
salt = os.urandom(16)
users = json.dumps({"ci": salt.hex()+":"+hashlib.scrypt(password.encode(),salt=salt,n=16384,r=8,p=1,dklen=32).hex()})
env = dict(os.environ, STAGING_USERS_JSON=users)
def docker(*args):
    return subprocess.check_output(["docker", *args], env=env, text=True).strip()
def get(path, authenticated=False):
    headers = {"Authorization": "Basic " + base64.b64encode(("ci:"+password).encode()).decode()} if authenticated else {}
    try:
        with urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8000"+path,headers=headers),timeout=3) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()
def start(auth):
    args = ["run", "-d", "--name", name, "-p", "127.0.0.1:8000:8000", "-v", volume+":/var/lib/strategylab"]
    if auth: args += ["-e", "STAGING_USERS_JSON", "-e", "APP_BASE_URL=https://demo.onrender.com"]
    docker(*args, "strategylab:ci")
    for _ in range(60):
        try:
            if get("/healthz")[0] == 200: return
        except OSError: pass
        time.sleep(1)
    raise RuntimeError("Container did not become healthy")
try:
    start(False)
    assert get("/")[0] == 503
    docker("rm", "-f", name)
    start(True)
    assert get("/")[0] == 401
    assert get("/api/me")[0] == 401
    assert get("/", True)[0] == 200
    for asset in re.findall(r'"(/assets/[^" ]+)"', get("/", True)[1].decode()):
        assert get(asset, True)[0] == 200
    assert json.loads(get("/api/me", True)[1])["name"] == "ci"
    assert get("/api/unknown", True)[0] == 404
    docker("exec", name, "python", "-c", "import sqlite3,pathlib; c=sqlite3.connect('/var/lib/strategylab/db/app.db'); c.execute('CREATE TABLE persistence_probe(value TEXT)'); c.execute(\"INSERT INTO persistence_probe VALUES ('retained')\"); c.commit(); pathlib.Path('/app/runs/probe.txt').write_text('result'); pathlib.Path('/app/data/probe.txt').write_text('dataset')")
    docker("rm", "-f", name)
    start(True)
    docker("exec", name, "python", "-c", "import sqlite3,pathlib; c=sqlite3.connect('/var/lib/strategylab/db/app.db'); assert c.execute('SELECT value FROM persistence_probe').fetchone()[0]=='retained'; assert pathlib.Path('/app/runs/probe.txt').read_text()=='result'; assert pathlib.Path('/app/data/probe.txt').read_text()=='dataset'")
    assert get("/", True)[0] == 200
finally:
    subprocess.run(["docker", "rm", "-f", name], check=False)
    subprocess.run(["docker", "volume", "rm", volume], check=False)
