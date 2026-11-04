"""Copy new prospective chunks from a remote collector into a local checkout.

Streams the remote `data/public/prospective_*` directories over `ssh ... tar`,
unpacks them with the safe `data` filter into a temporary directory, and adds only
chunk directories that are absent locally. A chunk present on both sides must be
byte-identical; otherwise nothing is copied. The merged chains are re-verified.
"""

import argparse
import hashlib
import io
import json
import shutil
import subprocess
import tarfile
import tempfile
import time
from pathlib import Path
from typing import Any

from tradev2.research.prospective_chain import summarize_prospective_evidence


def tree_digest(directory: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in directory.rglob("*") if item.is_file()):
        digest.update(path.relative_to(directory).as_posix().encode() + b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def merge_chunks(source_public: Path, target_public: Path) -> dict[str, Any]:
    """Add absent chunks; refuse everything if any shared chunk differs."""
    added: list[str] = []
    identical = 0
    for chunk in sorted(source_public.glob("prospective_*")):
        if not chunk.is_dir():
            continue
        destination = target_public / chunk.name
        if destination.exists():
            if tree_digest(destination) != tree_digest(chunk):
                raise ValueError(f"local and remote chunk differ; nothing copied: {chunk.name}")
            identical += 1
        else:
            added.append(chunk.name)
    target_public.mkdir(parents=True, exist_ok=True)
    for name in added:
        shutil.copytree(source_public / name, target_public / name)
    return {"added": added, "identical": identical}


def unpack(archive: bytes, destination: Path) -> None:
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as bundle:
        for member in bundle.getmembers():
            if not member.name.startswith("prospective_"):
                raise ValueError(f"unexpected archive member: {member.name}")
        bundle.extractall(destination, filter="data")


def fetch(host: str, remote_root: str, identity: Path | None) -> bytes:
    command = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15"]
    if identity is not None:
        command += ["-i", str(identity)]
    command += [host, f"cd {remote_root}/data/public && tar -cf - prospective_*"]
    return subprocess.run(command, check=True, capture_output=True, timeout=600).stdout


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", required=True, help="ssh destination, for example user@host")
    parser.add_argument("--remote-root", required=True, help="remote data root")
    parser.add_argument("--identity", type=Path, help="ssh private key")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1],
                        help="local data root (defaults to this checkout)")
    args = parser.parse_args()
    root = args.root.resolve()
    archive = fetch(args.host, args.remote_root, args.identity)
    with tempfile.TemporaryDirectory() as staging:
        unpack(archive, Path(staging))
        merged = merge_chunks(Path(staging), root / "data/public")
    summary = summarize_prospective_evidence(root, now_ms=time.time_ns() // 1_000_000)
    print(json.dumps({"merged": merged, "status": summary["status"], "error": summary["error"],
                      "gate": summary["gate"], "collector": summary["collector"]}, indent=2))
    if summary["status"] == "CHAIN_INTEGRITY_FAILED":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
