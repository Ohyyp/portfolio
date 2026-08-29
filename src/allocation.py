# Copyright Ohyyp 2026
# SPDX-License-Identifier: GPL-3.0-or-later

import heapq
import sys
from collections.abc import Mapping, Sequence
from decimal import ROUND_DOWN, Decimal

from configuration import HUNDRED, ONE, ZERO, AccountConfig, Config
from market_data import MarketQuote

SHARE_QUANTUM = Decimal("0.00001")


def truncate_shares(shares: Decimal) -> Decimal:
    return shares.quantize(SHARE_QUANTUM, rounding=ROUND_DOWN)


class AccountState:
    __slots__ = (
        "base_money",
        "broker",
        "config",
        "free_cash",
        "holdings",
        "money",
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
        self.config = config
        self.holdings = {
            ticker: truncate_shares(shares)
            for ticker, shares in config.fixed_assets.items()
        }

        fixed_value = sum(
            shares * market_data[ticker].price
            for ticker, shares in self.holdings.items()
            if shares > ZERO
        )
        self.base_money = config.money if config.money is not None else fixed_value
        leverage_ratio = Decimal(config.leverage_rate) / HUNDRED
        self.money = self.base_money * (ONE + leverage_ratio)
        self.free_cash = self.money - fixed_value

        if self.free_cash < ZERO:
            print(
                f"Warning: {broker} {name} has negative free cash; using $0.00.",
                file=sys.stderr,
            )
            self.free_cash = ZERO


def calculate_target_values(config: Config, total_money: Decimal) -> dict[str, Decimal]:
    return {
        ticker: total_money * percentage / HUNDRED
        for ticker, percentage in config.satellite.items()
    }


def compute_fixed_values(
    account_states: Sequence[AccountState],
    market_data: Mapping[str, MarketQuote],
) -> dict[str, Decimal]:
    fixed_values = dict.fromkeys(market_data, ZERO)
    for state in account_states:
        for ticker, configured_shares in state.config.fixed_assets.items():
            shares = truncate_shares(configured_shares)
            if shares > ZERO:
                fixed_values[ticker] += shares * market_data[ticker].price
    return fixed_values


def determine_buy_shares(
    target_values: Mapping[str, Decimal],
    fixed_values: Mapping[str, Decimal],
    market_data: Mapping[str, MarketQuote],
) -> dict[str, int]:
    purchases: dict[str, int] = {}
    for ticker, target_value in target_values.items():
        deficit = target_value - fixed_values.get(ticker, ZERO)
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
) -> None:
    assets = sorted(
        purchases,
        key=lambda ticker: (market_data[ticker].is_etf, ticker),
    )
    for ticker in assets:
        price = market_data[ticker].price
        remaining = purchases[ticker]
        accounts = [
            (
                state.holdings.get(ticker, ZERO) <= ZERO,
                -state.holdings.get(ticker, ZERO),
                -state.free_cash,
                index,
                state,
            )
            for index, state in enumerate(account_states)
        ]
        heapq.heapify(accounts)

        while remaining > 0 and accounts:
            *_, state = heapq.heappop(accounts)
            shares = min(remaining, int(state.free_cash / price))
            if shares <= 0:
                continue
            state.holdings[ticker] = state.holdings.get(ticker, ZERO) + shares
            state.free_cash -= price * shares
            remaining -= shares


def allocate_core_cash(
    account_states: Sequence[AccountState],
    core: Mapping[str, int],
    market_data: Mapping[str, MarketQuote],
) -> None:
    total_cash = sum((state.free_cash for state in account_states), ZERO)
    assets = sorted(ticker for ticker, percentage in core.items() if percentage > 0)
    for ticker in assets:
        remaining_value = total_cash * core[ticker] / HUNDRED
        if remaining_value <= ZERO:
            continue
        price = market_data[ticker].price
        accounts = [
            (
                state.holdings.get(ticker, ZERO) <= ZERO,
                -state.holdings.get(ticker, ZERO),
                -state.free_cash,
                index,
                state,
            )
            for index, state in enumerate(account_states)
            if state.free_cash > ZERO
        ]
        heapq.heapify(accounts)

        while remaining_value > ZERO and accounts:
            *_, state = heapq.heappop(accounts)
            value = min(remaining_value, state.free_cash)
            shares = truncate_shares(value / price)
            if shares <= ZERO:
                continue
            allocated_value = shares * price
            state.holdings[ticker] = state.holdings.get(ticker, ZERO) + shares
            state.free_cash -= allocated_value
            remaining_value -= allocated_value
