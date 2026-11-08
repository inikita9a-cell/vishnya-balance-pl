"""Serve the built app from this PC, with named users and an HTTPS demo tunnel."""
from __future__ import annotations
import argparse
import getpass
import json
import os
from pathlib import Path
import queue
import re
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / '.local/web_server.json'


def setup(data_root=None):
    from backend.staging_access import password_hash
    config = json.loads(CONFIG.read_text(encoding='utf-8')) if CONFIG.is_file() else {}
    root = Path(data_root or config.get('data_root') or input('Dataset root (parent of RUN folders): ').strip()).resolve()
    if not root.is_dir():
        raise ValueError('Dataset root does not exist')
    users = config.get('users', {})
    print('Add personal accounts. Use your existing app name to keep config ownership.')
    print('Empty account name finishes setup. Empty password generates one to copy once.')
    while True:
        name = input('Account name: ').strip()
        if not name:
            break
        if not re.fullmatch(r'[^:\x00-\x1f\x7f]{1,64}', name):
            print('Use 1-64 characters without colon or control characters.'); continue
        password = getpass.getpass('Password (minimum 24 characters, or Enter to generate): ')
        if not password:
            password = secrets.token_urlsafe(24)
            print(f'Copy password for {name}: {password}')
        elif len(password) < 24:
            print('Password must contain at least 24 characters.'); continue
        salt = secrets.token_hex(16)
        users[name] = salt + ':' + password_hash(password, salt)
    if not users:
        raise ValueError('At least one personal account is required')
    config.update(data_root=str(root), users=users,
                  db_dir=config.get('db_dir', str((ROOT / 'db').resolve())))
    CONFIG.parent.mkdir(exist_ok=True)
    temporary = CONFIG.with_suffix('.tmp')
    temporary.write_text(json.dumps(config,ensure_ascii=False,indent=2),encoding='utf-8')
    try:
        temporary.chmod(0o600)
    except OSError:
        pass
    temporary.replace(CONFIG)
    print('Server configuration saved. Passwords are stored as scrypt hashes only.')


def child_env(config, origin):
    env = dict(os.environ)
    env.update(APP_ENV='staging', REPORT_ACCESS='shared',
               STAGING_USERS_JSON=json.dumps(config['users'],ensure_ascii=False),
               APP_BASE_URL=origin, FRONTEND_BASE_URL=origin, PUBLIC_ORIGIN=origin,
               DATA_DIR=config['data_root'], DB_DIR=config['db_dir'],
               STATIC_DIR=str(ROOT / 'frontend/dist'))
    return env


def build_frontend(install=True):
    npm = shutil.which('npm.cmd' if os.name == 'nt' else 'npm')
    if not npm:
        raise RuntimeError('Node.js/npm not found. Install Node.js LTS and reopen the terminal.')
    env = dict(os.environ)
    # Process env overrides even an old frontend/.env pointing at localhost.
    env['VITE_API_BASE_URL'] = ''
    if install:
        subprocess.run([npm,'ci'],cwd=ROOT/'frontend',env=env,check=True)
    subprocess.run([npm,'run','build'],cwd=ROOT/'frontend',env=env,check=True)


def tunnel_executable():
    executable = shutil.which('cloudflared')
    if executable:
        return executable
    local = ROOT / '.tools' / ('cloudflared.exe' if os.name == 'nt' else 'cloudflared')
    if local.is_file():
        return str(local)
    raise RuntimeError('Install cloudflared, or put the official executable in .tools/cloudflared.exe (see WEB_SERVER.md).')


def find_origin(lines, process, timeout=90):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError('cloudflared exited before creating a URL; see its log above')
        try:
            line = lines.get(timeout=.25)
        except queue.Empty:
            continue
        print(line.rstrip())
        match = re.search(r'https://[a-z0-9-]+\.trycloudflare\.com',line)
        if match:
            return match.group(0)
    raise RuntimeError('No tunnel URL after 90 seconds. Check Internet access and cloudflared configuration.')


def stop(process):
    if process is None or process.poll() is not None:
        return
    try:
        if os.name == 'nt':
            process.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            process.terminate()
        process.wait(timeout=8)
    except (OSError,subprocess.TimeoutExpired):
        process.kill()
        process.wait()


def run(port=8000, install=True):
    if not CONFIG.is_file():
        raise RuntimeError('Run serve.ps1 -Setup first to create accounts and select the dataset root.')
    config = json.loads(CONFIG.read_text(encoding='utf-8'))
    if not Path(config['data_root']).is_dir() or not config.get('users'):
        raise ValueError('Invalid server setup. Run serve.ps1 -Setup again.')
    # Check the port before startup touches the database or creates a tunnel.
    with socket.socket() as probe:
        try:
            probe.bind(('127.0.0.1',port))
        except OSError as exc:
            raise RuntimeError(f'Port {port} is busy. Stop the old run.ps1/server first.') from exc
    executable = tunnel_executable()
    build_frontend(install=install)
    tunnel = api = None
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
    try:
        tunnel = subprocess.Popen([executable,'tunnel','--url',f'http://127.0.0.1:{port}'],
                                  stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                                  text=True,encoding='utf-8',errors='replace',creationflags=flags)
        lines = queue.Queue()
        def read_lines():
            for line in tunnel.stdout:
                lines.put(line)
        threading.Thread(target=read_lines,daemon=True).start()
        origin = find_origin(lines,tunnel)
        api = subprocess.Popen([sys.executable,'-m','uvicorn','backend.main:app',
                                '--host','127.0.0.1','--port',str(port),'--workers','1',
                                '--no-proxy-headers'],cwd=ROOT,env=child_env(config,origin),creationflags=flags)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if api.poll() is not None:
                raise RuntimeError('API failed during startup. See the error above.')
            try:
                with urlopen(f'http://127.0.0.1:{port}/healthz',timeout=1) as response:
                    if response.status == 200:
                        break
            except OSError:
                time.sleep(.25)
        else:
            raise RuntimeError('API did not become ready in 30 seconds')
        print('\nREADY: ' + origin,flush=True)
        print('Share this URL and the visitor personal credentials. Keep this window and PC awake.',flush=True)
        print('Database: ' + config['db_dir'],flush=True)
        print('Report history: SHARED. Config editing/reruns: OWNER ONLY.',flush=True)
        while api.poll() is None and tunnel.poll() is None:
            while not lines.empty():
                print(lines.get_nowait().rstrip())
            time.sleep(.5)
        raise RuntimeError('Server or tunnel stopped unexpectedly; restart serve.ps1 for a new URL.')
    except KeyboardInterrupt:
        print('\nStopping server and tunnel.')
    finally:
        stop(api)
        stop(tunnel)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['setup','run'])
    parser.add_argument('--data-root')
    parser.add_argument('--port',type=int,default=8000)
    parser.add_argument('--no-install',action='store_true')
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error('Port must be between 1024 and 65535')
    os.chdir(ROOT)
    if args.action == 'setup':
        setup(args.data_root)
    else:
        run(args.port,install=not args.no_install)


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError,ValueError,OSError,subprocess.CalledProcessError) as exc:
        print('ERROR: ' + str(exc),file=sys.stderr)
        sys.exit(1)
