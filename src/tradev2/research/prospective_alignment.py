"""Point-in-time availability for prospective 15-minute candle/OI features."""

from tradev2.research.datasets import BAR_MS


def first_eligible_open_ms(
    *, candle_open_ms: int, candle_safe_available_ms: int,
    oi_timestamp_ms: int, oi_safe_available_ms: int,
) -> int:
    """Return the first bar open strictly after both feature receipts and candle close.

    This is an eligibility bound, not evidence of an executable fill at that price.
    A consumer must also have that future bar and model its costs/latency.
    """
    if candle_open_ms < 0 or candle_open_ms % BAR_MS:
        raise ValueError("candle open must be a nonnegative 15-minute boundary")
    if oi_timestamp_ms != candle_open_ms:
        raise ValueError("OI and candle exchange timestamps must match exactly")
    if candle_safe_available_ms < candle_open_ms + BAR_MS:
        raise ValueError("candle availability precedes its close")
    if oi_safe_available_ms < oi_timestamp_ms + BAR_MS:
        raise ValueError("OI availability precedes its interval close")
    known_after_ms = max(
        candle_open_ms + BAR_MS, candle_safe_available_ms, oi_safe_available_ms,
    )
    return (known_after_ms // BAR_MS + 1) * BAR_MS
