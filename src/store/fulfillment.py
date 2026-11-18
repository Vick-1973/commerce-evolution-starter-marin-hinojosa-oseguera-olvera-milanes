"""Small, data-driven fulfillment policy for BANVO.

All current methods differ only in price and whether an address is required.
New options with the same rules can be added by extending OPTIONS; a more
complex pricing algorithm would be a reason to reconsider the design.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FulfillmentOption:
    code: str
    label: str
    fee_cents: int
    requires_address: bool


DEFAULT_FULFILLMENT_CODE = "standard_shipping"

OPTIONS: tuple[FulfillmentOption, ...] = (
    FulfillmentOption("standard_shipping", "Standard Shipping", 9_900, True),
    FulfillmentOption("express_shipping", "Express Shipping", 19_900, True),
    FulfillmentOption("store_pickup", "Store Pickup", 0, False),
)

_OPTIONS_BY_CODE = {option.code: option for option in OPTIONS}


def get_fulfillment_option(code: str) -> FulfillmentOption | None:
    """Return a supported option, or None for a forged/unknown option code."""
    return _OPTIONS_BY_CODE.get(code)
