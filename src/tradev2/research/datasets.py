"""Public OHLCV ingestion; never imports or executes legacy source code."""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]
IntArray = NDArray[np.int64]
BAR_MS = 900_000


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def json_write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
                    encoding="utf-8")


@dataclass(frozen=True)
class Panel:
    symbols: tuple[str, ...]
    timestamps: IntArray
    values: FloatArray  # time, symbol, [open,high,low,close,volume]
    manifest: dict[str, Any]

    def __post_init__(self) -> None:
        if self.values.shape != (len(self.timestamps), len(self.symbols), 5):
            raise ValueError("panel shape mismatch")
        if len(self.timestamps) < 2 or not np.all(np.diff(self.timestamps) == BAR_MS):
            raise ValueError("panel must be continuous 15m bars")
        if len(set(self.symbols)) != len(self.symbols):
            raise ValueError("duplicate symbols")
        if not np.all(np.isfinite(self.values)) or np.any(self.values[:, :, :4] <= 0):
            raise ValueError("nonfinite or nonpositive OHLC")
        if np.any(self.values[:, :, 4] < 0):
            raise ValueError("negative volume")
        if np.any(self.values[:, :, 1] < np.max(self.values[:, :, [0, 2, 3]], axis=2)):
            raise ValueError("high below OHLC")
        if np.any(self.values[:, :, 2] > np.min(self.values[:, :, [0, 1, 3]], axis=2)):
            raise ValueError("low above OHLC")
        self.values.flags.writeable = False
        self.timestamps.flags.writeable = False


def aggregate_minutes(raw: FloatArray) -> FloatArray:
    """Reject gaps/duplicates; trim only incomplete outer 15-minute bins."""
    if raw.ndim != 2 or raw.shape[1] != 6 or len(raw) < 15:
        raise ValueError("expected minute [timestamp, open, high, low, close, volume]")
    if not np.all(np.isfinite(raw)):
        raise ValueError("nonfinite candle")
    ts = raw[:, 0].astype(np.int64)
    if not np.array_equal(ts, raw[:, 0]) or np.any(ts % 60_000) or np.any(np.diff(ts) != 60_000):
        raise ValueError("minute timestamps not strictly consecutive")
    first = int(np.searchsorted(ts, ((int(ts[0]) + BAR_MS - 1) // BAR_MS) * BAR_MS))
    stop = first + ((len(raw) - first) // 15) * 15
    if stop <= first:
        raise ValueError("no complete bars")
    groups = np.asarray(raw[first:stop], dtype=np.float64).reshape(-1, 15, 6)
    result = np.column_stack((groups[:, 0, 0], groups[:, 0, 1], groups[:, :, 2].max(axis=1),
                              groups[:, :, 3].min(axis=1), groups[:, -1, 4],
                              groups[:, :, 5].sum(axis=1)))
    return np.asarray(result, dtype=np.float64)


def ingest_legacy_public(source_cache: Path, target: Path, source_sha: str) -> dict[str, Any]:
    """Hash immutable public files, aggregate into target, preserve prior consumption."""
    source_cache, target = source_cache.resolve(), target.resolve()
    if source_cache == target or source_cache in target.parents:
        raise ValueError("output may not be inside source")
    metadata: dict[str, Any] = json.loads((source_cache / "manifest.json").read_text())
    symbols = tuple(sorted(metadata))
    arrays: list[FloatArray] = []
    sources: list[dict[str, Any]] = []
    timestamps: IntArray | None = None
    for symbol in symbols:
        path = source_cache / f"{symbol}.npy"
        digest = sha256_file(path)
        raw = np.load(path, mmap_mode="r", allow_pickle=False)
        values = aggregate_minutes(raw)
        current = values[:, 0].astype(np.int64)
        if timestamps is not None and not np.array_equal(timestamps, current):
            raise ValueError(f"unaligned symbol {symbol}; no imputation permitted")
        timestamps = current
        arrays.append(values[:, 1:])
        sources.append({"symbol": symbol, "path": str(path), "sha256": digest,
                        "bytes": path.stat().st_size, "minute_rows": len(raw)})
    if timestamps is None:
        raise ValueError("empty dataset")
    target.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(target / "candles_15m.npz", timestamps=timestamps,
                        symbols=np.asarray(symbols), values=np.stack(arrays, axis=1))
    manifest = {"schema_version": 1, "dataset_id": "BYBIT_PUBLIC_REUSED_37_OHLCV_210D",
                "venue": "bybit_linear", "interval_ms": BAR_MS, "symbols": list(symbols),
                "first_open_ms": int(timestamps[0]), "last_open_ms": int(timestamps[-1]),
                "bars_per_symbol": len(timestamps), "source_revision": source_sha,
                "sources": sources, "sha256": sha256_file(target / "candles_15m.npz"),
                "evidence_role": "REUSED_HISTORICAL_DISCOVERY",
                "prior_consumption": "Legacy footprint/horizon/RSI campaigns already inspected this history",
                "untouched_holdout": False, "final_holdout_state": "NOT_ACQUIRED_NOT_CONSUMED",
                "quality": "consecutive minutes; aligned symbols; exact complete 15m aggregation; no fill",
                "limitations": ["universe selected in September 2026, survivorship/selection bias",
                                "no historical L2, queue, trade-side flow or point-in-time instrument rules",
                                "OHLCV volume is total base volume, not aggressive buy volume"]}
    json_write(target / "manifest.json", manifest)
    return manifest


def load_panel(directory: Path) -> Panel:
    manifest: dict[str, Any] = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    path = directory / "candles_15m.npz"
    if sha256_file(path) != manifest["sha256"]:
        raise ValueError("dataset content hash mismatch")
    if manifest["evidence_role"] != "REUSED_HISTORICAL_DISCOVERY":
        raise ValueError("this discovery loader cannot open protected/final/prospective evidence")
    with np.load(path, allow_pickle=False) as data:
        return Panel(tuple(str(s) for s in data["symbols"]), data["timestamps"].astype(np.int64),
                     data["values"].astype(np.float64), manifest)
