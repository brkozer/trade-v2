import pytest

from tradev2.strategies.reference import (
    maker_eligible,
    reference_entry,
    reference_exit,
    reference_levels,
    wilder_rsi,
)


def test_legacy_rule_golden_cases() -> None:
    # Frozen public rules inspected at Bybit e136564, v4bot/rsi_candidate.py.
    down = [10., 9., 8., 7., 6., 5.]
    up = list(reversed(down))
    assert wilder_rsi(down, 4) == 0
    assert reference_entry(down, 900000)
    assert not reference_entry(down, 900000, 900000)
    assert reference_exit(up, 1) == 'RSI_EXIT'
    assert reference_exit(down, 32) == 'TIME_STOP'
    assert reference_exit(down, 31) is None
    assert reference_levels(100) == pytest.approx((98, 102.8))
    assert maker_eligible(100, 100, 0, 60000)
    assert not maker_eligible(100, 100, 0, 60001)
    assert not maker_eligible(100, 100, 1, 0)  # intentional negative-age hardening
