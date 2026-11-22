"""Focused Strategy contract tests, including a future fulfillment algorithm."""

from dataclasses import dataclass

import pytest

from store.fulfillment import (
    FlatRateDeliveryStrategy,
    FulfillmentAddressError,
    FulfillmentOption,
    StorePickupStrategy,
    get_fulfillment_option,
)


def test_delivery_strategy_requires_address_and_charges_flat_rate():
    option = get_fulfillment_option("express_shipping")

    assert isinstance(option.strategy, FlatRateDeliveryStrategy)
    assert option.calculate_fee(10000) == 19900
    assert option.normalize_address("  Street 1  ") == "Street 1"

    with pytest.raises(FulfillmentAddressError):
        option.normalize_address(" ")


def test_pickup_strategy_zeroes_shipping_and_address():
    option = get_fulfillment_option("store_pickup")

    assert isinstance(option.strategy, StorePickupStrategy)
    assert option.calculate_fee(10000) == 0
    assert option.normalize_address("unexpected address") == ""


def test_new_strategy_can_be_composed_without_checkout_conditions():
    @dataclass(frozen=True)
    class PercentageDelivery:
        requires_address: bool = True

        def calculate_fee(self, subtotal_cents: int) -> int:
            return subtotal_cents // 10

        def normalize_address(self, address: str) -> str:
            if not address.strip():
                raise FulfillmentAddressError("Address required")
            return address.strip()

    option = FulfillmentOption(
        "future_percent_delivery",
        "Future Method",
        PercentageDelivery(),
    )

    assert option.calculate_fee(15000) == 1500
    assert option.normalize_address(" Street ") == "Street"
