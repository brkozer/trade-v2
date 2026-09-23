import hashlib
from pathlib import Path
from typing import IO

import portalocker


class AccountAuthority:
    """Host-local file lock, not a distributed account lock.

    Root is fixed by the application installation, never a user-selected config file.
    Account aliases must resolve to a canonical credential profile before this boundary.
    """

    def __init__(self, root: Path, venue: str, profile: str) -> None:
        key = hashlib.sha256(f"{venue}:{profile}".encode()).hexdigest()
        self.path = root.resolve() / "state" / "authority" / f"{key}.lock"
        self._file: IO[str] | None = None

    def acquire(self) -> None:
        if self._file is not None:
            raise PermissionError("account authority already acquired")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+", encoding="utf-8")
        try:
            portalocker.lock(handle, portalocker.LOCK_EX | portalocker.LOCK_NB)
        except portalocker.LockException as exc:
            handle.close()
            raise PermissionError("account authority owned by another runtime") from exc
        self._file = handle

    def release(self) -> None:
        if self._file is not None:
            portalocker.unlock(self._file)
            self._file.close()
            self._file = None

