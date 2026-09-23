from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from typing import TypeVar

T = TypeVar("T")


def bounded_batch(symbols: Iterable[str], fetch: Callable[[str], T], workers: int = 4) -> list[T]:
    if not 1 <= workers <= 8:
        raise ValueError("public polling worker budget must be 1..8")
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(fetch, symbols))

