"""Forced SSH command for the existing company Linux installation (Python 3.12)."""

import ctypes
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from urllib.error import URLError
from urllib.request import urlopen

BASE = Path.home() / "data/ai-learn/standalone-v2"
LIMIT = 512 * 1024**2
TIMER = "ai-learn-v2-reaper.timer"
SERVICES = ["ai-learn-v2-" + name + ".service" for name in
            ("embed", "api", "worker@llm", "worker@io")]
# Queue DDL, interpreter environments and host integration require a coordinated release.
GUARDED = ("requirements-learn-core.txt", "requirements-learn-embed.txt", "alembic.ini",
           "migrations", "scripts/phase0/apply_queue_schema.py", "deploy")


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def prepare(stream, folder, commit, checksum):
    archive = folder / "incoming.tar.gz"
    target = folder / "candidate"
    target.mkdir()
    count = 0
    with archive.open("xb") as out:
        while chunk := stream.read(1024 * 1024):
            count += len(chunk)
            if count > LIMIT:
                raise ValueError("archive too large")
            out.write(chunk)
    if digest(archive) != checksum:
        raise ValueError("archive checksum mismatch")
    names = set()
    size = 0
    with tarfile.open(archive, "r:gz") as tar:
        for member in tar:
            name = member.name
            size += member.size
            if (not member.isreg() or name.startswith("/") or
                    any(part in ("", ".", "..") for part in name.split("/")) or
                    name in names or size > LIMIT or len(names) >= 50000):
                raise ValueError("invalid release member")
            names.add(name)
            path = target / name
            path.parent.mkdir(parents=True, exist_ok=True)
            with tar.extractfile(member) as source, path.open("xb") as dest:
                shutil.copyfileobj(source, dest)
    manifest = json.loads((target / "RELEASE.json").read_bytes())
    inputs = manifest["inputs"]
    if (manifest["commit"] != commit or manifest["id"] != "learn-v2-" + commit[:12]
            or names != set(inputs) | {"RELEASE.json"}
            or any(digest(target / name) != expected for name, expected in inputs.items())):
        raise ValueError("release manifest mismatch")
    return target


def guarded_files(root):
    files = {}
    for entry in GUARDED:
        path = root / entry
        if not path.exists():
            raise ValueError(f"missing release prerequisite: {entry}")
        for file in path.rglob("*") if path.is_dir() else [path]:
            if file.is_file() and "__pycache__" not in file.parts:
                files[file.relative_to(root)] = digest(file)
    return files


def exchange(a, b):
    # Linux RENAME_EXCHANGE works with the first release's populated src directory too.
    rename = ctypes.CDLL(None, use_errno=True).renameat2
    if rename(-100, os.fsencode(a), -100, os.fsencode(b), 2) != 0:
        raise OSError(ctypes.get_errno(), "could not exchange release directories")


def systemctl(*args):
    subprocess.run(["systemctl", "--user", *args], check=True)


def stop():
    systemctl("stop", TIMER)
    systemctl("stop", "ai-learn-v2-reaper.service", *SERVICES)


def start():
    systemctl("start", *SERVICES, TIMER)
    for _ in range(60):
        try:
            for url in ("http://127.0.0.1:18080/healthz", "http://127.0.0.1:18080/app/",
                        "http://127.0.0.1:18090/healthz"):
                with urlopen(url, timeout=2) as response:
                    if response.status != 200:
                        raise ValueError("unexpected health response")
            for unit in [*SERVICES, TIMER]:
                systemctl("is-active", "--quiet", unit)
            return
        except (URLError, OSError, ValueError, subprocess.CalledProcessError):
            time.sleep(1)
    raise RuntimeError("release did not become healthy")


def switch(current, alternate):
    switched = False
    try:
        stop()
        exchange(current, alternate)
        switched = True
        start()
    except BaseException:
        if switched:
            stop()
            exchange(current, alternate)
        start()
        raise


def main():
    request = re.fullmatch(r"deploy ([0-9a-f]{40}) ([0-9a-f]{64})",
                           os.environ.get("SSH_ORIGINAL_COMMAND", ""))
    restore = (len(sys.argv) == 3 and sys.argv[1] == "--restore" and
               re.fullmatch(r"before-[0-9a-f]{12}-[a-z0-9_]+", sys.argv[2]) and
               "SSH_ORIGINAL_COMMAND" not in os.environ)
    if not (request or restore):
        raise SystemExit("expected a release from CI or local --restore before-...")

    os.umask(0o077)
    releases = BASE / "releases"
    releases.mkdir(exist_ok=True)
    with (releases / ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        current = BASE / "src"
        if restore:
            alternate = releases / sys.argv[2]
            if guarded_files(current) != guarded_files(alternate):
                raise ValueError("manual rollback required after schema or runtime changes")
            switch(current, alternate)
            print(f"Restored source from {sys.argv[2]}")
            return
        commit, checksum = request.groups()
        with tempfile.TemporaryDirectory(dir=releases, prefix=".receive-") as tmp:
            folder = Path(tmp)
            candidate = prepare(sys.stdin.buffer, folder, commit, checksum)
            if (current / "RELEASE.json").is_file() and (
                    (current / "RELEASE.json").read_bytes() == (candidate / "RELEASE.json").read_bytes()):
                start()
                print(f"Already active: {commit}")
                return
            previous = releases / ("before-" + commit[:12] + "-" + folder.name.removeprefix(".receive-"))
            if guarded_files(current) != guarded_files(candidate):
                raise ValueError("manual release required for dependency, migration or host changes")
            candidate.rename(previous)
            switch(current, previous)
            print(f"Active: {commit}; previous source: {previous}")


if __name__ == "__main__":
    main()
