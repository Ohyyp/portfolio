# Copyright Ohyyp 2026
# SPDX-License-Identifier: GPL-3.0-or-later

import argparse
import sys
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

from allocation import (
    AccountState,
    allocate_core,
    apply_portfolio_leverage,
    calculate_satellite_targets,
    compute_holding_values,
    compute_target_holding_values,
    determine_buy_shares,
    distribute_shares,
)
from configuration import ZERO, Config, ConfigError, get_all_tickers, load_config
from market_data import MarketDataError, fetch_market_data
from reporting import print_report


def run(config: Config, *, shareable: bool = False) -> None:
    market_data = fetch_market_data(get_all_tickers(config))
    configured_etfs = dict.fromkeys((*config.core, *config.substitutions, *config.substitutions.values()))
    type_mismatches = [ticker for ticker in configured_etfs if ticker in market_data and not market_data[ticker].is_etf]
    if type_mismatches:
        symbols = ", ".join(type_mismatches)
        print(
            f"Warning: Yahoo did not classify configured ETF assets as ETFs: {symbols}; treating them as ETFs.",
            file=sys.stderr,
        )
        for ticker in type_mismatches:
            market_data[ticker] = replace(market_data[ticker], quote_type="ETF", market_cap=None, year_change=None)
    account_states = [
        AccountState(account_name, broker_name, account, market_data)
        for broker_name, accounts in config.broker.items()
        for account_name, account in accounts.items()
    ]
    apply_portfolio_leverage(account_states)
    total_money = sum((state.base_money + state.leverage_limit for state in account_states), ZERO)
    if total_money <= ZERO:
        raise ConfigError("Total portfolio money must be greater than zero")

    targets = calculate_satellite_targets(config, total_money)
    holding_values = compute_holding_values(account_states, market_data)
    target_holding_values = compute_target_holding_values(config.satellite, holding_values, config.substitutions)
    purchases = determine_buy_shares(targets, target_holding_values, market_data)
    distribute_shares(purchases, account_states, market_data, config.substitutions)
    allocate_core(account_states, config.core, market_data, config.substitutions)
    print_report(account_states, market_data, substitutions=config.substitutions, shareable=shareable)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="portfolio-allocator",
        description="Calculate a target allocation across brokerage accounts.",
    )
    parser.add_argument(
        "--shareable",
        action="store_true",
        help="omit private accounts, position sizes, and portfolio amounts",
    )
    parser.add_argument("config", type=Path, help="path to a TOML configuration file")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        run(load_config(args.config), shareable=args.shareable)
    except (ConfigError, MarketDataError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
