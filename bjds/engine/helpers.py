"""Small builders shared by the engine tests."""


def reading(stage, hands=(), dealer=None, **extra):
    """hands: (hand_id, seat, bubble) tuples; dealer: bubble text."""
    return {"stage": stage,
            "hands": [{"hand_id": h, "seat": s, "bubble": b} for h, s, b in hands],
            "dealer": {"bubble": dealer} if dealer else None, **extra}
