"""Offline checks for the deployment pieces we ship."""
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_docker_compose_database_volume_and_identity():
    doc = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    backend = doc["services"]["backend"]
    assert backend["environment"]["DB_DIR"] == "/app/db"
    assert "app_db:/app/db" in backend["volumes"]
    assert "user" not in backend  # same appuser who owns /app/db in image
    dockerfile = (ROOT / "Dockerfile.backend").read_text(encoding="utf-8")
    assert "/app/db" in dockerfile
    assert dockerfile.index("/app/db") < dockerfile.index("USER appuser")


def test_powershell_runs_backend_and_cleans_up():
    script = (ROOT / "run.ps1").read_text(encoding="utf-8")
    assert "-BackendOnly" in script
    assert "Stop-Process" in script
    assert "finally" in script
    assert "npm.cmd run dev" in script


def test_docker_context_ignores_large_private_files():
    patterns = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
    for ignored in (".git", ".venv", "data", "runs", "*.db"):
        assert ignored in patterns
