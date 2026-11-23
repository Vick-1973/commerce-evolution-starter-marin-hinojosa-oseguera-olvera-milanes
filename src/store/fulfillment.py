"""Fulfillment Strategy: swap delivery behavior without teaching checkout each method.

M2 used a table of fees/flags. M3 keeps the small registry for method discovery
and gives each method a replaceable behavior object (Strategy). This matters when
future delivery/pickup options vary beyond a constant price or address flag.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class FulfillmentAddressError(ValueError):
    """The selected method needs shipping information that is not provided."""


class FulfillmentStrategy(Protocol):
    """Stable contract used by the web and marketplace entry points."""

    @property
    def requires_address(self) -> bool: ...

    def calculate_fee(self, subtotal_cents: int) -> int: ...

    def normalize_address(self, address: str) -> str: ...


@dataclass(frozen=True)
class FlatRateDeliveryStrategy:
    """Delivery: fixed fee and required address (standard or express)."""

    amount_cents: int

    @property
    def requires_address(self) -> bool:
        return True

    def calculate_fee(self, subtotal_cents: int) -> int:
        return self.amount_cents

    def normalize_address(self, address: str) -> str:
        address = address.strip()
        if not address:
            raise FulfillmentAddressError(
                "A shipping address is required for delivery."
            )
        return address


@dataclass(frozen=True)
class StorePickupStrategy:
    """Pickup: no delivery fee and no address stored, even when supplied."""

    @property
    def requires_address(self) -> bool:
        return False

    def calculate_fee(self, subtotal_cents: int) -> int:
        return 0

    def normalize_address(self, address: str) -> str:
        return ""


@dataclass(frozen=True)
class FulfillmentOption:
    code: str
    label: str
    strategy: FulfillmentStrategy

    @property
    def requires_address(self) -> bool:
        return self.strategy.requires_address

    @property
    def fee_cents(self) -> int:
        """Compatibility with M2 templates while current fees remain flat."""
        return self.calculate_fee(0)

    def calculate_fee(self, subtotal_cents: int) -> int:
        fee = self.strategy.calculate_fee(subtotal_cents)
        if not isinstance(fee, int) or isinstance(fee, bool) or fee < 0:
            raise ValueError(
                "Fulfillment fee must be a non-negative number of cents"
            )
        return fee

    def normalize_address(self, address: str) -> str:
        return self.strategy.normalize_address(address)


DEFAULT_FULFILLMENT_CODE = "standard_shipping"

OPTIONS: tuple[FulfillmentOption, ...] = (
    FulfillmentOption(
        "standard_shipping",
        "Standard Shipping",
        FlatRateDeliveryStrategy(9_900),
    ),
    FulfillmentOption(
        "express_shipping",
        "Express Shipping",
        FlatRateDeliveryStrategy(19_900),
    ),
    FulfillmentOption(
        "store_pickup",
        "Store Pickup",
        StorePickupStrategy(),
    ),
)

_OPTIONS_BY_CODE = {option.code: option for option in OPTIONS}


def get_fulfillment_option(code: str) -> FulfillmentOption | None:
    return _OPTIONS_BY_CODE.get(code)
