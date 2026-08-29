# Copyright Ohyyp 2026
# SPDX-License-Identifier: GPL-3.0-or-later

from decimal import Decimal

from allocation import (
    AccountState,
    allocate_core_cash,
    determine_buy_shares,
    distribute_shares,
)
from configuration import AccountConfig
from market_data import MarketQuote


def quote(price: str, quote_type: str = "EQUITY") -> MarketQuote:
    return MarketQuote(price=Decimal(price), quote_type=quote_type)


def test_distribution_concentrates_shares_in_the_richest_account() -> None:
    market = {"TARGET": quote("100")}
    accounts = [
        AccountState(
            "first",
            "broker",
            AccountConfig(money=300),
            market,
        ),
        AccountState(
            "second",
            "broker",
            AccountConfig(money=200),
            market,
        ),
    ]

    purchases = determine_buy_shares({"TARGET": Decimal("300")}, {"TARGET": Decimal("0")}, market)
    distribute_shares(purchases, accounts, market)

    assert accounts[0].holdings == {"TARGET": Decimal("3")}
    assert accounts[1].holdings == {}
    assert accounts[0].free_cash == Decimal("0")
    assert accounts[1].free_cash == Decimal("200")


def test_distribution_prioritizes_an_existing_position() -> None:
    market = {"TARGET": quote("100")}
    accounts = [
        AccountState("rich", "broker", AccountConfig(money=500), market),
        AccountState(
            "holder",
            "broker",
            AccountConfig(money=300, fixed_assets={"TARGET": 1}),
            market,
        ),
    ]

    distribute_shares({"TARGET": 2}, accounts, market)

    assert accounts[0].holdings == {}
    assert accounts[1].holdings == {"TARGET": Decimal("3")}


def test_distribution_uses_toml_order_to_break_ties() -> None:
    market = {"TARGET": quote("100")}
    accounts = [
        AccountState("first", "broker", AccountConfig(money=200), market),
        AccountState("second", "broker", AccountConfig(money=200), market),
    ]

    distribute_shares({"TARGET": 2}, accounts, market)

    assert accounts[0].holdings == {"TARGET": Decimal("2")}
    assert accounts[1].holdings == {}


def test_distribution_orders_assets_by_risk_then_ticker() -> None:
    market = {
        "A_ETF": quote("100", "ETF"),
        "A_STOCK": quote("100"),
        "Z_STOCK": quote("100"),
    }
    accounts = [
        AccountState("first", "broker", AccountConfig(money=100), market),
        AccountState("second", "broker", AccountConfig(money=100), market),
        AccountState("third", "broker", AccountConfig(money=100), market),
    ]

    distribute_shares(
        {"A_ETF": 1, "Z_STOCK": 1, "A_STOCK": 1},
        accounts,
        market,
    )

    assert accounts[0].holdings == {"A_STOCK": Decimal("1")}
    assert accounts[1].holdings == {"Z_STOCK": Decimal("1")}
    assert accounts[2].holdings == {"A_ETF": Decimal("1")}


def test_core_cash_uses_global_weights_and_existing_positions() -> None:
    market = {
        "CORE_A": quote("100", "ETF"),
        "CORE_B": quote("100", "ETF"),
    }
    accounts = [
        AccountState(
            "a_holder",
            "broker",
            AccountConfig(money=301, fixed_assets={"CORE_A": 1}),
            market,
        ),
        AccountState(
            "b_holder",
            "broker",
            AccountConfig(money=401, fixed_assets={"CORE_B": 1}),
            market,
        ),
        AccountState("unassigned", "broker", AccountConfig(money=498), market),
    ]

    allocate_core_cash(
        accounts,
        {
            "CORE_A": 40,
            "CORE_B": 60,
            "ZERO_CORE": 0,
        },
        market,
    )

    assert accounts[0].holdings == {"CORE_A": Decimal("3.01")}
    assert accounts[1].holdings == {"CORE_B": Decimal("4.01")}
    assert accounts[2].holdings == {
        "CORE_A": Decimal("1.99"),
        "CORE_B": Decimal("2.99"),
    }
    assert all(account.free_cash == Decimal("0") for account in accounts)


def test_core_assets_use_alphabetical_order_and_account_priority() -> None:
    market = {
        "A_CORE": quote("100", "ETF"),
        "Z_CORE": quote("100", "ETF"),
    }
    accounts = [
        AccountState("first", "broker", AccountConfig(money=500), market),
        AccountState("second", "broker", AccountConfig(money=500), market),
    ]

    allocate_core_cash(
        accounts,
        {"Z_CORE": 60, "A_CORE": 40},
        market,
    )

    assert accounts[0].holdings == {
        "A_CORE": Decimal("4"),
        "Z_CORE": Decimal("1"),
    }
    assert accounts[1].holdings == {"Z_CORE": Decimal("5")}


def test_fixed_and_core_shares_truncate_to_five_decimals() -> None:
    fixed_market = {"FIXED": quote("1")}
    fixed_account = AccountState(
        "fixed",
        "broker",
        AccountConfig(money=2, fixed_assets={"FIXED": Decimal("1.234567")}),
        fixed_market,
    )
    core_market = {"CORE": quote("3", "ETF")}
    core_account = AccountState(
        "core",
        "broker",
        AccountConfig(money=1),
        core_market,
    )

    allocate_core_cash(
        [core_account],
        {"CORE": 100},
        core_market,
    )

    assert fixed_account.holdings == {"FIXED": Decimal("1.23456")}
    assert core_account.holdings == {"CORE": Decimal("0.33333")}
    assert core_account.free_cash == Decimal("0.00001")


def test_leverage_rate_is_an_integer_percentage() -> None:
    account = AccountState(
        "account",
        "broker",
        AccountConfig(money=100, leverage_rate=3),
        {},
    )

    assert account.money == Decimal("103")
    assert account.free_cash == Decimal("103")
