from decimal import Decimal

from pydantic import Field

from tradev2.domain.base import FrozenModel


class ReturnObservation(FrozenModel):
    time_ms: int = Field(ge=0)
    value: Decimal


def rolling_correlation_bucket(candidate: tuple[ReturnObservation, ...],
                               peers: dict[str, tuple[ReturnObservation, ...]], *,
                               as_of_ms: int, window: int = 30,
                               threshold: Decimal = Decimal("0.7")) -> frozenset[str]:
    """Unknown/constant/insufficient series conservatively share the risk bucket.

    Input returns must have matching timestamps. Future observations cannot inform
    correlation. Absolute correlation includes opposite-direction dependencies.
    """
    if window < 3 or not Decimal(0) <= threshold <= Decimal(1):
        raise ValueError("invalid correlation window or threshold")

    def eligible(rows: tuple[ReturnObservation, ...]) -> dict[int, Decimal]:
        result: dict[int, Decimal] = {}
        for row in rows:
            if row.time_ms > as_of_ms:
                continue
            if row.time_ms in result:
                raise ValueError("duplicate return timestamp")
            result[row.time_ms] = row.value
        return result

    base = eligible(candidate)
    bucket: set[str] = set()
    for symbol, observations in peers.items():
        peer = eligible(observations)
        times = sorted(base.keys() & peer.keys())[-window:]
        if len(times) < window:
            bucket.add(symbol)
            continue
        xs, ys = [base[t] for t in times], [peer[t] for t in times]
        mx, my = sum(xs, Decimal(0)) / window, sum(ys, Decimal(0)) / window
        covariance = sum(((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True)), Decimal(0))
        vx = sum(((x - mx) ** 2 for x in xs), Decimal(0))
        vy = sum(((y - my) ** 2 for y in ys), Decimal(0))
        denominator = (vx * vy).sqrt()
        if denominator == 0 or abs(covariance / denominator) >= threshold:
            bucket.add(symbol)
    return frozenset(bucket)
