"""Prospective L2/trade-flow smoke diagnostics and execution upper bounds.

Public trades can show a quote traded through, not our queue priority. Maker
"fills" here are optimistic upper bounds and must never authorize promotion.
"""

import json
from collections import defaultdict
from decimal import Decimal
from itertools import product
from pathlib import Path
from statistics import mean
from typing import Any

from tradev2.evidence.journal import open_reader
from tradev2.marketdata.recording_audit import inspect_recording


def _money(value: Any) -> Decimal:
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError("nonfinite microstructure price or size")
    return result


def _traded_through(fills: list[dict[str, Any]], direction: Decimal,
                    price: Decimal, after_ms: int, until_ms: int) -> bool:
    return any(after_ms < int(trade["exchange_event_ms"]) <= until_ms
               and (direction == 1 and _money(trade["price"]) <= price
                    or direction == -1 and _money(trade["price"]) >= price)
               for trade in fills)


def analyze(path: Path, run_id: str, *, horizon_ms: int = 2000,
            fee_taker_bps: Decimal = Decimal("5.5"),
            fee_maker_bps: Decimal = Decimal("2")) -> dict[str, Any]:
    if not 100 <= horizon_ms <= 60_000:
        raise ValueError("smoke horizon must be bounded")
    audit = inspect_recording(path, run_id)
    books: dict[str, list[dict[str, Any]]] = defaultdict(list)
    trades: dict[str, list[dict[str, Any]]] = defaultdict(list)
    connection = open_reader(path)
    try:
        for row in connection.execute("SELECT body FROM events WHERE run_id=? AND kind='microstructure' ORDER BY sequence", (run_id,)):
            event = json.loads(row[0])
            payload = event["payload"]
            symbol = payload["symbol"]
            if payload["kind"] == "orderbook":
                books[symbol].append(payload)
            else:
                trades[symbol].extend(payload["trades"])
    finally:
        connection.close()
    symbols: dict[str, Any] = {}
    experiments: list[dict[str, Any]] = []
    for symbol, observations in sorted(books.items()):
        if any(row.get("exchange_event_ms") is None for row in observations):
            raise ValueError("orderbook event timestamp unknown")
        sequence = sorted(observations, key=lambda row: row["exchange_event_ms"])
        fills = sorted(trades[symbol], key=lambda row: row["exchange_event_ms"])
        spreads = [float(_money(row["spread_bps"])) for row in sequence if row["spread_bps"] is not None]
        imbalances: list[float] = []
        forward_bps: list[float] = []
        for index, row in enumerate(sequence[:-1]):
            bid_depth = _money(row["bid_depth_50"])
            ask_depth = _money(row["ask_depth_50"])
            total = bid_depth + ask_depth
            if total <= 0:
                continue
            future_index = next((j for j in range(index + 1, len(sequence))
                                 if sequence[j]["exchange_event_ms"] >= row["exchange_event_ms"] + horizon_ms), None)
            if future_index is None:
                continue
            next_row = sequence[future_index]
            current_mid = (_money(row["best_bid"]) + _money(row["best_ask"])) / 2
            future_mid = (_money(next_row["best_bid"]) + _money(next_row["best_ask"])) / 2
            imbalances.append(float((bid_depth - ask_depth) / total))
            forward_bps.append(float((future_mid / current_mid - 1) * 10_000))
        symbols[symbol] = {"books": len(sequence), "public_trades": len(fills),
                           "median_spread_bps": sorted(spreads)[len(spreads) // 2] if spreads else None,
                           "paired_book_observations": len(forward_bps),
                           "mean_next_mid_bps_when_buy_imbalance":
                           mean(value for imbalance, value in zip(imbalances, forward_bps, strict=True) if imbalance >= .2)
                           if any(value >= .2 for value in imbalances) else None,
                           "mean_next_mid_bps_when_sell_imbalance":
                           mean(value for imbalance, value in zip(imbalances, forward_bps, strict=True) if imbalance <= -.2)
                           if any(value <= -.2 for value in imbalances) else None}
        # Sparse, predeclared every-20th-book opportunities limit overlap. All
        # arms use identical timestamps; nonfills contribute zero treatment PnL.
        for offset_bps, wait_ms, reprice, exit_urgency in product(
                (Decimal(0), Decimal(1)), (1000, 3000),
                ("NONE", "ONCE_AT_HALF_WAIT"), ("MARK_ONLY", "TAKER_EXIT")):
                paired: list[Decimal] = []
                taker_results: list[Decimal] = []
                maker_results: list[Decimal] = []
                adverse: list[Decimal] = []
                optimistic_fills = 0
                for index in range(0, len(sequence), 20):
                    row = sequence[index]
                    start = row["exchange_event_ms"]
                    if start is None:
                        continue
                    later = next((book for book in sequence[index + 1:]
                                  if book["exchange_event_ms"] is not None
                                  and book["exchange_event_ms"] >= start + max(wait_ms, horizon_ms)), None)
                    if later is None:
                        continue
                    bid, ask = _money(row["best_bid"]), _money(row["best_ask"])
                    mid = (bid + ask) / 2
                    bid_depth, ask_depth = _money(row["bid_depth_50"]), _money(row["ask_depth_50"])
                    direction = Decimal(1) if bid_depth >= ask_depth else Decimal(-1)
                    taker_price = ask if direction == 1 else bid
                    maker_price = (bid * (1 - offset_bps / 10_000) if direction == 1
                                   else ask * (1 + offset_bps / 10_000))
                    exit_mid = (_money(later["best_bid"]) + _money(later["best_ask"])) / 2
                    exit_price = (exit_mid if exit_urgency == "MARK_ONLY" else
                                  _money(later["best_bid"] if direction == 1 else later["best_ask"]))
                    exit_fee = exit_price * fee_taker_bps / 10_000 if exit_urgency == "TAKER_EXIT" else Decimal(0)
                    taker_net = direction * (exit_price - taker_price) - (
                        taker_price * fee_taker_bps / 10_000 + exit_fee)
                    half = start + wait_ms // 2
                    through = _traded_through(fills, direction, maker_price, start,
                                              half if reprice != "NONE" else start + wait_ms)
                    if reprice != "NONE" and not through:
                        new_book = next((book for book in sequence[index + 1:]
                                         if book["exchange_event_ms"] >= half), None)
                        if new_book is not None and new_book["exchange_event_ms"] <= start + wait_ms:
                            quote = _money(new_book["best_bid"] if direction == 1 else new_book["best_ask"])
                            maker_price = quote * (1 - direction * offset_bps / 10_000)
                            through = _traded_through(fills, direction, maker_price,
                                                      new_book["exchange_event_ms"], start + wait_ms)
                    maker_net = (direction * (exit_price - maker_price) -
                                 maker_price * fee_maker_bps / 10_000 - exit_fee) if through else Decimal(0)
                    optimistic_fills += through
                    taker_results.append(taker_net / mid * 10_000)
                    maker_results.append(maker_net / mid * 10_000)
                    paired.append((maker_net - taker_net) / mid * 10_000)
                    if through:
                        adverse.append(direction * (exit_mid - maker_price) / mid * 10_000)
                experiments.append({"symbol": symbol, "baseline": "immediate_taker_quote",
                                    "treatment": "optimistic_maker_trade_through",
                                    "maker_offset_bps": str(offset_bps), "maker_wait_ms": wait_ms,
                                    "repricing": reprice, "exit_urgency": exit_urgency,
                                    "sample_unit": "every_20th_book_intent", "n": len(paired),
                                    "optimistic_fill_upper_bound_n": optimistic_fills,
                                    "optimistic_fill_upper_bound_rate": str(Decimal(optimistic_fills) / len(paired)) if paired else None,
                                    "mean_taker_net_bps": str(mean(taker_results)) if taker_results else None,
                                    "mean_maker_upper_bound_net_bps": str(mean(maker_results)) if maker_results else None,
                                    "mean_paired_upper_bound_delta_bps": str(mean(paired)) if paired else None,
                                    "mean_adverse_selection_bps_on_through": str(mean(adverse)) if adverse else None,
                                    "confidence_interval": None, "status": "SMOKE_BOUND_ONLY"})
    return {"schema_version": 1, "run_id": run_id, "source_manifest_sha256": audit["manifest_sha256"],
            "source_messages": audit["messages"], "source_books": audit["books"],
            "source_trades": audit["trades"], "analysis_horizon_ms": horizon_ms,
            "symbols": symbols, "execution_experiments": experiments,
            "status": "PROSPECTIVE_DATA_COLLECTION_ACTIVE_SOFTWARE; SMOKE_ONLY_NO_EDGE_CLAIM",
            "limitations": ["ten-second public sample is not a statistically useful alpha test",
                            "public trade-through is only an optimistic maker-fill upper bound; queue priority unknown",
                            "no account-specific fees, actual fills, inventory or order latency measured",
                            "intents overlap in calendar time; no inferential p-value or confidence interval"]}
