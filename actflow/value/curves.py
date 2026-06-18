"""Value curves — map metrics to normalized value scores (0.0–1.0).

Each curve answers: "Given this metric value, what fraction of the full value
is delivered?"
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod


class ValueCurve(ABC):
    """Abstract base for value-mapping curves."""

    @abstractmethod
    def evaluate(self, value: float) -> float: ...

    @abstractmethod
    def describe(self) -> str: ...


class Linear(ValueCurve):
    """Linear mapping from [min_good, max_good] to [1.0, 0.0].

    Args:
        min_threshold: Value below which score is 0.0.
        max_perfect: Value above which score is 1.0.
    """

    def __init__(self, min_threshold: float = 0.0, max_perfect: float = 1.0):
        self.min_threshold = min_threshold
        self.max_perfect = max_perfect

    def evaluate(self, value: float) -> float:
        if value <= self.min_threshold:
            return 0.0
        if value >= self.max_perfect:
            return 1.0
        return (value - self.min_threshold) / (self.max_perfect - self.min_threshold)

    def describe(self) -> str:
        return f"Linear(min={self.min_threshold}, max={self.max_perfect})"


class ExponentialDecay(ValueCurve):
    """Exponential decay: perfect at *perfect* ms, half value at *half_life* ms.

    Args:
        perfect: Value at which score = 1.0 (e.g. 60 seconds).
        half_life: Value at which score = 0.5 (e.g. 300 seconds).
    """

    def __init__(self, perfect: float, half_life: float):
        self.perfect = perfect
        # compute decay constant: score(t) = 2^(-lambda * (t - perfect))
        # at t = half_life, score = 0.5 => lambda = 1/(half_life - perfect)
        if half_life <= perfect:
            raise ValueError("half_life must be > perfect for exponential decay")
        self.lmbda = math.log(2) / (half_life - perfect)

    def evaluate(self, value: float) -> float:
        if value <= self.perfect:
            return 1.0
        return math.exp(-self.lmbda * (value - self.perfect))

    def describe(self) -> str:
        return f"ExponentialDecay(perfect={self.perfect}, half_life={math.log(2)/self.lmbda + self.perfect:.0f})"


class Sigmoid(ValueCurve):
    """Sigmoid (logistic) curve for binary-ish outcomes.

    Args:
        midpoint: Value where score = 0.5.
        steepness: Controls how sharp the transition is (higher = steeper).
    """

    def __init__(self, midpoint: float = 0.5, steepness: float = 10.0):
        self.midpoint = midpoint
        self.steepness = steepness

    def evaluate(self, value: float) -> float:
        return 1.0 / (1.0 + math.exp(-self.steepness * (value - self.midpoint)))

    def describe(self) -> str:
        return f"Sigmoid(midpoint={self.midpoint}, steepness={self.steepness})"
