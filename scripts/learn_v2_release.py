"""Build and verify a standalone AI Learn v2 candidate from a clean commit."""

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
from tempfile import TemporaryDirectory

from official_release import ROOT, git, runtime_files, verify

APP_PATH = "/official/learn-everything/app/"
API_PATH = "/official/learn-everything/api/v2"


def pack(output: Path) -> None:
    if git("status", "--porcelain", "--untracked-files=normal"):
        raise ValueError("Commit authored inputs before packaging")
    commit = git("rev-parse", "HEAD")
    policy_path = ROOT / "runtime/learn-v2-release-policy.json"
    files = dict(runtime_files(ROOT, json.loads(policy_path.read_text(encoding="utf-8"))))

    web = ROOT / "learn_web"
    if any(path.name != ".env.example" for path in web.glob(".env*")):
        raise ValueError("Build from a checkout without learn_web/.env files")
    env = dict(os.environ, LEARN_WEB_BASE=APP_PATH, VITE_API_BASE=API_PATH)
    npm = "npm.cmd" if os.name == "nt" else "npm"
    subprocess.run([npm, "run", "build"], cwd=web, env=env, check=True)
    dist = web / "dist"
    if not (dist / "index.html").is_file() or not (dist / "pdfjs-assets").is_dir():
        raise ValueError("Vite output is missing the app or PDF resources")
    for path in dist.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"Linked frontend asset: {path}")
        if path.is_file():
            files[path.relative_to(ROOT).as_posix()] = path

    digests = {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in sorted(files.items())}
    release_id = f"learn-v2-{commit[:12]}"
    manifest = {
        "schemaVersion": 1,
        "id": release_id,
        "commit": commit,
        "sourceDigest": hashlib.sha256(json.dumps(digests, sort_keys=True).encode()).hexdigest(),
        "inputs": digests,
    }
    data = (json.dumps(manifest, indent=2) + "\n").encode()
    output.mkdir(parents=True, exist_ok=True)
    archive = output / f"{release_id}.tar.gz"
    with TemporaryDirectory(dir=output) as staging:
        pending = Path(staging) / archive.name
        with tarfile.open(pending, mode="w:gz") as tar:
            for name, path in sorted(files.items()):
                entry = tarfile.TarInfo(name)
                entry.size = path.stat().st_size
                with path.open("rb") as source:
                    tar.addfile(entry, source)
            entry = tarfile.TarInfo("RELEASE.json")
            entry.size = len(data)
            tar.addfile(entry, io.BytesIO(data))
        os.link(pending, archive)
    print(json.dumps({"archive": str(archive.resolve()), "commit": commit,
                      "sha256": hashlib.sha256(archive.read_bytes()).hexdigest()}))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    build = commands.add_parser("pack")
    build.add_argument("--output", type=Path, default=ROOT / "output/learn-v2")
    check = commands.add_parser("verify")
    check.add_argument("release", type=Path)
    args = parser.parse_args()
    if args.action == "pack":
        pack(args.output.resolve())
    else:
        metadata = verify(args.release)
        print(json.dumps({"verified": True, "commit": metadata["commit"]}))


if __name__ == "__main__":
    main()
