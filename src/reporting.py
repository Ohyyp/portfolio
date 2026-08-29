# Copyright Ohyyp 2026
# SPDX-License-Identifier: GPL-3.0-or-later

from collections.abc import Mapping, Sequence
from decimal import ROUND_DOWN, Decimal

from allocation import AccountState, truncate_shares
from configuration import HUNDRED, ZERO
from market_data import MarketQuote

MONEY_QUANTUM = Decimal("0.01")
MISSING_VALUE = "—"
ACCOUNT_TERMS = {"401k": "401(k)", "hsa": "HSA", "ira": "IRA"}


def truncate_money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_QUANTUM, rounding=ROUND_DOWN)


def format_money(value: Decimal) -> str:
    return f"${truncate_money(value):,.2f}"


def format_identifier(value: str) -> str:
    return " ".join(ACCOUNT_TERMS.get(part, part.title()) for part in value.split("_"))


def escape_markdown(value: str) -> str:
    return " ".join(value.replace("|", "\\|").split())


def partition_holdings(state: AccountState, market_data: Mapping[str, MarketQuote]) -> tuple[dict[str, Decimal], dict[str, Decimal]]:
    etfs: dict[str, Decimal] = {}
    equities: dict[str, Decimal] = {}
    for ticker, shares in state.holdings.items():
        if shares <= ZERO:
            continue
        destination = etfs if market_data[ticker].is_etf else equities
        destination[ticker] = shares
    return etfs, equities


def format_shares(shares: Decimal) -> str:
    shares = truncate_shares(shares)
    if shares == shares.to_integral_value():
        return str(int(shares))
    return f"{shares:.5f}"


def account_value(state: AccountState, market_data: Mapping[str, MarketQuote]) -> Decimal:
    return sum(
        (shares * market_data[ticker].price for ticker, shares in state.holdings.items() if shares > ZERO),
        ZERO,
    )


def percentage(value: Decimal, total: Decimal) -> Decimal:
    return value / total * HUNDRED if total > ZERO else ZERO


def format_percentage(value: Decimal) -> str:
    return f"{value:.2f}%"


def format_ratio(value: Decimal | None) -> str:
    return format_percentage(value * HUNDRED) if value is not None else MISSING_VALUE


def format_market_cap(value: Decimal | None) -> str:
    if value is None:
        return MISSING_VALUE
    for scale, suffix in (
        (Decimal("1000000000000"), "T"),
        (Decimal("1000000000"), "B"),
        (Decimal("1000000"), "M"),
    ):
        if value >= scale:
            return f"${truncate_money(value / scale):,.2f}{suffix}"
    return format_money(value)


def format_name(ticker: str, quote: MarketQuote) -> str:
    return escape_markdown(quote.name or ticker)


def print_section(
    title: str,
    assets: Mapping[str, Decimal],
    market_data: Mapping[str, MarketQuote],
    account_total: Decimal,
    portfolio_total: Decimal,
) -> None:
    if not assets:
        return

    valued_assets = [(ticker, shares, shares * market_data[ticker].price) for ticker, shares in assets.items()]
    section_value = sum((value for _, _, value in valued_assets), ZERO)

    print(f"\n### {title}\n")
    print(f"**Section value:** {format_money(section_value)} · **Account:** {format_percentage(percentage(section_value, account_total))} · **Portfolio:** {format_percentage(percentage(section_value, portfolio_total))}\n")

    if title == "ETFs":
        print("| Ticker | Name | Price | Shares | Value | Expense Ratio | Category | Account | Portfolio |")
        print("| :--- | :--- | ---: | ---: | ---: | ---: | :--- | ---: | ---: |")
    else:
        print("| Ticker | Name | Price | Shares | Value | Market Cap | 1Y Change | Account | Portfolio |")
        print("| :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")

    for ticker, shares, value in sorted(valued_assets, key=lambda item: item[2], reverse=True):
        quote = market_data[ticker]
        common = f"| {ticker} | {format_name(ticker, quote)} | {format_money(quote.price)} | {format_shares(shares)} | {format_money(value)} |"
        account_percentage = format_percentage(percentage(value, account_total))
        portfolio_percentage = format_percentage(percentage(value, portfolio_total))
        if title == "ETFs":
            category = escape_markdown(quote.category) if quote.category else MISSING_VALUE
            print(f"{common} {format_ratio(quote.expense_ratio)} | {category} | {account_percentage} | {portfolio_percentage} |")
        else:
            print(f"{common} {format_market_cap(quote.market_cap)} | {format_ratio(quote.year_change)} | {account_percentage} | {portfolio_percentage} |")


def print_report(
    account_states: Sequence[AccountState],
    market_data: Mapping[str, MarketQuote],
) -> None:
    account_totals = [account_value(state, market_data) for state in account_states]
    portfolio_total = sum(account_totals, ZERO)

    print("# Portfolio Allocation Report\n")
    print(f"**Final portfolio value:** {format_money(portfolio_total)}")

    for state, account_total in zip(account_states, account_totals, strict=True):
        broker = format_identifier(state.broker)
        account = format_identifier(state.name)
        print(f"\n## {broker} · {account}\n")
        if state.config.leverage_rate > 0:
            print(f"- **Base equity:** {format_money(state.base_money)}")
            print(f"- **Leverage rate:** {state.config.leverage_rate}%")
        print(f"- **Final account value:** {format_money(account_total)}")

        etfs, equities = partition_holdings(state, market_data)
        print_section("ETFs", etfs, market_data, account_total, portfolio_total)
        print_section("Equities", equities, market_data, account_total, portfolio_total)
