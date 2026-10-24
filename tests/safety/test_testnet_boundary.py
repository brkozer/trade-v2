import json
from decimal import Decimal

import httpx
import pytest

from tradev2.config.models import Mode, RuntimeConfig
from tradev2.domain.orders import OrderIntent
from tradev2.runtime.startup import REQUIRED
from tradev2.testnet.transport import (
    TestnetCredentials as Credentials,
)
from tradev2.testnet.transport import TestnetLinear as LinearTransport
from tradev2.testnet.transport import order_link_id


def test_testnet_requires_dedicated_mode_authorization_and_env(monkeypatch) -> None:
    monkeypatch.delenv("TRADEV2_TESTNET_ENABLE", raising=False)
    credentials = Credentials("fake-testnet-key", "fake-testnet-secret")
    assert "secret" not in repr(credentials)
    with pytest.raises(PermissionError, match="configuration"):
        LinearTransport(RuntimeConfig(mode=Mode.PAPER), credentials=credentials)
    with pytest.raises(PermissionError, match="enable switch"):
        LinearTransport(RuntimeConfig(mode=Mode.TESTNET, testnet_authorized=True),
                      credentials=credentials)


def test_mock_testnet_ack_never_becomes_fill_or_foreign_cancel(monkeypatch) -> None:
    monkeypatch.setenv("TRADEV2_TESTNET_ENABLE", "1")
    observed: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        observed.append(request)
        assert request.url.host == "api-testnet.bybit.com"
        assert request.headers.get("X-BAPI-SIGN")
        return httpx.Response(200, json={"retCode": 0, "result": {"orderId": "ack-only"}})

    config = RuntimeConfig(mode=Mode.TESTNET, testnet_authorized=True)
    intent = OrderIntent(owner_id="run", decision_id="decision", symbol="BTCUSDT",
                         side="Buy", quantity=Decimal("0.001"),
                         reference_price=Decimal("100"), stop_price=Decimal("90"),
                         available_ms=1)
    with LinearTransport(config, transport=httpx.MockTransport(handler),
                         credentials=Credentials("fake-key", "fake-secret")) as client:
        with pytest.raises(PermissionError, match="entry blocked"):
            client.place_entry("run", intent, Decimal("100"))
        state = client.authorize_entry({name: True for name in REQUIRED if name != "fees"})
        assert state.status == "ENTRY_BLOCKED"
        assert client.wallet()["result"]["orderId"] == "ack-only"
        with pytest.raises(PermissionError, match="foreign"):
            client.cancel_owned("BTCUSDT", "tv2_" + "a" * 32)
        state = client.authorize_entry({name: True for name in REQUIRED})
        assert state.status == "ENTRY_ENABLED"
        result = client.place_entry("run", intent, Decimal("100"))
        assert result["status"] == "ACK_UNRESOLVED"
        assert result["order_link_id"] == order_link_id("run", "decision", "entry")
        posted = json.loads(observed[-1].content)
        assert posted["reduceOnly"] is False and posted["orderLinkId"] == result["order_link_id"]
        assert client.cancel_owned("BTCUSDT", result["order_link_id"])["status"] == "CANCEL_ACK_UNRESOLVED"
        with pytest.raises(PermissionError, match="allowlisted"):
            client._request("POST", "/v5/asset/transfer/inter-transfer", body={})


def test_simulation_and_api_code_never_import_the_testnet_package() -> None:
    import ast
    from pathlib import Path

    package = Path(__file__).resolve().parents[2] / "src/tradev2"
    offenders: list[str] = []
    for directory in ("paper", "runtime", "api", "research", "alpha", "marketdata", "venues"):
        for path in (package / directory).rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                names = ([alias.name for alias in node.names] if isinstance(node, ast.Import)
                         else [node.module or ""] if isinstance(node, ast.ImportFrom) else [])
                if any(name == "tradev2.testnet" or name.startswith("tradev2.testnet.")
                       for name in names):
                    offenders.append(str(path.relative_to(package)))
    assert offenders == []
    cli = (package / "cli.py").read_text(encoding="utf-8")
    assert "TestnetLinear" not in cli and "testnet.transport" not in cli


def test_transport_errors_never_carry_credentials(monkeypatch) -> None:
    monkeypatch.setenv("TRADEV2_TESTNET_ENABLE", "1")
    from tradev2.testnet.transport import TestnetTransportError

    def failing(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"retCode": 10003})

    def unreachable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    config = RuntimeConfig(mode=Mode.TESTNET, testnet_authorized=True)
    for handler in (failing, unreachable):
        with LinearTransport(config, transport=httpx.MockTransport(handler),
                             credentials=Credentials("visible-key-123", "visible-secret-456")) as client:
            with pytest.raises(TestnetTransportError) as caught:
                client.wallet()
        rendered = repr(caught.value) + str(caught.value) + repr(caught.value.__cause__)
        assert "visible-key-123" not in rendered and "visible-secret-456" not in rendered
        assert caught.value.__cause__ is None and caught.value.__suppress_context__


def test_owned_writes_reject_non_finite_prices(monkeypatch) -> None:
    monkeypatch.setenv("TRADEV2_TESTNET_ENABLE", "1")
    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200, json={"retCode": 0, "result": {}})

    config = RuntimeConfig(mode=Mode.TESTNET, testnet_authorized=True)
    intent = OrderIntent(owner_id="run", decision_id="decision", symbol="BTCUSDT", side="Sell",
                         quantity=Decimal("0.001"), reference_price=Decimal("100"),
                         stop_price=Decimal("110"), available_ms=1)
    with LinearTransport(config, transport=httpx.MockTransport(handler),
                         credentials=Credentials("fake-key", "fake-secret")) as client:
        client.authorize_entry({name: True for name in REQUIRED})
        for bad in (Decimal("Infinity"), Decimal("NaN")):
            with pytest.raises((ValueError, PermissionError)):
                client.place_reduce_only("run", intent, bad, "exit")
        link = client.place_reduce_only("run", intent, Decimal("101"), "exit")["order_link_id"]
        with pytest.raises(PermissionError):
            client.amend_owned("BTCUSDT", link, Decimal("Infinity"))
    assert len(sent) == 1
