"""Prepare already-consumed public legacy candles and explicit market assumptions.

Run from the Trade v2 repository. Writes only to its data/public directory.
"""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from tradev2.research.datasets import ingest_legacy_public, json_write, sha256_file

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    args = parser.parse_args()
    source = args.source.resolve()
    target = ROOT / "data" / "public" / "initial_campaign"
    manifest = ingest_legacy_public(source / "research" / "footprint-2026-09-09" / "cache",
                                    target, args.source_sha)
    fees_path = source / "fee_tiers.measured.json"
    spreads_path = source / "research" / "spread_sample.json"
    funding_path = source / "research" / "funding-model-2026-09-08" / "funding_365.json"
    fees = json.loads(fees_path.read_text())
    spreads = json.loads(spreads_path.read_text())
    funding = json.loads(funding_path.read_text())
    instruments: dict[str, Any] = {}
    cursor = ""
    with httpx.Client(timeout=30, follow_redirects=False) as client:
        while True:
            response = client.get("https://api.bybit.com/v5/market/instruments-info",
                                  params={"category": "linear", "limit": 1000, "cursor": cursor})
            response.raise_for_status()
            payload = response.json()
            if payload.get("retCode") != 0:
                raise RuntimeError(f"public instrument request rejected: {payload.get('retCode')}")
            instruments.update({row["symbol"]: row for row in payload["result"]["list"]})
            next_cursor = payload["result"].get("nextPageCursor", "")
            if not next_cursor:
                break
            if next_cursor == cursor:
                raise RuntimeError("instrument pagination did not progress")
            cursor = next_cursor
    result: dict[str, Any] = {"schema_version": 1, "symbols": {},
        "instrument_observed_at": datetime.now(UTC).isoformat(),
        "instrument_source": "https://api.bybit.com/v5/market/instruments-info?category=linear",
        "fee_observed_at": fees["measured_at"], "spread_observed_at_ms": spreads["measured_at_ms"],
        "sources": [{"path": str(p), "sha256": sha256_file(p)} for p in (fees_path, spreads_path, funding_path)],
        "limitations": ["fee tiers are a dated observed account schedule, not a historical fee time series",
                        "instrument minimums are current snapshots, not point-in-time historical rules",
                        "spread assumptions are max(3bps, old snapshot median), not observed historical spreads",
                        "funding uses settled historical rates and entry-notional approximation; historical mark missing"]}
    for symbol in manifest["symbols"]:
        instrument = instruments[symbol]
        if instrument["status"] != "Trading" or instrument["contractType"] != "LinearPerpetual":
            raise ValueError(f"unsupported instrument {symbol}")
        lot = instrument["lotSizeFilter"]
        measured = symbol in fees["tiers"]
        # An unmeasured fee tier is an explicit assumption, never silently "measured".
        tier = fees["tiers"][symbol] if measured else {"maker": .0004, "taker": .0011}
        if not measured:
            result["limitations"].append(f"{symbol}: fee tier not measured; assumed 4/11 bps")
        spread = spreads["spreads"].get(symbol, {}).get("median_bps")
        result["symbols"][symbol] = {
            "maker_rate": tier["maker"], "taker_rate": tier["taker"],
            "spread_bps": max(3., float(spread)) if spread is not None else 5.,
            "spread_observed_median_bps": spread,
            "qty_step": lot["qtyStep"], "min_qty": lot["minOrderQty"],
            "min_notional": lot["minNotionalValue"], "max_qty": lot["maxMktOrderQty"],
            "funding": funding[symbol], "instrument": instrument,
            "fee_source": "MEASURED" if measured else "ASSUMED_DEFAULT",
            "provenance": ("dated measured fee schedule" if measured else "ASSUMED default fee")
                          + "; assumed spread floor; public current rules; settled funding"}
    json_write(target / "economics.json", result)
    print(json.dumps({"dataset": manifest["dataset_id"], "symbols": len(manifest["symbols"]),
                      "bars_per_symbol": manifest["bars_per_symbol"], "data_sha256": manifest["sha256"],
                      "economics_sha256": sha256_file(target / "economics.json")}))


if __name__ == "__main__":
    main()
