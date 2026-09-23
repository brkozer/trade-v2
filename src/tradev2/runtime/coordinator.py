import json
import time
import uuid
from decimal import ROUND_DOWN, ROUND_UP, Decimal
from pathlib import Path
from typing import Any

import numpy as np

from tradev2.config.models import Mode, RuntimeConfig
from tradev2.config.privilege import require_runtime_mode
from tradev2.domain.account import PortfolioRisk
from tradev2.domain.evidence import EvidenceEnvelope, RunManifest
from tradev2.domain.instruments import InstrumentRules
from tradev2.domain.market import Candle, FundingSnapshot, OrderBookSnapshot
from tradev2.domain.orders import OrderIntent
from tradev2.evidence.journal import Journal
from tradev2.evidence.manifests import create_manifest, digest
from tradev2.marketdata.integrity import confirmed_window
from tradev2.paper.broker import PaperBroker
from tradev2.research.costs import SymbolEconomics
from tradev2.risk.engine import RiskLimits, assess
from tradev2.runtime.authority import AccountAuthority
from tradev2.runtime.candidates import CandidateSignal, load_candidate
from tradev2.venues.bybit_linear.public import PublicBybit


class SimulationRuntime:
    def __init__(self, root: Path, config: RuntimeConfig, *, resume: str | None = None) -> None:
        require_runtime_mode(config.mode)
        if config.mode not in {Mode.PAPER, Mode.SHADOW}:
            raise ValueError("simulation runtime requires paper or shadow")
        self.candidate = load_candidate(root, config)
        params = self.candidate.parameters()
        self.root, self.config = root.resolve(), config
        self.authority = AccountAuthority(self.root, f"simulation:{config.mode}:bybit", config.profile)
        self.authority.acquire()
        self.last_bars: dict[str, int] = {}
        self.marks: dict[str, Decimal] = {}
        self.pending_halt = False
        self.journal: Journal
        try:
            if resume is None:
                self.manifest = create_manifest(self.root, config, params)
                directory = self.root / "runtime" / config.mode / self.manifest.run_id
                self.journal = Journal(directory / "journal.sqlite")
                self.journal.register(self.manifest)
                self.broker = PaperBroker(config.initial_equity, target_r=self.candidate.target_r)
            else:
                if len(resume) != 32 or any(c not in "0123456789abcdef" for c in resume):
                    raise ValueError("invalid run identity")
                path = self.root / "runtime" / config.mode / resume / "journal.sqlite"
                if not path.is_file():
                    raise ValueError("resume journal missing")
                self.journal = Journal(path)
                if not self.journal.verify():
                    raise ValueError("resume journal integrity failed")
                row = self.journal.connection.execute("SELECT manifest FROM runs WHERE run_id=?",
                                                       (resume,)).fetchone()
                if row is None:
                    raise ValueError("resume manifest missing")
                self.manifest = RunManifest.model_validate_json(row[0])
                if (self.manifest.config_hash != digest(config.model_dump(mode="json"))
                        or self.manifest.parameter_hash != digest(params)):
                    raise ValueError("resume configuration/parameter mismatch")
                latest = self.journal.connection.execute(
                    "SELECT body FROM checkpoints WHERE run_id=? ORDER BY recorded_ms DESC LIMIT 1",
                    (resume,)).fetchone()
                if latest is None:
                    raise ValueError("resume checkpoint missing")
                state = json.loads(latest[0])
                self.broker = PaperBroker.restore(state["broker"])
                self.last_bars = state["last_bars"]
                self.pending_halt = state["pending_halt"]
            self.emit("runtime", {"status": "STARTING", "startup_phase": "PUBLIC_DATA_PENDING"})
        except Exception:
            if hasattr(self, "journal"):
                self.journal.close()
            self.authority.release()
            raise

    def emit(self, kind: str, payload: dict[str, Any], source_ms: int | None = None) -> None:
        now = time.time_ns() // 1_000_000
        if kind == "runtime":
            payload = {"mode": self.config.mode.value, "simulated": True,
                "live_disabled": True, "run_id": self.manifest.run_id,
                "candidate_id": self.candidate.candidate_id,
                "candidate_stage": self.candidate.stage,
                "candidate_family": self.candidate.family,
                "heartbeat_ms": now, "source_ms": source_ms,
                "pending_halt": self.pending_halt, **payload}
        self.journal.append(EvidenceEnvelope(event_id=uuid.uuid4().hex,
            run_id=self.manifest.run_id, kind=kind, recorded_ms=now,
            source="public_shadow_simulation", source_ms=source_ms, payload=payload))

    def evaluate(self, candles: list[Candle], book: OrderBookSnapshot,
                 rules: InstrumentRules, now_ms: int, candidate_signal: CandidateSignal,
                 candidate_rank: int | None = None) -> None:
        self.broker.observe(book, now_ms)
        if book.bids:
            position_item = self.broker.positions.get(book.symbol)
            self.marks[book.symbol] = (book.asks[0][0] if position_item is not None
                                       and position_item.position.side == "Sell" else book.bids[0][0])
        try:
            window = confirmed_window(candles, now_ms)
        except ValueError as exc:
            self.emit("rejection", {"symbol": book.symbol, "reason": str(exc)})
            return
        current = window[-1]
        # New closed bars only, plus realistic quote availability after that close.
        if (current.start_ms == self.last_bars.get(book.symbol)
                or now_ms - current.close_ms > current.interval_ms
                or book.exchange_event_ms is None or book.exchange_event_ms < current.close_ms):
            return
        self.last_bars[book.symbol] = current.start_ms
        closes = [float(c.close) for c in window]
        opportunity = digest([self.manifest.run_id, book.symbol, current.start_ms])[:32]
        if not np.isfinite(candidate_signal.strength):
            self.emit("rejection", {"symbol": book.symbol, "reason": "CANDIDATE_SIGNAL_UNKNOWN"})
            return
        signal, side = candidate_signal.active, candidate_signal.side
        features = candidate_signal.features
        spread = book.spread_bps
        payload: dict[str, Any] = {"opportunity_id": opportunity, "symbol": book.symbol,
            "candidate_id": self.config.candidate_id, "signal": signal,
            "features": features, "side": side,
            "candidate_rank": candidate_rank,
            "candidate_family": self.candidate.family, "candidate_stage": self.candidate.stage,
            "candidate_evidence": self.candidate.evidence,
            "decision_ms": now_ms, "candle_close_ms": current.close_ms,
            "spread_bps": str(spread) if spread is not None else None,
            "fee_state": "EXPLICIT_CONSERVATIVE_SIMULATION_ESTIMATE",
            "maker_fee": str(self.broker.maker_fee), "taker_fee": str(self.broker.taker_fee),
            "funding_state": "SETTLED_HISTORY_ENTRY_NOTIONAL_ESTIMATE",
            "simulated": True}
        item = self.broker.positions.get(book.symbol)
        if item is not None:
            held = max(0, (current.close_ms-item.opened_ms)//current.interval_ms)
            exit_reason = self.candidate.exit_reason(closes, held)
            if exit_reason:
                self.broker.exit(book, now_ms, exit_reason)
        reason = "NO_SIGNAL"
        if signal:
            reason = "EXPOSURE_EXISTS" if book.symbol in self.broker.positions else "PENDING_EXISTS"
            pending = any(o.intent.symbol == book.symbol and o.unresolved
                          for o in self.broker.orders.values())
            if book.symbol not in self.broker.positions and not pending:
                if self.pending_halt:
                    reason = "HALT_LATCHED"
                elif spread is None or spread > self.config.max_spread_bps:
                    reason = "SPREAD_UNKNOWN_OR_HIGH"
                elif book.exchange_event_ms > now_ms or now_ms-book.exchange_event_ms > self.config.source_max_age_ms:
                    reason = "SOURCE_STALE"
                else:
                    if side is None:
                        raise ValueError("active candidate has no direction")
                    stop_pct = self.candidate.stop_pct
                    raw_price = book.bids[0][0] if side == "Buy" else book.asks[0][0]
                    rounding = ROUND_DOWN if side == "Buy" else ROUND_UP
                    price = (raw_price/rules.tick_size).to_integral_value(rounding=rounding)*rules.tick_size
                    stop = (price * (1-stop_pct if side == "Buy" else 1+stop_pct) / rules.tick_size
                            ).to_integral_value(rounding=rounding)*rules.tick_size
                    intent = OrderIntent(owner_id=self.manifest.run_id, decision_id=opportunity,
                        symbol=book.symbol, side=side, quantity=self.config.initial_equity / price,
                        reference_price=price, stop_price=stop, available_ms=now_ms)
                    allocation = self._risk(intent, rules)
                    payload["risk"] = allocation
                    reason = str(allocation["reason"])
                    if allocation["action"] in {"ALLOW", "RESIZE"}:
                        self.broker.submit(intent.model_copy(update={"quantity": Decimal(allocation["quantity"])}), rules)
                        reason = "SIMULATED_MAKER_SUBMITTED"
        payload["reason"] = reason
        payload["decision"] = "TRADE" if reason == "SIMULATED_MAKER_SUBMITTED" else "NO_TRADE"
        self.emit("opportunity", payload, current.close_ms)
        self.emit("decision", payload, current.close_ms)
        if payload["decision"] == "NO_TRADE":
            self.emit("rejection", payload, current.close_ms)

    def _risk(self, intent: OrderIntent, rules: InstrumentRules) -> dict[str, Any]:
        account = self.broker.account(self.marks)
        equity = Decimal(account["equity"]) if account["equity"] is not None else None
        notional = sum((p.position.quantity*p.position.entry_price for p in self.broker.positions.values()), Decimal(0))
        pending_risk = sum(((o.intent.quantity-o.filled)*abs(o.intent.reference_price-o.intent.stop_price)
                            for o in self.broker.orders.values() if o.unresolved), Decimal(0))
        pending_notional = sum(((o.intent.quantity-o.filled)*o.intent.reference_price
                                for o in self.broker.orders.values() if o.unresolved), Decimal(0))
        limits = RiskLimits(per_trade=self.config.initial_equity*self.config.risk_fraction,
            total_open=self.config.initial_equity*self.config.max_open_risk_fraction,
            directional_notional=self.config.initial_equity*Decimal(".8"),
            correlated_notional=self.config.initial_equity*Decimal(".5"),
            symbol_notional=self.config.initial_equity*Decimal(".2"),
            daily_loss=self.config.initial_equity*Decimal(".05"),
            equity_floor=self.config.initial_equity*Decimal(".8"),
            roundtrip_cost_rate=self.broker.maker_fee+self.broker.taker_fee+Decimal(".0004"))
        portfolio = PortfolioRisk(equity=equity,
            available_margin=max(Decimal(0), self.broker.cash-notional-pending_notional),
            open_risk=Decimal(account["open_risk"]), pending_risk=pending_risk,
            directional_notional=notional+pending_notional,
            correlated_notional=notional+pending_notional,  # unknown correlation => one bucket
            symbol_notional=Decimal(0), daily_pnl=self.broker.cash-self.broker.initial_equity,
            reconciled=True, protection_healthy=all(p.position.protection_healthy
                                                   for p in self.broker.positions.values()))
        return assess(intent, rules, portfolio, limits).model_dump(mode="json")

    def checkpoint(self) -> None:
        self.journal.checkpoint(uuid.uuid4().hex, self.manifest.run_id, time.time_ns()//1_000_000,
            {"broker": self.broker.checkpoint(), "last_bars": self.last_bars,
             "pending_halt": self.pending_halt})

    def poll(self, client: PublicBybit) -> None:
        latest: int | None = None
        candidate_inputs: dict[str, list[Candle]] = {}
        books: dict[str, OrderBookSnapshot] = {}
        instruments: dict[str, InstrumentRules] = {}
        funding_inputs: dict[str, list[FundingSnapshot]] = {}
        for symbol in self.config.symbols:
            rules = client.instruments(symbol).get(symbol)
            if rules is None:
                raise ValueError(f"instrument unavailable: {symbol}")
            candles = client.candles(symbol, limit=self.candidate.required_bars + 1)
            book = client.orderbook(symbol)
            now = time.time_ns() // 1_000_000
            self.emit("market", {"symbol": symbol, "spread_bps": str(book.spread_bps)
                if book.spread_bps is not None else None,
                "instrument": rules.model_dump(mode="json"), "tracked": True}, book.exchange_event_ms)
            funding_history = client.funding_history(symbol)
            for funding in funding_history:
                self.broker.apply_funding(funding)
            candidate_inputs[symbol] = confirmed_window(
                candles, now, minimum=self.candidate.required_bars)
            books[symbol], instruments[symbol] = book, rules
            funding_inputs[symbol] = funding_history
            latest = min(latest, book.exchange_event_ms) if latest is not None and book.exchange_event_ms is not None else book.exchange_event_ms
        economics: dict[str, SymbolEconomics] = {}
        if self.candidate.requires_funding:
            for symbol in self.config.symbols:
                    settled: set[tuple[int, Decimal]] = set()
                    for funding in funding_inputs[symbol]:
                        rate, funding_ms = funding.rate, funding.funding_ms
                        if rate is not None and funding_ms is not None and funding.status in {
                            "KNOWN", "KNOWN_ZERO"
                        }:
                            settled.add((funding_ms, rate))
                    observations = sorted(settled)
                    if len(observations) < 2:
                        raise ValueError("settled funding coverage insufficient for live factor")
                    book, rules = books[symbol], instruments[symbol]
                    spread = book.spread_bps
                    if spread is None or rules.max_qty is None:
                        raise ValueError("factor spread or exchange maximum unknown")
                    maximum_qty = rules.max_qty
                    economics[symbol] = SymbolEconomics(float(self.broker.maker_fee),
                        float(self.broker.taker_fee), float(spread), float(rules.qty_step),
                        float(rules.min_qty), float(rules.min_notional), float(maximum_qty),
                        np.asarray([[float(t), float(rate)] for t, rate in observations],
                                   dtype=np.float64), "public_settled_funding_simulation_fee_proxy")
        signals = self.candidate.signals(candidate_inputs, economics)
        ranked = sorted(self.config.symbols,
                        key=lambda symbol: (-abs(signals[symbol].strength), symbol))
        for rank, symbol in enumerate(ranked, start=1):
            self.evaluate(candidate_inputs[symbol], books[symbol], instruments[symbol],
                          time.time_ns() // 1_000_000, signals[symbol], rank)
        for kind, payload in self.broker.drain():
            self.emit(kind, payload)
        self.emit("account", self.broker.account(self.marks))
        self.emit("runtime", {"status": "RUNNING", "engine_alive": True,
            "startup_phase": "SIMULATION_READY", "authority": "LOCAL_SIMULATION_LOCK"}, latest)
        self.checkpoint()

    def close(self, failed: bool = False) -> None:
        try:
            self.checkpoint()
            self.emit("runtime", {"status": "FAILED" if failed else "STOPPED",
                "engine_alive": False, "open_positions": len(self.broker.positions)})
        finally:
            self.journal.close()
            self.authority.release()
