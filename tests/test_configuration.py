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
                    blocked_assets=[" target ", "vug"],
                )
            }
        },
        satellite={" target ": 75, "zero_target": 0},
        substitutions={" old_core ": " core "},
    )

    assert config.core == {
        "CORE": 100,
        "ZERO_CORE": 0,
    }
    assert config.satellite == {
        "TARGET": 75,
        "ZERO_TARGET": 0,
    }
    assert list(config.core) == ["CORE", "ZERO_CORE"]
    assert list(config.satellite) == ["TARGET", "ZERO_TARGET"]
    assert config.substitutions == {"OLD_CORE": "CORE"}
    assert config.broker["test_broker"]["test_account"].blocked_assets == ["TARGET", "VUG"]
    assert get_all_tickers(config) == {"TARGET", "HELD", "CORE"}


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"satellite": {"A": 60, "B": 41}}, "cannot exceed 100%"),
        ({"core": {"A": 60, "B": 39}}, "must equal 100%"),
        ({"core": {"A": 100}}, "must be distinct"),
        ({"core": {"CORE": 100.0}}, "valid integer"),
        ({"satellite": {"A": 50.0}}, "valid integer"),
        ({"substitutions": {"OLD": "MISSING"}}, "must be configured allocation tickers"),
        ({"substitutions": {"CORE": "CORE"}}, "cannot also be allocation targets"),
        ({"substitutions": {" old ": "CORE", "OLD": "CORE"}}, "duplicate ticker"),
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


@pytest.mark.parametrize(
    "data",
    [
        {"money": Decimal("Infinity")},
        {"fixed_assets": {"ASSET": Decimal("Infinity")}},
        {"leverage_amount": Decimal("Infinity")},
    ],
)
def test_account_money_and_shares_must_be_finite(data) -> None:
    with pytest.raises(ValidationError):
        AccountConfig.model_validate(data)


def test_config_allows_leverage_in_only_one_account() -> None:
    with pytest.raises(ValidationError, match="at most one account"):
        Config(
            core={"CORE": 100},
            broker={
                "test_broker": {
                    "first": {"money": 100, "leverage_rate": 1},
                    "second": {"money": 100, "leverage_rate": 2},
                }
            },
            satellite={"TARGET": 50},
        )


def test_account_requires_one_leverage_unit_and_unique_blocked_assets() -> None:
    with pytest.raises(ValidationError, match="mutually exclusive"):
        AccountConfig(money=100, leverage_rate=1, leverage_amount=500)

    with pytest.raises(ValidationError, match="duplicate tickers"):
        AccountConfig(money=100, blocked_assets=["vug", " VUG "])


def test_config_counts_fixed_amount_as_the_one_leveraged_account() -> None:
    with pytest.raises(ValidationError, match="at most one account"):
        Config(
            core={"CORE": 100},
            broker={
                "test_broker": {
                    "first": {"money": 100, "leverage_amount": 500},
                    "second": {"money": 100, "leverage_rate": 2},
                }
            },
            satellite={"TARGET": 50},
        )


@pytest.mark.parametrize("data", [{"leverage_mode": "minimum"}, {"leverage_mode": "min"}])
def test_config_rejects_invalid_or_unfunded_leverage_mode(data) -> None:
    with pytest.raises(ValidationError):
        AccountConfig.model_validate(data)


def test_leverage_modes_support_both_units_and_default_to_max() -> None:
    assert AccountConfig(leverage_amount=10).leverage_mode == "max"
    assert AccountConfig(leverage_amount=10, leverage_mode="min").leverage_amount == 10
    assert AccountConfig(leverage_rate=10, leverage_mode="min").leverage_rate == 10
    assert AccountConfig(leverage_amount=0, leverage_mode="min").leverage_amount == 0
