import hashlib
import importlib.util
import re
import subprocess
from pathlib import Path

import pytest

from pm_lol import live_runner


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATHS = [
    ROOT / "scripts" / "field_source_map_probe.py",
    ROOT / "scripts" / "lolesports_t1_g2_livestats_probe.py",
    ROOT / "scripts" / "lolesports_live_watcher_smoke.py",
    ROOT / "scripts" / "polymarket_discovery_smoke.py",
]
COMPROMISED_CREDENTIAL_SHA256 = (
    "f0041cc0cc3107e08f112ab933c2b0a42796f83a17051f576c3d1e7f2a4fd5d8"
)


def load_script(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("loader", [live_runner, *SCRIPT_PATHS])
def test_lolesports_api_key_is_loaded_from_environment(monkeypatch, loader):
    module = load_script(loader) if isinstance(loader, Path) else loader
    monkeypatch.setenv("LOLESPORTS_API_KEY", "  injected-test-key  ")

    assert module.load_lolesports_api_key() == "injected-test-key"


@pytest.mark.parametrize("loader", [live_runner, *SCRIPT_PATHS])
def test_lolesports_api_key_is_required(monkeypatch, loader):
    module = load_script(loader) if isinstance(loader, Path) else loader
    monkeypatch.delenv("LOLESPORTS_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="LOLESPORTS_API_KEY is required"):
        module.load_lolesports_api_key()


def test_live_runner_rejects_missing_key_before_creating_client(monkeypatch, tmp_path):
    monkeypatch.delenv("LOLESPORTS_API_KEY", raising=False)

    def unexpected_client(**kwargs):
        raise AssertionError("client must not be created without a credential")

    monkeypatch.setattr(live_runner, "LoLEsportsClient", unexpected_client)

    with pytest.raises(RuntimeError, match="LOLESPORTS_API_KEY is required"):
        live_runner.run_live_runner("match-id", tmp_path / "live.db")


def test_compromised_lolesports_credential_is_absent_from_tracked_files():
    tracked = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    ).stdout.split(b"\0")

    matches = []
    for raw_path in filter(None, tracked):
        path = ROOT / raw_path.decode()
        for candidate in re.findall(rb"[A-Za-z0-9]{40}", path.read_bytes()):
            if hashlib.sha256(candidate).hexdigest() == COMPROMISED_CREDENTIAL_SHA256:
                matches.append(str(path.relative_to(ROOT)))

    assert matches == []
