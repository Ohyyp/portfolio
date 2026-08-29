# Copyright Ohyyp 2026
# SPDX-License-Identifier: GPL-3.0-or-later

from decimal import Decimal

import pytest
from pydantic import ValidationError

from configuration import AccountConfig, Config, get_all_tickers


def test_config_normalizes_tickers_and_collects_required_symbols() -> None:
    config = Config(
        core={" core ": 100, "zero_core": 0},
        broker={
            "test_broker": {
                "test_account": AccountConfig(
                    money=Decimal("1000"),
                    fixed_assets={" held ": Decimal("2"), "zero_held": Decimal("0")},
                )
            }
        },
        satellite={" target ": 75, "zero_target": 0},
    )

    assert config.core == {
        "CORE": 100,
        "ZERO_CORE": 0,
    }
    assert config.satellite == {
        "TARGET": 75,
        "ZERO_TARGET": 0,
    }
    assert get_all_tickers(config) == {"TARGET", "HELD", "CORE"}


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"satellite": {"A": 60, "B": 41}}, "cannot exceed 100%"),
        ({"core": {"A": 60, "B": 39}}, "must equal 100%"),
        ({"core": {"A": 100}}, "must be distinct"),
        ({"core": {"CORE": 100.0}}, "valid integer"),
        ({"satellite": {"A": 50.0}}, "valid integer"),
        ({"allocation": {"A": 50}}, "Extra inputs are not permitted"),
        ({"asset_types": {}}, "Extra inputs are not permitted"),
        (
            {
                "broker": {
                    "test_broker": {
                        "test_account": {
                            "free_money_to": "CORE",
                            "money": 100,
                        }
                    }
                }
            },
            "Extra inputs are not permitted",
        ),
        ({"broker": {"bad broker": {}}}, "must be snake_case"),
    ],
)
def test_config_rejects_invalid_input(overrides, message: str) -> None:
    data = {
        "core": {"CORE": 100},
        "broker": {
            "test_broker": {
                "test_account": {
                    "money": 100,
                }
            }
        },
        "satellite": {"A": 50},
    }
    data.update(overrides)

    with pytest.raises(ValidationError, match=message):
        Config.model_validate(data)


@pytest.mark.parametrize("leverage_rate", [0.01, 1.0, 100])
def test_config_requires_integer_leverage_percent_below_100(leverage_rate) -> None:
    with pytest.raises(ValidationError):
        AccountConfig(money=100, leverage_rate=leverage_rate)
