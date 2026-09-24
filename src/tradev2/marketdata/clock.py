"""Observed public server/local clock bracket; never an inferred latency."""

import time
from typing import Protocol


class PublicServerClock(Protocol):
    def server_time(self) -> int: ...


def observe_public_clock(client: PublicServerClock) -> dict[str, int | str]:
    local_before_ms = time.time_ns() // 1_000_000
    monotonic_before_ms = time.monotonic_ns() // 1_000_000
    server_ms = client.server_time()
    monotonic_after_ms = time.monotonic_ns() // 1_000_000
    local_after_ms = time.time_ns() // 1_000_000
    wall_elapsed_ms = local_after_ms - local_before_ms
    monotonic_elapsed_ms = monotonic_after_ms - monotonic_before_ms
    return {
        "local_before_ms": local_before_ms,
        "server_ms": server_ms,
        "local_after_ms": local_after_ms,
        "wall_elapsed_ms": wall_elapsed_ms,
        "monotonic_elapsed_ms": monotonic_elapsed_ms,
        "server_minus_local_after_ms": server_ms - local_after_ms,
        "server_minus_local_before_ms": server_ms - local_before_ms,
        "status": "WALL_CLOCK_STABLE" if wall_elapsed_ms >= 0
                  and abs(wall_elapsed_ms - monotonic_elapsed_ms) <= 50
                  else "WALL_CLOCK_UNSTABLE",
    }
