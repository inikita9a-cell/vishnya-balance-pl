"""Run locally; enter a unique randomly generated password from your password manager."""
import getpass
import hashlib
import json
import secrets
name = input("User login: ").strip()
password = getpass.getpass("Random password (at least 24 characters): ")
if len(password) < 24:
    raise SystemExit("Use at least 24 random characters")
salt = secrets.token_bytes(16)
digest = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1, dklen=32)
print(json.dumps({name: salt.hex() + ":" + digest.hex()}))
