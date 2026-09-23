"""Fail CI on tracked credentials, runtime state, raw datasets and oversized artifacts."""

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_ROOTS = {"runtime", "state", "secrets", "credentials", "data", ".venv", ".local"}
FORBIDDEN_SUFFIXES = {".sqlite", ".sqlite3", ".db", ".log", ".pid", ".pem", ".key", ".npy", ".npz"}
SECRET_PATTERNS = [
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(rb"gh[pousr]_[A-Za-z0-9]{30,}"),
    re.compile(rb"github_pat_[A-Za-z0-9_]{50,}"),
    re.compile(rb"AKIA[0-9A-Z]{16}"),
]


def main() -> int:
    tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")
    problems = []
    for name in filter(None, tracked):
        path = ROOT / name
        parts = Path(name).parts
        if (parts[0] in FORBIDDEN_ROOTS or path.suffix.lower() in FORBIDDEN_SUFFIXES
                or path.name.startswith(".env") and path.name != ".env.example"
                or "node_modules" in parts):
            problems.append(f"forbidden tracked artifact: {name}")
        if not path.is_file():
            continue
        if path.stat().st_size > 5_000_000:
            problems.append(f"artifact exceeds 5 MB: {name}")
        content = path.read_bytes()
        if any(pattern.search(content) for pattern in SECRET_PATTERNS):
            problems.append(f"credential pattern detected: {name}")
    for problem in problems:
        print(problem)
    print(f"artifact/secret-pattern scan: {len(problems)} violations")
    return bool(problems)


if __name__ == "__main__":
    raise SystemExit(main())
