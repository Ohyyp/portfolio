# Copyright Ohyyp 2026
# SPDX-License-Identifier: GPL-3.0-or-later

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from allocation import (
    AccountState,
    allocate_core_cash,
    calculate_target_values,
    compute_fixed_values,
    determine_buy_shares,
    distribute_shares,
)
from configuration import ZERO, Config, ConfigError, get_all_tickers, load_config
from market_data import MarketDataError, fetch_market_data
from reporting import print_report


def run(config: Config) -> None:
    market_data = fetch_market_data(get_all_tickers(config))
    invalid_core = sorted(
        ticker
        for ticker, percentage in config.core.items()
        if percentage > 0 and not market_data[ticker].is_etf
    )
    if invalid_core:
        symbols = ", ".join(invalid_core)
        raise ConfigError(f"Core assets must be ETFs: {symbols}")
    account_states = [
        AccountState(account_name, broker_name, account, market_data)
        for broker_name, accounts in config.broker.items()
        for account_name, account in accounts.items()
    ]
    total_money = sum((state.money for state in account_states), ZERO)
    if total_money <= ZERO:
        raise ConfigError("Total portfolio money must be greater than zero")

    targets = calculate_target_values(config, total_money)
    fixed_values = compute_fixed_values(account_states, market_data)
    purchases = determine_buy_shares(targets, fixed_values, market_data)
    distribute_shares(purchases, account_states, market_data)
    allocate_core_cash(account_states, config.core, market_data)
    print_report(account_states, market_data)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="portfolio-allocator",
        description="Calculate a target allocation across brokerage accounts.",
    )
    parser.add_argument("config", type=Path, help="path to a TOML configuration file")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        run(load_config(args.config))
    except (ConfigError, MarketDataError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
