"""Dedicated Bybit Linear TESTNET boundary. Never import into paper/shadow.

Constructing this transport requires a testnet-mode config, a dedicated
authorization switch and testnet-only environment credentials. Mainnet is
not configurable. REST acknowledgements are never treated as fills.
"""

import hashlib
import hmac
import json
import os
import time
from collections.abc import Mapping
from decimal import Decimal
from typing import Any
from urllib.parse import urlencode

import httpx

from tradev2.config.models import Mode, RuntimeConfig
from tradev2.domain.orders import OrderIntent
from tradev2.reconciliation.snapshot import ReconciliationInput, reconcile_snapshot
from tradev2.runtime.startup import StartupState, startup_gate

TESTNET_REST = "https://api-testnet.bybit.com"
READ_PATHS = frozenset({"/v5/account/wallet-balance", "/v5/account/fee-rate",
                        "/v5/position/list", "/v5/position/closed-pnl",
                        "/v5/order/realtime", "/v5/order/history", "/v5/execution/list"})
WRITE_PATHS = frozenset({"/v5/order/create", "/v5/order/amend", "/v5/order/cancel",
                         "/v5/position/trading-stop"})


class TestnetCredentials:
    def __init__(self, key: str, secret: str) -> None:
        if not key or not secret:
            raise ValueError("dedicated testnet credentials missing")
        self.key = key
        self.secret = secret

    def __repr__(self) -> str:
        return "TestnetCredentials(REDACTED)"

    @classmethod
    def from_environment(cls) -> "TestnetCredentials":
        if os.environ.get("TRADEV2_TESTNET_ENABLE") != "1":
            raise PermissionError("dedicated TRADEV2_TESTNET_ENABLE=1 is required")
        key = os.environ.get("TRADEV2_TESTNET_API_KEY", "")
        secret = os.environ.get("TRADEV2_TESTNET_API_SECRET", "")
        return cls(key, secret)


def order_link_id(run_id: str, decision_id: str, purpose: str) -> str:
    if not all((run_id, decision_id, purpose)):
        raise ValueError("order identity requires run, decision and purpose")
    return "tv2_" + hashlib.sha256(f"{run_id}|{decision_id}|{purpose}".encode()).hexdigest()[:32]


class TestnetLinear:
    def __init__(self, config: RuntimeConfig, *, transport: httpx.BaseTransport | None = None,
                 credentials: TestnetCredentials | None = None) -> None:
        if config.mode != Mode.TESTNET or not config.testnet_authorized:
            raise PermissionError("testnet configuration and authorization required")
        if os.environ.get("TRADEV2_TESTNET_ENABLE") != "1":
            raise PermissionError("dedicated testnet enable switch required")
        self._credentials = credentials or TestnetCredentials.from_environment()
        self._client = httpx.Client(base_url=TESTNET_REST, timeout=10, transport=transport,
                                    follow_redirects=False, trust_env=False)
        self._entry_enabled = False
        self._identity_verified = False
        self._owned_links: set[str] = set()
        self.profile = config.profile

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "TestnetLinear":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def authorize_entry(self, checks: dict[str, bool | None]) -> StartupState:
        state = startup_gate(checks)
        self._identity_verified = checks.get("venue_identity") is True and checks.get("account_identity") is True
        self._entry_enabled = state.status == "ENTRY_ENABLED"
        return state

    def restore_owned_link(self, link_id: str, proof: ReconciliationInput) -> None:
        """Recovery requires complete matching journal/exchange ownership evidence."""
        if (not self._identity_verified or not link_id.startswith("tv2_") or len(link_id) != 36
                or not reconcile_snapshot(proof).entry_permitted
                or link_id not in {order.client_id for order in proof.journal_orders}):
            raise PermissionError("owned order identity or reconciliation proof missing")
        self._owned_links.add(link_id)

    def _request(self, method: str, path: str,
                 params: Mapping[str, str] | None = None,
                 body: Mapping[str, Any] | None = None) -> dict[str, Any]:
        if (method == "GET" and path not in READ_PATHS) or (method == "POST" and path not in WRITE_PATHS):
            raise PermissionError("testnet endpoint not allowlisted")
        if method not in {"GET", "POST"}:
            raise PermissionError("unsupported testnet HTTP method")
        timestamp = str(time.time_ns() // 1_000_000)
        window = "5000"
        query = urlencode(sorted((params or {}).items())) if method == "GET" else ""
        encoded = json.dumps(body, separators=(",", ":"), sort_keys=True) if method == "POST" else ""
        signed = timestamp + self._credentials.key + window + (query if method == "GET" else encoded)
        signature = hmac.new(self._credentials.secret.encode(), signed.encode(), hashlib.sha256).hexdigest()
        headers = {"X-BAPI-API-KEY": self._credentials.key, "X-BAPI-TIMESTAMP": timestamp,
                   "X-BAPI-RECV-WINDOW": window, "X-BAPI-SIGN": signature,
                   "X-BAPI-SIGN-TYPE": "2", "Content-Type": "application/json"}
        response = self._client.request(method, path, params=query if method == "GET" else None,
                                        content=encoded if method == "POST" else None,
                                        headers=headers)
        response.raise_for_status()
        payload: dict[str, Any] = response.json()
        if payload.get("retCode") != 0:
            raise ValueError(f"testnet returned retCode={payload.get('retCode')}; state remains unresolved")
        return payload

    def wallet(self) -> dict[str, Any]:
        return self._request("GET", "/v5/account/wallet-balance", {"accountType": "UNIFIED"})

    def fee_rate(self, symbol: str) -> dict[str, Any]:
        return self._request("GET", "/v5/account/fee-rate", {"category": "linear", "symbol": symbol})

    def positions(self, symbol: str) -> dict[str, Any]:
        return self._request("GET", "/v5/position/list", {"category": "linear", "symbol": symbol})

    def open_orders(self, symbol: str) -> dict[str, Any]:
        return self._request("GET", "/v5/order/realtime", {"category": "linear", "symbol": symbol})

    def order_history(self, symbol: str) -> dict[str, Any]:
        return self._request("GET", "/v5/order/history", {"category": "linear", "symbol": symbol})

    def executions(self, symbol: str) -> dict[str, Any]:
        return self._request("GET", "/v5/execution/list", {"category": "linear", "symbol": symbol})

    def closed_pnl(self, symbol: str) -> dict[str, Any]:
        return self._request("GET", "/v5/position/closed-pnl", {"category": "linear", "symbol": symbol})

    def place_entry(self, run_id: str, intent: OrderIntent, price: Decimal) -> dict[str, Any]:
        if not self._entry_enabled or not self._identity_verified or intent.owner_id != run_id:
            raise PermissionError("entry blocked until verified account startup and ownership")
        if not price.is_finite() or price <= 0 or intent.quantity <= 0:
            raise ValueError("invalid testnet entry price or quantity")
        link = order_link_id(run_id, intent.decision_id, "entry")
        payload = {"category": "linear", "symbol": intent.symbol, "side": intent.side,
                   "orderType": "Limit", "qty": str(intent.quantity), "price": str(price),
                   "timeInForce": "PostOnly", "positionIdx": 0, "reduceOnly": False,
                   "orderLinkId": link}
        result = self._request("POST", "/v5/order/create", body=payload)
        self._owned_links.add(link)
        return {"status": "ACK_UNRESOLVED", "order_link_id": link, "exchange_ack": result.get("result")}

    def place_reduce_only(self, run_id: str, intent: OrderIntent,
                          price: Decimal, purpose: str) -> dict[str, Any]:
        if not self._identity_verified or intent.owner_id != run_id:
            raise PermissionError("verified testnet account and order ownership required")
        if price <= 0 or intent.quantity <= 0 or purpose not in {"stop", "target", "exit"}:
            raise ValueError("invalid owned reduce-only order")
        link = order_link_id(run_id, intent.decision_id, purpose)
        result = self._request("POST", "/v5/order/create", body={
            "category": "linear", "symbol": intent.symbol, "side": intent.side,
            "orderType": "Limit", "qty": str(intent.quantity), "price": str(price),
            "timeInForce": "GTC", "positionIdx": 0, "reduceOnly": True,
            "orderLinkId": link})
        self._owned_links.add(link)
        return {"status": "ACK_UNRESOLVED", "order_link_id": link, "exchange_ack": result.get("result")}

    def cancel_owned(self, symbol: str, link_id: str) -> dict[str, Any]:
        if not self._identity_verified or link_id not in self._owned_links:
            raise PermissionError("cannot cancel an unverified or foreign order")
        result = self._request("POST", "/v5/order/cancel", body={
            "category": "linear", "symbol": symbol, "orderLinkId": link_id})
        return {"status": "CANCEL_ACK_UNRESOLVED", "order_link_id": link_id,
                "exchange_ack": result.get("result")}

    def amend_owned(self, symbol: str, link_id: str, price: Decimal) -> dict[str, Any]:
        if not self._identity_verified or link_id not in self._owned_links or price <= 0:
            raise PermissionError("cannot amend unverified or foreign order")
        result = self._request("POST", "/v5/order/amend", body={
            "category": "linear", "symbol": symbol, "orderLinkId": link_id, "price": str(price)})
        return {"status": "AMEND_ACK_UNRESOLVED", "order_link_id": link_id,
                "exchange_ack": result.get("result")}

    def set_stop(self, symbol: str, stop: Decimal, proof: ReconciliationInput,
                 position_index: int = 0) -> dict[str, Any]:
        """Protect an exactly owned position; the ACK still needs read-back proof.

        An unprotected position may be repaired, but no other reconciliation
        disagreement is acceptable. A successful request never enables entry.
        """
        result = reconcile_snapshot(proof)
        allowed_missing = frozenset({"PROTECTION_UNVERIFIED"})
        owned = [position for position in proof.exchange_positions
                 if position.symbol == symbol and position.owner_id == proof.owner_id
                 and position.quantity > 0]
        if (not self._identity_verified or stop <= 0 or position_index not in {0, 1, 2}
                or not owned or set(result.missing) - allowed_missing):
            raise PermissionError("verified owned position and complete reconciliation required")
        ack = self._request("POST", "/v5/position/trading-stop", body={
            "category": "linear", "symbol": symbol, "tpslMode": "Full",
            "positionIdx": position_index, "stopLoss": str(stop), "slTriggerBy": "MarkPrice"})
        return {"status": "PROTECTION_ACK_UNVERIFIED", "exchange_ack": ack.get("result")}
