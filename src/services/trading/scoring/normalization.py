from __future__ import annotations


def clamp(value: float) -> float:
    try:
        number = float(value)
        if number != number:
            return 0.0
        return max(0.0, min(1.0, number))
    except Exception:
        return 0.0


def normalize_weights(weights: dict[str, float]) -> dict[str, float]:
    cleaned = {key: max(0.0, float(value or 0.0)) for key, value in weights.items()}
    total = sum(cleaned.values())
    if total <= 0:
        even = 1.0 / max(len(cleaned), 1)
        return {key: even for key in cleaned}
    return {key: value / total for key, value in cleaned.items()}
