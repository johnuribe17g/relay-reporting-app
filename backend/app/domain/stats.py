"""Robust statistics for weekly counts. Pure functions, no I/O."""

import math
from collections.abc import Sequence

MAD_SCALE = 1.4826  # makes MAD comparable to a standard deviation for normal data


def median(values: Sequence[float]) -> float:
    """Median; for an even count, the mean of the two middle values."""
    if not values:
        raise ValueError("median of an empty sequence")
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2 == 1:
        return float(ordered[mid])
    return (ordered[mid - 1] + ordered[mid]) / 2


def mad(values: Sequence[float]) -> float:
    """Raw median absolute deviation (no 1.4826 scaling)."""
    center = median(values)
    return median([abs(v - center) for v in values])


def spread(values: Sequence[float]) -> float:
    """`max(1.4826·MAD, √median, 1)`: the √median Poisson floor covers MAD ≈ 0 (PLAN §2)."""
    return max(MAD_SCALE * mad(values), math.sqrt(median(values)), 1.0)
