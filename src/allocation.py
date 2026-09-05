# Copyright Ohyyp 2026
# SPDX-License-Identifier: GPL-3.0-or-later

import sys
from collections.abc import Mapping, Sequence
from decimal import ROUND_DOWN, Decimal

from configuration import HUNDRED, ZERO, AccountConfig, Config
from market_data import MarketQuote

SHARE_QUANTUM = Decimal("0.00001")


def truncate_shares(shares: Decimal) -> Decimal:
    return shares.quantize(SHARE_QUANTUM, rounding=ROUND_DOWN)


class AccountState:
    __slots__ = (
        "base_money",
        "broker",
        "free_cash",
        "holdings",
        "leverage_limit",
        "leverage_rate",
        "name",
    )

    def __init__(
        self,
        name: str,
        broker: str,
        config: AccountConfig,
        market_data: Mapping[str, MarketQuote],
    ) -> None:
        self.name = name
        self.broker = broker
        self.leverage_rate = config.leverage_rate
        self.holdings = {ticker: truncate_shares(shares) for ticker, shares in config.fixed_assets.items()}

        fixed_value = sum(
            shares * market_data[ticker].price for ticker, shares in self.holdings.items() if shares > ZERO
        )
        configured_money = config.money if config.money is not None else fixed_value
        self.base_money = max(configured_money, fixed_value)
        self.leverage_limit = ZERO
        self.free_cash = self.base_money - fixed_value

        if configured_money < fixed_value:
            print(
                f"Warning: {broker} {name} fixed holdings exceed configured money; "
                "using their current value as base equity.",
                file=sys.stderr,
            )


def apply_portfolio_leverage(account_states: Sequence[AccountState]) -> None:
    leveraged_account = next((state for state in account_states if state.leverage_rate > 0), None)
    if leveraged_account is None:
        return
    portfolio_base_money = sum((state.base_money for state in account_states), ZERO)
    leverage_ratio = Decimal(leveraged_account.leverage_rate) / HUNDRED
    leveraged_account.leverage_limit = portfolio_base_money * leverage_ratio


def calculate_satellite_targets(config: Config, total_money: Decimal) -> dict[str, Decimal]:
    return {ticker: total_money * percentage / HUNDRED for ticker, percentage in config.satellite.items()}


def compute_holding_values(
    account_states: Sequence[AccountState],
    market_data: Mapping[str, MarketQuote],
) -> dict[str, Decimal]:
    holding_values = dict.fromkeys(market_data, ZERO)
    for state in account_states:
        for ticker, shares in state.holdings.items():
            if shares > ZERO:
                holding_values[ticker] += shares * market_data[ticker].price
    return holding_values


def compute_target_holding_values(
    targets: Mapping[str, object],
    holding_values: Mapping[str, Decimal],
    substitutions: Mapping[str, str],
) -> dict[str, Decimal]:
    values = {ticker: holding_values.get(ticker, ZERO) for ticker in targets}
    for substitute, target in substitutions.items():
        if target in values:
            values[target] += holding_values.get(substitute, ZERO)
    return values


def determine_buy_shares(
    target_values: Mapping[str, Decimal],
    holding_values: Mapping[str, Decimal],
    market_data: Mapping[str, MarketQuote],
) -> dict[str, int]:
    purchases: dict[str, int] = {}
    for ticker, target_value in target_values.items():
        deficit = target_value - holding_values.get(ticker, ZERO)
        if deficit <= ZERO:
            continue
        shares = int(deficit / market_data[ticker].price)
        if shares > 0:
            purchases[ticker] = shares
    return purchases


def distribute_shares(
    purchases: Mapping[str, int],
    account_states: Sequence[AccountState],
    market_data: Mapping[str, MarketQuote],
    substitutions: Mapping[str, str] | None = None,
) -> None:
    substitutions = substitutions or {}
    for ticker in purchases:
        price = market_data[ticker].price
        remaining = purchases[ticker]
        equivalent_tickers = {ticker, *(substitute for substitute, target in substitutions.items() if target == ticker)}
        holders = [
            state
            for state in account_states
            if any(state.holdings.get(equivalent, ZERO) > ZERO for equivalent in equivalent_tickers)
        ]
        non_holders = [state for state in account_states if state not in holders]

        for state in (*holders, *non_holders):
            if remaining <= 0:
                break
            shares = min(remaining, int((state.free_cash + state.leverage_limit) / price))
            if shares <= 0:
                continue
            state.holdings[ticker] = state.holdings.get(ticker, ZERO) + shares
            state.free_cash -= price * shares
            remaining -= shares


def calculate_core_targets(
    account_states: Sequence[AccountState],
    core: Mapping[str, int],
    market_data: Mapping[str, MarketQuote],
    substitutions: Mapping[str, str] | None = None,
) -> tuple[dict[str, Decimal], dict[str, Decimal]]:
    holding_values = compute_holding_values(account_states, market_data)
    target_holding_values = compute_target_holding_values(core, holding_values, substitutions or {})
    remaining_buying_power = sum((state.free_cash + state.leverage_limit for state in account_states), ZERO)
    core_value = remaining_buying_power + sum(target_holding_values.values(), ZERO)
    targets = {ticker: target_holding_values[ticker] for ticker, percentage in core.items() if percentage == 0}
    active = {ticker: Decimal(percentage) for ticker, percentage in core.items() if percentage > 0}
    remaining_value = core_value - sum(targets.values(), ZERO)
    while active:
        weight_total = sum(active.values(), ZERO)
        provisional: dict[str, Decimal] = {}
        allocated = ZERO
        for index, (ticker, weight) in enumerate(active.items()):
            target = (
                remaining_value - allocated if index == len(active) - 1 else remaining_value * weight / weight_total
            )
            provisional[ticker] = target
            allocated += target
        overweight = [ticker for ticker in active if target_holding_values[ticker] > provisional[ticker]]
        if not overweight:
            targets.update(provisional)
            break
        for ticker in overweight:
            targets[ticker] = target_holding_values[ticker]
            remaining_value -= targets[ticker]
            del active[ticker]

    ordered_targets = {ticker: targets[ticker] for ticker in core}
    final_ticker = next(
        (ticker for ticker in reversed(ordered_targets) if ordered_targets[ticker] > target_holding_values[ticker]),
        None,
    )
    if final_ticker is not None:
        ordered_targets = {ticker: target for ticker, target in ordered_targets.items() if ticker != final_ticker}
        ordered_targets[final_ticker] = core_value - sum(ordered_targets.values(), ZERO)
    return ordered_targets, target_holding_values


def allocate_core(
    account_states: Sequence[AccountState],
    core: Mapping[str, int],
    market_data: Mapping[str, MarketQuote],
    substitutions: Mapping[str, str] | None = None,
) -> None:
    substitutions = substitutions or {}
    target_values, holding_values = calculate_core_targets(account_states, core, market_data, substitutions)
    unordered_purchases = determine_buy_shares(target_values, holding_values, market_data)
    purchases = {ticker: unordered_purchases[ticker] for ticker in core if ticker in unordered_purchases}
    distribute_shares(purchases, account_states, market_data, substitutions)
