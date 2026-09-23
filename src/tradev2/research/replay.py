"""Deterministic event replay: decisions at close, execution at the next open.

This is an OHLCV research simulator, not a calibrated queue or exchange simulator.
"""

import hashlib
from collections import Counter
from dataclasses import asdict, dataclass
from decimal import ROUND_FLOOR, Decimal
from typing import Any

import numpy as np

from tradev2.alpha.candidates import Candidate
from tradev2.research.costs import BASE, CostScenario, SymbolEconomics
from tradev2.research.datasets import BAR_MS, FloatArray, Panel


def money(value: float | int | Decimal) -> Decimal:
    return Decimal(str(value))


@dataclass
class Position:
    symbol_index: int
    direction: int
    entry_index: int
    decision_ms: int
    entry_ms: int
    entry_mid: Decimal
    entry_price: Decimal
    quantity: Decimal
    risk: Decimal
    stop: Decimal
    target: Decimal
    entry_fee: Decimal
    entry_spread: Decimal
    entry_slippage: Decimal
    funding: Decimal
    opportunity_id: str
    regime: str


@dataclass(frozen=True)
class Trade:
    opportunity_id: str
    symbol: str
    direction: int
    decision_ms: int
    entry_ms: int
    exit_bar_ms: int
    exit_reason: str
    quantity: float
    entry_price: float
    exit_price: float
    gross_pnl: float
    fees: float
    funding: float
    spread: float
    slippage: float
    net_pnl: float
    risk: float
    regime: str

    @property
    def net_r(self) -> float:
        return self.net_pnl / self.risk


@dataclass
class ReplayResult:
    trades: list[Trade]
    daily_pnl: dict[int, float]
    opportunities: list[dict[str, Any]]
    rejections: dict[str, int]
    metrics: dict[str, Any]


def opportunity_id(candidate_id: str, symbol: str, decision_ms: int, direction: int) -> str:
    return hashlib.sha256(f"{candidate_id}|{symbol}|{decision_ms}|{direction}".encode()).hexdigest()[:24]


def replay(panel: Panel, candidate: Candidate, signals: FloatArray, exit_rsi: FloatArray,
           economics: dict[str, SymbolEconomics], start: int, stop: int,
           scenario: CostScenario = BASE, *, capture: bool = False) -> ReplayResult:
    if not 0 < start < stop <= len(panel.timestamps):
        raise ValueError("invalid replay interval")
    if signals.shape != panel.values[:, :, 3].shape or exit_rsi.shape != signals.shape:
        raise ValueError("decision shape mismatch")
    first_ms, last_ms = int(panel.timestamps[start]), int(panel.timestamps[stop - 1]) + BAR_MS
    for symbol in panel.symbols:
        obs = economics[symbol].funding
        if first_ms < obs[0, 0] or last_ms > obs[-1, 0]:
            raise ValueError(f"funding coverage incomplete for {symbol}")
    cash = Decimal('10000')
    positions: dict[int, Position] = {}
    trades: list[Trade] = []
    opportunities: list[dict[str, Any]] = []
    rejected: Counter[str] = Counter()
    daily_pnl: dict[int, float] = {}
    previous_equity = peak = cash
    drawdown = Decimal(0)
    turnover = Decimal(0)
    symbol_counts = len(panel.symbols)
    market = panel.values[:, :, 3].mean(axis=1)  # only direction label; not used for trading
    # Funding at a bar's opening boundary is applied before existing positions exit.
    settlements: list[dict[int, float]] = []
    for symbol in panel.symbols:
        settlements.append({int(ts): float(rate) for ts, rate in economics[symbol].funding})

    def close_position(symbol_index: int, index: int, mid: Decimal, reason: str) -> None:
        nonlocal cash, turnover
        position = positions.pop(symbol_index)
        eco = economics[panel.symbols[symbol_index]]
        half_spread = money(eco.spread_bps) * money(scenario.spread_multiplier) / 20_000
        slip = money(scenario.slippage_bps_per_side) / 10_000
        price = mid * (1 - position.direction * (half_spread + slip))
        exit_fee = position.quantity * price * money(eco.taker_rate) * money(scenario.fee_multiplier)
        exit_spread = position.quantity * mid * half_spread
        exit_slippage = position.quantity * mid * slip
        gross = position.quantity * position.direction * (mid - position.entry_mid)
        spread = position.entry_spread + exit_spread
        slippage = position.entry_slippage + exit_slippage
        fees = position.entry_fee + exit_fee
        net = gross - spread - slippage - fees - position.funding
        cash += position.quantity * position.direction * (price - position.entry_price) - exit_fee
        turnover += position.quantity * price
        trades.append(Trade(position.opportunity_id, panel.symbols[symbol_index], position.direction,
                            position.decision_ms, position.entry_ms, int(panel.timestamps[index]), reason,
                            float(position.quantity), float(position.entry_price), float(price), float(gross), float(fees), float(position.funding),
                            float(spread), float(slippage), float(net), float(position.risk), position.regime))

    for index in range(start, stop):
        ts = int(panel.timestamps[index])
        opens = panel.values[index, :, 0]
        for symbol_index, position in tuple(positions.items()):
            settlement = money(settlements[symbol_index].get(ts, 0.))
            payment = position.quantity * position.entry_price * settlement * position.direction
            cash -= payment
            position.funding += payment
            held = index - position.entry_index
            is_rsi_exit = (candidate.reference is not None
                           and exit_rsi[index - 1, symbol_index] >= candidate.reference.exit_rsi_min)
            if held >= candidate.holding_bars or is_rsi_exit:
                close_position(symbol_index, index, money(float(opens[symbol_index])),
                               "RSI_EXIT" if is_rsi_exit else "TIME_STOP")
        equity_open = cash + sum(p.quantity * p.direction * (money(float(opens[s])) - p.entry_price)
                                 for s, p in positions.items())
        signal_index = index - 1 - scenario.latency_bars
        # A fold begins flat; do not carry discovery-period signals into validation.
        if signal_index >= start:
            strengths = signals[signal_index]
            ranked = sorted(np.flatnonzero(strengths), key=lambda s: (-abs(strengths[s]), panel.symbols[s]))
            for index_value in ranked:
                s = int(index_value)
                symbol, eco = panel.symbols[s], economics[panel.symbols[s]]
                direction = 1 if strengths[s] > 0 else -1
                decision_ms = int(panel.timestamps[signal_index]) + BAR_MS
                oid = opportunity_id(candidate.candidate_id, symbol, decision_ms, direction)
                reason = "FILLED"
                mid = money(float(opens[s]))
                half_spread = money(eco.spread_bps) * money(scenario.spread_multiplier) / 20_000
                slip = money(scenario.slippage_bps_per_side) / 10_000
                price = mid * (1 + direction * (half_spread + slip))
                risk_budget = max(Decimal(0), equity_open) * Decimal('.0025')
                desired_notional = min(risk_budget / money(candidate.stop_pct), max(Decimal(0), equity_open) * Decimal('.20'))
                step = money(eco.qty_step)
                quantity = (desired_notional / price / step).to_integral_value(rounding=ROUND_FLOOR) * step
                quantity = (quantity * money(scenario.fill_fraction) / step).to_integral_value(rounding=ROUND_FLOOR) * step
                used_notional = sum(p.quantity * money(float(opens[j])) for j, p in positions.items())
                if s in positions:
                    reason = "SYMBOL_ALREADY_OPEN"
                elif len(positions) >= 4:
                    reason = "PORTFOLIO_SLOTS"
                elif equity_open <= 0 or used_notional + quantity * price > equity_open * Decimal('.8'):
                    reason = "MARGIN_OR_GROSS_EXPOSURE"
                elif quantity < money(eco.min_qty) or quantity * price < money(eco.min_notional):
                    reason = "MINIMUM_RISK_REJECT"
                elif quantity > money(eco.max_qty):
                    reason = "MAX_QUANTITY"
                elif scenario.miss_every and int(oid, 16) % scenario.miss_every == 0:
                    reason = "ASSUMED_MISSED_FILL"
                if reason != "FILLED":
                    rejected[reason] += 1
                else:
                    fee = quantity * price * money(eco.taker_rate) * money(scenario.fee_multiplier)
                    cash -= fee
                    turnover += quantity * price
                    regime_return = market[max(0, signal_index)] / market[max(0, signal_index - 96)] - 1
                    regime = "up" if regime_return > .01 else "down" if regime_return < -.01 else "sideways"
                    positions[s] = Position(s, direction, index, decision_ms, ts, mid, price, quantity,
                                            quantity * price * money(candidate.stop_pct),
                                            price * (1 - direction * money(candidate.stop_pct)),
                                            price * (1 + direction * money(candidate.stop_pct) * money(candidate.target_r)),
                                            fee, quantity * mid * half_spread,
                                            quantity * mid * slip, Decimal(0), oid, regime)
                if capture:
                    opportunities.append({"opportunity_id": oid, "candidate_id": candidate.candidate_id,
                                          "symbol": symbol, "decision_ms": decision_ms, "direction": direction,
                                          "scenario": scenario.name, "outcome": reason})
        for s, position in tuple(positions.items()):
            high, low, opening = (money(float(panel.values[index, s, i])) for i in (1, 2, 0))
            hit_stop = low <= position.stop if position.direction == 1 else high >= position.stop
            hit_target = high >= position.target if position.direction == 1 else low <= position.target
            if hit_stop:
                stop_mid = min(opening, position.stop) if position.direction == 1 else max(opening, position.stop)
                close_position(s, index, stop_mid, "STOP_FIRST_IF_AMBIGUOUS")
            elif hit_target:
                close_position(s, index, position.target, "TARGET")
        if index == stop - 1:
            for s in tuple(positions):
                close_position(s, index, money(float(panel.values[index, s, 3])), "FOLD_LIQUIDATION")
        equity = cash + sum(p.quantity * p.direction * (money(float(panel.values[index, s, 3])) - p.entry_price)
                            for s, p in positions.items())
        peak = max(peak, equity)
        drawdown = max(drawdown, (peak - equity) / peak)
        day = ts // 86_400_000
        daily_pnl[day] = daily_pnl.get(day, 0.) + float(equity - previous_equity)
        previous_equity = equity
    if abs(float(cash - 10_000) - sum(t.net_pnl for t in trades)) > 1e-6:
        raise AssertionError("research cash ledger does not reconcile")
    metric = summarize(trades, daily_pnl)
    metric.update(max_drawdown_pct=float(drawdown * 100), turnover=float(turnover),
                  rejections=dict(rejected), symbol_universe=symbol_counts,
                  assumption="taker entry/exit; current instrument constraints; no queue inference")
    return ReplayResult(trades, daily_pnl, opportunities, dict(rejected), metric)


def summarize(trades: list[Trade], daily_pnl: dict[int, float]) -> dict[str, Any]:
    symbol_totals: dict[str, float] = {}
    regime_totals: dict[str, float] = {}
    for trade in trades:
        symbol_totals[trade.symbol] = symbol_totals.get(trade.symbol, 0.) + trade.net_pnl
        regime_totals[trade.regime] = regime_totals.get(trade.regime, 0.) + trade.net_pnl
    symbol_denominator = sum(abs(v) for v in symbol_totals.values())
    day_denominator = sum(abs(v) for v in daily_pnl.values())
    n = len(trades)
    return {"trades": n, "days": len(daily_pnl), "symbols_traded": len(symbol_totals),
            "mean_net_r": sum(t.net_r for t in trades) / n if n else None,
            "mean_gross_r": sum(t.gross_pnl / t.risk for t in trades) / n if n else None,
            "total_net_pnl": sum(t.net_pnl for t in trades),
            "gross_pnl": sum(t.gross_pnl for t in trades),
            "fees": sum(t.fees for t in trades), "funding": sum(t.funding for t in trades),
            "spread": sum(t.spread for t in trades), "slippage": sum(t.slippage for t in trades),
            "tail_loss_r": float(np.quantile([t.net_r for t in trades], .05)) if n else None,
            "symbol_concentration": max((abs(v) for v in symbol_totals.values()), default=0) / symbol_denominator if symbol_denominator else None,
            "day_concentration": max((abs(v) for v in daily_pnl.values()), default=0) / day_denominator if day_denominator else None,
            "symbol_net_pnl": dict(symbol_totals), "regime_net_pnl": dict(regime_totals)}


def paired_comparison(baseline: ReplayResult, treatment: ReplayResult) -> dict[str, Any]:
    """Intent-to-treat pairing retains missed/rejected opportunities as zero PnL.

    This is descriptive. Portfolio refilling is fully replayed in each arm; no
    post-hoc filtered trade list is mistaken for a portfolio simulation.
    """
    first = {row["opportunity_id"] for row in baseline.opportunities}
    second = {row["opportunity_id"] for row in treatment.opportunities}
    common = first & second
    base = {t.opportunity_id: t.net_pnl for t in baseline.trades}
    other = {t.opportunity_id: t.net_pnl for t in treatment.trades}
    deltas = [other.get(key, 0.) - base.get(key, 0.) for key in sorted(common)]
    return {"common_opportunities": len(common), "baseline_only": len(first - second),
            "treatment_only": len(second - first), "paired_net_delta": sum(deltas),
            "mean_paired_delta": sum(deltas) / len(deltas) if deltas else None,
            "unpaired_portfolio_delta": treatment.metrics["total_net_pnl"] - baseline.metrics["total_net_pnl"],
            "method": "common opportunity intent-to-treat; full independent portfolio replay"}


def trade_payload(trade: Trade) -> dict[str, Any]:
    return asdict(trade) | {"net_r": trade.net_r, "fill_timestamp": None,
                            "timestamp_note": "exit_bar_ms identifies OHLC bar; intrabar fill time unobserved"}
