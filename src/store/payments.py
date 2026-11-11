from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4


class PaymentDeclined(Exception):
    pass


@dataclass
class FakePaymentProcessor:
    """A tiny stand-in for an external payment provider.

    Any non-empty token succeeds except ``tok_fail``, which is intentionally
    available for tests and demos of the failure path.
    """

    def charge(self, amount_cents: int, token: str) -> str:
        if amount_cents <= 0:
            raise ValueError("amount must be positive")
        if not token or token == "tok_fail":
            raise PaymentDeclined("Payment was declined")
        return f"pay_{uuid4().hex[:12]}"
