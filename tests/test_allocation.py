# Copyright Ohyyp 2026
# SPDX-License-Identifier: GPL-3.0-or-later

from decimal import Decimal

from allocation import (
    AccountState,
    allocate_core,
    apply_portfolio_leverage,
    calculate_core_targets,
    determine_buy_shares,
    distribute_shares,
)
from configuration import AccountConfig
from market_data import MarketQuote


def quote(price: str, quote_type: str = "EQUITY") -> MarketQuote:
    return MarketQuote(price=Decimal(price), quote_type=quote_type)


def test_distribution_fills_accounts_in_config_order() -> None:
    market = {"TARGET": quote("100")}
    accounts = [
        AccountState(
            "first",
            "broker",
            AccountConfig(money=200),
            market,
        ),
        AccountState(
            "second",
            "broker",
            AccountConfig(money=300),
            market,
        ),
    ]

    purchases = determine_buy_shares({"TARGET": Decimal("300")}, {"TARGET": Decimal("0")}, market)
    distribute_shares(purchases, accounts, market)

    assert accounts[0].holdings == {"TARGET": Decimal("2")}
    assert accounts[1].holdings == {"TARGET": Decimal("1")}
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


def test_distribution_preserves_config_order_between_existing_holders() -> None:
    market = {"TARGET": quote("100")}
    accounts = [
        AccountState("first", "broker", AccountConfig(money=300, fixed_assets={"TARGET": 1}), market),
        AccountState("second", "broker", AccountConfig(money=1200, fixed_assets={"TARGET": 10}), market),
    ]

    distribute_shares({"TARGET": 2}, accounts, market)

    assert accounts[0].holdings == {"TARGET": Decimal("3")}
    assert accounts[1].holdings == {"TARGET": Decimal("10")}


def test_distribution_treats_a_substitute_holder_as_an_existing_holder() -> None:
    market = {
        "NEW": quote("100", "ETF"),
        "OLD": quote("100", "ETF"),
    }
    accounts = [
        AccountState("non_holder", "broker", AccountConfig(money=100), market),
        AccountState("substitute_holder", "broker", AccountConfig(money=200, fixed_assets={"OLD": 1}), market),
    ]

    distribute_shares({"NEW": 1}, accounts, market, {"OLD": "NEW"})

    assert accounts[0].holdings == {}
    assert accounts[1].holdings == {"OLD": Decimal("1"), "NEW": Decimal("1")}


def test_distribution_uses_toml_order_to_break_ties() -> None:
    market = {"TARGET": quote("100")}
    accounts = [
        AccountState("first", "broker", AccountConfig(money=200), market),
        AccountState("second", "broker", AccountConfig(money=200), market),
    ]

    distribute_shares({"TARGET": 2}, accounts, market)

    assert accounts[0].holdings == {"TARGET": Decimal("2")}
    assert accounts[1].holdings == {}


def test_distribution_preserves_asset_declaration_order() -> None:
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
        {"Z_STOCK": 1, "A_ETF": 1, "A_STOCK": 1},
        accounts,
        market,
    )

    assert accounts[0].holdings == {"Z_STOCK": Decimal("1")}
    assert accounts[1].holdings == {"A_ETF": Decimal("1")}
    assert accounts[2].holdings == {"A_STOCK": Decimal("1")}


def test_core_targets_include_and_deduct_existing_core_positions() -> None:
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

    allocate_core(
        accounts,
        {
            "CORE_A": 40,
            "CORE_B": 60,
            "ZERO_CORE": 0,
        },
        market,
    )

    assert accounts[0].holdings == {"CORE_A": Decimal("3")}
    assert accounts[1].holdings == {
        "CORE_B": Decimal("3"),
        "CORE_A": Decimal("1"),
    }
    assert accounts[2].holdings == {"CORE_B": Decimal("4")}
    assert [account.free_cash for account in accounts] == [Decimal("1"), Decimal("1"), Decimal("98")]


def test_core_assets_use_declared_order_and_account_priority() -> None:
    market = {
        "A_CORE": quote("100", "ETF"),
        "Z_CORE": quote("100", "ETF"),
    }
    accounts = [
        AccountState("first", "broker", AccountConfig(money=500), market),
        AccountState("second", "broker", AccountConfig(money=500), market),
    ]

    allocate_core(
        accounts,
        {"Z_CORE": 60, "A_CORE": 40},
        market,
    )

    assert accounts[0].holdings == {
        "Z_CORE": Decimal("5"),
    }
    assert accounts[1].holdings == {
        "Z_CORE": Decimal("1"),
        "A_CORE": Decimal("4"),
    }


def test_existing_substitute_counts_toward_core_target_but_new_buys_use_target() -> None:
    market = {
        "NEW": quote("100", "ETF"),
        "OLD": quote("100", "ETF"),
        "OTHER": quote("100", "ETF"),
    }
    account = AccountState(
        "account",
        "broker",
        AccountConfig(money=1000, fixed_assets={"OLD": 4}),
        market,
    )

    allocate_core(
        [account],
        {"NEW": 50, "OTHER": 50},
        market,
        {"OLD": "NEW"},
    )

    assert account.holdings == {
        "OLD": Decimal("4"),
        "NEW": Decimal("1"),
        "OTHER": Decimal("5"),
    }
    assert account.free_cash == Decimal("0")


def test_core_surplus_is_frozen_and_cash_is_redistributed() -> None:
    market = {
        "FIRST": quote("100", "ETF"),
        "SECOND": quote("100", "ETF"),
        "SURPLUS": quote("100", "ETF"),
    }
    account = AccountState(
        "account",
        "broker",
        AccountConfig(money=1000, fixed_assets={"SURPLUS": 8}),
        market,
    )

    allocate_core(
        [account],
        {"FIRST": 40, "SECOND": 40, "SURPLUS": 20},
        market,
    )

    assert account.holdings == {
        "SURPLUS": Decimal("8"),
        "FIRST": Decimal("1"),
        "SECOND": Decimal("1"),
    }
    assert account.free_cash == Decimal("0")


def test_core_redistribution_repeats_when_another_asset_becomes_overweight() -> None:
    market = {ticker: quote("1", "ETF") for ticker in ("FIRST", "SECOND", "THIRD", "FOURTH")}
    account = AccountState(
        "account",
        "broker",
        AccountConfig(money=1000, fixed_assets={"FIRST": 600, "SECOND": 250}),
        market,
    )

    allocate_core(
        [account],
        {"FIRST": 40, "SECOND": 30, "THIRD": 20, "FOURTH": 10},
        market,
    )

    assert account.holdings == {
        "FIRST": Decimal("600"),
        "SECOND": Decimal("250"),
        "THIRD": Decimal("100"),
        "FOURTH": Decimal("50"),
    }
    assert account.free_cash == Decimal("0")


def test_core_redistribution_preserves_the_exact_pool_value() -> None:
    market = {ticker: quote("1", "ETF") for ticker in ("OVERWEIGHT", "SECOND", "THIRD")}
    account = AccountState(
        "account",
        "broker",
        AccountConfig(money=1000, fixed_assets={"OVERWEIGHT": 500}),
        market,
    )

    targets, holdings = calculate_core_targets(
        [account],
        {"OVERWEIGHT": 40, "SECOND": 35, "THIRD": 25},
        market,
    )

    assert targets["OVERWEIGHT"] == holdings["OVERWEIGHT"]
    assert sum(targets.values(), Decimal("0")) == Decimal("1000.00000")
    assert all(targets[ticker] >= holdings[ticker] for ticker in targets)


def test_core_redistribution_corrects_decimal_precision_residue() -> None:
    core = {"T0": 19, "T1": 5, "T2": 14, "T3": 19, "T4": 5, "T5": 1, "T6": 12, "T7": 25}
    fixed_assets = {"T0": 1768, "T1": 509, "T2": 929, "T3": 225, "T4": 254, "T5": 1118, "T6": 363, "T7": 936}
    market = {ticker: quote("1", "ETF") for ticker in core}
    account = AccountState(
        "account",
        "broker",
        AccountConfig(money=7449, fixed_assets=fixed_assets),
        market,
    )

    targets, holdings = calculate_core_targets([account], core, market)

    assert sum(targets.values(), Decimal("0")) == Decimal("7449.00000")
    assert all(targets[ticker] >= holdings[ticker] for ticker in targets)


def test_fixed_shares_truncate_to_five_decimals_and_new_core_shares_are_whole() -> None:
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
        AccountConfig(money=10),
        core_market,
    )

    allocate_core(
        [core_account],
        {"CORE": 100},
        core_market,
    )

    assert fixed_account.holdings == {"FIXED": Decimal("1.23456")}
    assert core_account.holdings == {"CORE": Decimal("3")}
    assert core_account.free_cash == Decimal("1")


def test_leverage_rate_uses_total_portfolio_equity_and_stays_in_its_account() -> None:
    market = {"FIXED": quote("200")}
    accounts = [
        AccountState(
            "leveraged",
            "broker",
            AccountConfig(money=100, leverage_rate=10),
            market,
        ),
        AccountState(
            "fixed_only",
            "broker",
            AccountConfig(fixed_assets={"FIXED": Decimal("1.5")}),
            market,
        ),
    ]

    apply_portfolio_leverage(accounts)

    assert accounts[0].leverage_limit == Decimal("40.0")
    assert accounts[0].free_cash == Decimal("100")
    assert accounts[1].leverage_limit == Decimal("0")
    assert accounts[1].free_cash == Decimal("0.0")


def test_leverage_is_buying_power_and_purchases_create_negative_cash() -> None:
    market = {
        "FIXED": quote("100"),
        "TARGET": quote("6"),
    }
    account = AccountState(
        "leveraged",
        "broker",
        AccountConfig(money=100, fixed_assets={"FIXED": 1}, leverage_rate=10),
        market,
    )
    apply_portfolio_leverage([account])

    distribute_shares({"TARGET": 2}, [account], market)

    assert account.holdings == {"FIXED": Decimal("1"), "TARGET": Decimal("1")}
    assert account.leverage_limit == Decimal("10.0")
    assert account.free_cash == Decimal("-6.00000")


def test_fixed_holdings_above_configured_money_use_current_value(capsys) -> None:
    account = AccountState(
        "account",
        "broker",
        AccountConfig(money=150, fixed_assets={"FIXED": 2}),
        {"FIXED": quote("100")},
    )

    assert account.base_money == Decimal("200.00000")
    assert account.free_cash == Decimal("0.00000")
    assert "fixed holdings exceed configured money" in capsys.readouterr().err
