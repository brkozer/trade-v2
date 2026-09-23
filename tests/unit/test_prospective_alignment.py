import pytest

from tradev2.research.datasets import BAR_MS
from tradev2.research.prospective_alignment import first_eligible_open_ms


def test_joint_availability_waits_for_later_source() -> None:
    opened = 100 * BAR_MS
    assert first_eligible_open_ms(
        candle_open_ms=opened, candle_safe_available_ms=opened + BAR_MS + 5_000,
        oi_timestamp_ms=opened, oi_safe_available_ms=opened + BAR_MS + 20_000,
    ) == opened + 2 * BAR_MS
    assert first_eligible_open_ms(
        candle_open_ms=opened, candle_safe_available_ms=opened + 2 * BAR_MS + 5_000,
        oi_timestamp_ms=opened, oi_safe_available_ms=opened + BAR_MS + 20_000,
    ) == opened + 3 * BAR_MS


def test_exact_boundary_still_requires_next_open() -> None:
    opened = 100 * BAR_MS
    assert first_eligible_open_ms(
        candle_open_ms=opened, candle_safe_available_ms=opened + 2 * BAR_MS,
        oi_timestamp_ms=opened, oi_safe_available_ms=opened + BAR_MS,
    ) == opened + 3 * BAR_MS


@pytest.mark.parametrize("changes", [
    {"oi_timestamp_ms": 101 * BAR_MS},
    {"candle_safe_available_ms": 101 * BAR_MS - 1},
    {"oi_safe_available_ms": 101 * BAR_MS - 1},
    {"candle_open_ms": 100 * BAR_MS + 1, "oi_timestamp_ms": 100 * BAR_MS + 1},
])
def test_rejects_misalignment_or_premature_receipts(changes: dict[str, int]) -> None:
    inputs = {
        "candle_open_ms": 100 * BAR_MS,
        "candle_safe_available_ms": 101 * BAR_MS,
        "oi_timestamp_ms": 100 * BAR_MS,
        "oi_safe_available_ms": 101 * BAR_MS,
    }
    inputs.update(changes)
    with pytest.raises(ValueError):
        first_eligible_open_ms(**inputs)
