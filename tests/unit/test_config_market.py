from decimal import Decimal as D

import httpx
import pytest
from pydantic import ValidationError

from tradev2.config.models import Mode, RuntimeConfig
from tradev2.config.privilege import override_mode, require_runtime_mode
from tradev2.domain.market import Candle, FeeSchedule
from tradev2.marketdata.integrity import OrderBook, confirmed_window
from tradev2.venues.bybit_linear.fees import resolve_fee
from tradev2.venues.bybit_linear.public import PublicBybit


@pytest.mark.parametrize("mode", [Mode.PAPER, Mode.SHADOW, Mode.TESTNET, Mode.RESEARCH])
def test_cli_cannot_escalate_to_live(mode):
    with pytest.raises(PermissionError):
        override_mode(mode, Mode.LIVE)


def test_downgrade_does_not_enable_transport():
    assert override_mode(Mode.LIVE, Mode.PAPER) == Mode.PAPER
    for mode in (Mode.LIVE, Mode.TESTNET):
        with pytest.raises(PermissionError):
            require_runtime_mode(mode)


@pytest.mark.parametrize("key", ["risk_fracton", "api_url", "production_endpoint", "api_secret"])
def test_unknown_configuration_is_rejected(key):
    with pytest.raises(ValidationError):
        RuntimeConfig.model_validate({"mode": "testnet", key: "value"})


def candle(start, confirmed=True):
    return Candle(symbol="BTCUSDT", start_ms=start, interval_ms=60000, open=D(100),
                  high=D(101), low=D(99), close=D(100), volume=D(10), confirmed=confirmed)


def test_candle_availability_and_gap():
    assert len(confirmed_window([candle(0), candle(60000)], 60000, 1)) == 1
    with pytest.raises(ValueError, match="GAP"):
        confirmed_window([candle(0), candle(120000)], 180000, 2)
    with pytest.raises(ValueError, match="INSUFFICIENT"):
        confirmed_window([candle(0, False)], 60000, 1)


def msg(kind="snapshot", seq=10, u=100):
    return {"type": kind, "ts": 1000, "cts": 999,
            "data": {"s": "BTCUSDT", "b": [["100", "2"]], "a": [["101", "3"]],
                     "seq": seq, "u": u}}


def test_book_semantics_and_reseed():
    book = OrderBook("BTCUSDT")
    with pytest.raises(ValueError, match="reseed"):
        book.apply(msg("delta"), 1001)
    first = book.apply(msg(), 1001)
    assert first.matching_engine_ms == 999
    # Non-contiguous IDs are legal; do not invent u+1 continuity.
    assert book.apply(msg("delta", 15, 130), 1002).update_id == 130
    with pytest.raises(ValueError, match="out-of-order"):
        book.apply(msg("delta", 14, 129), 1003)
    assert not book.seeded
    book.apply(msg(), 1004)
    assert book.apply(msg(), 1005).exchange_sequence == 10  # repeated snapshot valid


def test_book_unknown_spread_and_deleted_level():
    book = OrderBook("BTCUSDT")
    book.apply(msg(), 1001)
    change = msg("delta", 20, 150)
    change["data"]["a"] = [["101", "0"]]
    assert book.apply(change, 1002).spread_bps is None


def test_fee_unknown_not_cheapest_and_stale_not_usable():
    stale = FeeSchedule(symbol="BTCUSDT", maker=D(".0002"), taker=D(".00055"),
                        source="measured", observed_ms=100, valid_until_ms=200, verified=True)
    with pytest.raises(ValueError, match="FEE_UNKNOWN"):
        resolve_fee("BTCUSDT", 201, stale, None, None)
    conservative = stale.model_copy(update={"symbol": "*", "taker": D(".0011"),
                                           "valid_until_ms": 300})
    assert resolve_fee("BTCUSDT", 201, stale, None, conservative).taker == D(".0011")


def test_public_client_cannot_send_private_requests_and_filters_unclosed():
    paths = []

    def handler(request):
        paths.append(request.url.path)
        assert request.method == "GET"
        assert "x-bapi-api-key" not in request.headers
        return httpx.Response(200, json={"retCode": 0, "time": 120000, "result": {
            "list": [["120000", "100", "101", "99", "100", "10"],
                     ["60000", "100", "101", "99", "100", "10"]]}})

    client = PublicBybit(transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(PermissionError):
            client.get("/v5/order/create")
        rows = client.candles("BTCUSDT", interval_minutes=1)
        assert [c.confirmed for c in rows] == [True, False]
        assert paths == ["/v5/market/kline"]
        assert not hasattr(client, "submit")
    finally:
        client.close()

