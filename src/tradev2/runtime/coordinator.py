import json
import time
import uuid
from dataclasses import asdict
from decimal import ROUND_DOWN, Decimal
from pathlib import Path
from typing import Any

from tradev2.config.models import Mode, RuntimeConfig
from tradev2.config.privilege import require_runtime_mode
from tradev2.domain.account import PortfolioRisk
from tradev2.domain.evidence import EvidenceEnvelope, RunManifest
from tradev2.domain.instruments import InstrumentRules
from tradev2.domain.market import Candle, OrderBookSnapshot
from tradev2.domain.orders import OrderIntent
from tradev2.evidence.journal import Journal
from tradev2.evidence.manifests import create_manifest, digest
from tradev2.marketdata.integrity import confirmed_window
from tradev2.paper.broker import PaperBroker
from tradev2.risk.engine import RiskLimits, assess
from tradev2.runtime.authority import AccountAuthority
from tradev2.strategies.reference import (
    REFERENCE_PARAMS,
    reference_entry,
    reference_exit,
    wilder_rsi,
)
from tradev2.venues.bybit_linear.public import PublicBybit


class SimulationRuntime:
    def __init__(self, root: Path, config: RuntimeConfig, *, resume: str | None = None) -> None:
        require_runtime_mode(config.mode)
        if config.mode not in {Mode.PAPER, Mode.SHADOW}:
            raise ValueError("simulation runtime requires paper or shadow")
        if config.candidate_id != REFERENCE_PARAMS.candidate_id:
            raise ValueError("runtime candidate not implemented; cannot substitute reference")
        self.root, self.config = root.resolve(), config
        self.authority = AccountAuthority(self.root, f"simulation:{config.mode}:bybit", config.profile)
        self.authority.acquire()
        self.last_bars: dict[str, int] = {}
        self.marks: dict[str, Decimal] = {}
        self.pending_halt = False
        self.journal: Journal
        try:
            if resume is None:
                self.manifest = create_manifest(self.root, config, asdict(REFERENCE_PARAMS))
                directory = self.root / "runtime" / config.mode / self.manifest.run_id
                self.journal = Journal(directory / "journal.sqlite")
                self.journal.register(self.manifest)
                self.broker = PaperBroker(config.initial_equity)
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
                        or self.manifest.parameter_hash != digest(asdict(REFERENCE_PARAMS))):
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
                "heartbeat_ms": now, "source_ms": source_ms,
                "pending_halt": self.pending_halt, **payload}
        self.journal.append(EvidenceEnvelope(event_id=uuid.uuid4().hex,
            run_id=self.manifest.run_id, kind=kind, recorded_ms=now,
            source="public_shadow_simulation", source_ms=source_ms, payload=payload))

    def evaluate(self, candles: list[Candle], book: OrderBookSnapshot,
                 rules: InstrumentRules, now_ms: int) -> None:
        self.broker.observe(book, now_ms)
        if book.bids:
            self.marks[book.symbol] = book.bids[0][0]
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
        signal = reference_entry(closes, current.start_ms)
        spread = book.spread_bps
        payload: dict[str, Any] = {"opportunity_id": opportunity, "symbol": book.symbol,
            "candidate_id": REFERENCE_PARAMS.candidate_id, "signal": signal,
            "features": {"rsi": wilder_rsi(closes, REFERENCE_PARAMS.entry_period)},
            "decision_ms": now_ms, "candle_close_ms": current.close_ms,
            "spread_bps": str(spread) if spread is not None else None,
            "fee_state": "EXPLICIT_CONSERVATIVE_SIMULATION_ESTIMATE",
            "maker_fee": str(self.broker.maker_fee), "taker_fee": str(self.broker.taker_fee),
            "funding_state": "SETTLED_HISTORY_ENTRY_NOTIONAL_ESTIMATE",
            "simulated": True}
        item = self.broker.positions.get(book.symbol)
        if item is not None:
            held = max(0, (current.close_ms-item.opened_ms)//current.interval_ms)
            exit_reason = reference_exit(closes, held)
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
                    price = (book.bids[0][0]/rules.tick_size).to_integral_value(rounding=ROUND_DOWN)*rules.tick_size
                    stop = (price * (1-Decimal(str(REFERENCE_PARAMS.stop_pct))) / rules.tick_size
                            ).to_integral_value(rounding=ROUND_DOWN)*rules.tick_size
                    intent = OrderIntent(owner_id=self.manifest.run_id, decision_id=opportunity,
                        symbol=book.symbol, side="Buy", quantity=self.config.initial_equity / price,
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
        pending_risk = sum(((o.intent.quantity-o.filled)*(o.intent.reference_price-o.intent.stop_price)
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
        for symbol in self.config.symbols:
            rules = client.instruments(symbol).get(symbol)
            if rules is None:
                raise ValueError(f"instrument unavailable: {symbol}")
            candles = client.candles(symbol, limit=65)
            book = client.orderbook(symbol)
            now = time.time_ns() // 1_000_000
            self.emit("market", {"symbol": symbol, "spread_bps": str(book.spread_bps)
                if book.spread_bps is not None else None,
                "instrument": rules.model_dump(mode="json"), "tracked": True}, book.exchange_event_ms)
            for funding in client.funding_history(symbol):
                self.broker.apply_funding(funding)
            self.evaluate(candles, book, rules, now)
            latest = min(latest, book.exchange_event_ms) if latest is not None and book.exchange_event_ms is not None else book.exchange_event_ms
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
