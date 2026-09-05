# Copyright Ohyyp 2026
# SPDX-License-Identifier: GPL-3.0-or-later

from collections.abc import Mapping, Sequence
from decimal import ROUND_DOWN, ROUND_FLOOR, Decimal

from allocation import AccountState, compute_holding_values, truncate_shares
from configuration import HUNDRED, ZERO
from market_data import MarketQuote

MONEY_QUANTUM = Decimal("0.01")
PERCENTAGE_QUANTUM = Decimal("0.01")
MISSING_VALUE = "—"
ACCOUNT_TERMS = {"401k": "401(k)", "hsa": "HSA", "ira": "IRA"}


def truncate_money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_QUANTUM, rounding=ROUND_DOWN)


def format_money(value: Decimal) -> str:
    truncated = truncate_money(value)
    if truncated == ZERO:
        return "$0.00"
    if truncated < ZERO:
        return f"-${abs(truncated):,.2f}"
    return f"${truncated:,.2f}"


def format_identifier(value: str) -> str:
    return " ".join(ACCOUNT_TERMS.get(part, part.title()) for part in value.split("_"))


def escape_markdown(value: str) -> str:
    return " ".join(value.replace("|", "\\|").split())


def partition_holdings(
    holdings: Mapping[str, Decimal], market_data: Mapping[str, MarketQuote]
) -> tuple[dict[str, Decimal], dict[str, Decimal]]:
    etfs: dict[str, Decimal] = {}
    equities: dict[str, Decimal] = {}
    for ticker, shares in holdings.items():
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


def invested_value(state: AccountState, market_data: Mapping[str, MarketQuote]) -> Decimal:
    return sum(
        (shares * market_data[ticker].price for ticker, shares in state.holdings.items() if shares > ZERO),
        ZERO,
    )


def account_value(state: AccountState, market_data: Mapping[str, MarketQuote]) -> Decimal:
    return invested_value(state, market_data) + state.free_cash


def borrowed_amount(state: AccountState) -> Decimal:
    return max(-state.free_cash, ZERO)


def percentage(value: Decimal, total: Decimal) -> Decimal:
    return value / total * HUNDRED if total > ZERO else ZERO


def apportioned_percentages(values: Sequence[Decimal]) -> list[Decimal]:
    total = sum(values, ZERO)
    if total <= ZERO:
        return [ZERO] * len(values)
    exact = [percentage(value, total) for value in values]
    result = [value.quantize(PERCENTAGE_QUANTUM, rounding=ROUND_FLOOR) for value in exact]
    remainder = int((HUNDRED - sum(result, ZERO)) / PERCENTAGE_QUANTUM)
    ranked = sorted(range(len(values)), key=lambda index: (-(exact[index] - result[index]), index))
    for index in ranked[:remainder]:
        result[index] += PERCENTAGE_QUANTUM
    return result


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
    account_total: Decimal | None,
    portfolio_total: Decimal,
    substitutions: Mapping[str, str],
) -> None:
    if not assets:
        return

    valued_assets = [(ticker, shares, shares * market_data[ticker].price) for ticker, shares in assets.items()]
    section_value = sum((value for _, _, value in valued_assets), ZERO)
    account_summary = ""
    if account_total is not None:
        account_section_percentage = (
            format_percentage(percentage(section_value, account_total)) if account_total > ZERO else MISSING_VALUE
        )
        account_summary = f" · **Account:** {account_section_percentage}"
    portfolio_section_percentage = format_percentage(percentage(section_value, portfolio_total))

    print(f"\n### {title}\n")
    print(
        f"**Section value:** {format_money(section_value)}{account_summary} · "
        f"**Portfolio:** {portfolio_section_percentage}\n"
    )

    account_column = " Account |" if account_total is not None else ""
    account_alignment = " ---: |" if account_total is not None else ""
    if title == "ETFs":
        print(
            "| Ticker | Name | Price | Shares | Value | Expense Ratio | Category | "
            f"Counts Toward |{account_column} Portfolio |"
        )
        print(f"| :--- | :--- | ---: | ---: | ---: | ---: | :--- | :--- |{account_alignment} ---: |")
    else:
        print(f"| Ticker | Name | Price | Shares | Value | Market Cap | 1Y Change |{account_column} Portfolio |")
        print(f"| :--- | :--- | ---: | ---: | ---: | ---: | ---: |{account_alignment} ---: |")

    for ticker, shares, value in sorted(valued_assets, key=lambda item: item[2], reverse=True):
        quote = market_data[ticker]
        common = (
            f"| {ticker} | {format_name(ticker, quote)} | {format_money(quote.price)} | "
            f"{format_shares(shares)} | {format_money(value)} |"
        )
        account_cell = ""
        if account_total is not None:
            account_percentage = (
                format_percentage(percentage(value, account_total)) if account_total > ZERO else MISSING_VALUE
            )
            account_cell = f" {account_percentage} |"
        portfolio_percentage = format_percentage(percentage(value, portfolio_total))
        if title == "ETFs":
            category = escape_markdown(quote.category) if quote.category else MISSING_VALUE
            target = substitutions.get(ticker, MISSING_VALUE)
            print(
                f"{common} {format_ratio(quote.expense_ratio)} | {category} | {target} |"
                f"{account_cell} {portfolio_percentage} |"
            )
        else:
            print(
                f"{common} {format_market_cap(quote.market_cap)} | {format_ratio(quote.year_change)} |"
                f"{account_cell} {portfolio_percentage} |"
            )


def print_shareable_section(
    title: str,
    assets: Sequence[tuple[str, Decimal]],
    percentages: Mapping[str, Decimal],
    market_data: Mapping[str, MarketQuote],
    substitutions: Mapping[str, str],
) -> None:
    if not assets:
        return

    print(f"\n## {title}\n")
    section_percentage = sum((percentages[ticker] for ticker, _ in assets), ZERO)
    print(f"**Portfolio:** {format_percentage(section_percentage)}\n")
    if title == "ETFs":
        print("| Ticker | Name | Price | Expense Ratio | Category | Counts Toward | Portfolio |")
        print("| :--- | :--- | ---: | ---: | :--- | :--- | ---: |")
    else:
        print("| Ticker | Name | Price | Market Cap | 1Y Change | Portfolio |")
        print("| :--- | :--- | ---: | ---: | ---: | ---: |")

    for ticker, _ in assets:
        quote = market_data[ticker]
        common = f"| {ticker} | {format_name(ticker, quote)} | {format_money(quote.price)} |"
        portfolio_percentage = format_percentage(percentages[ticker])
        if title == "ETFs":
            category = escape_markdown(quote.category) if quote.category else MISSING_VALUE
            target = substitutions.get(ticker, MISSING_VALUE)
            print(f"{common} {format_ratio(quote.expense_ratio)} | {category} | {target} | {portfolio_percentage} |")
        else:
            print(
                f"{common} {format_market_cap(quote.market_cap)} | {format_ratio(quote.year_change)} | "
                f"{portfolio_percentage} |"
            )


def print_shareable_report(
    account_states: Sequence[AccountState],
    market_data: Mapping[str, MarketQuote],
    substitutions: Mapping[str, str],
) -> None:
    assets = [
        (ticker, value) for ticker, value in compute_holding_values(account_states, market_data).items() if value > ZERO
    ]
    cash = sum((state.free_cash for state in account_states), ZERO)
    assets.sort(key=lambda item: (-item[1], item[0]))
    percentages = apportioned_percentages([*(value for _, value in assets), cash])
    percentage_by_ticker = {ticker: value for (ticker, _), value in zip(assets, percentages[:-1], strict=True)}
    cash_percentage = percentages[-1]
    etfs = [(ticker, value) for ticker, value in assets if market_data[ticker].is_etf]
    equities = [(ticker, value) for ticker, value in assets if not market_data[ticker].is_etf]

    print("# Portfolio Allocation — Shareable\n")
    gross_exposure = sum((percentage_by_ticker[ticker] for ticker, _ in assets), ZERO)
    summary = [
        f"**Gross exposure:** {format_percentage(gross_exposure)}",
        f"**Cash:** {format_percentage(cash_percentage)}",
    ]
    leveraged_account = next((state for state in account_states if state.leverage_rate > 0), None)
    if leveraged_account is not None:
        portfolio_base_money = sum((state.base_money for state in account_states), ZERO)
        actual_rate = percentage(borrowed_amount(leveraged_account), portfolio_base_money)
        summary.append(
            f"**Leverage:** {leveraged_account.leverage_rate}% budget / {format_percentage(actual_rate)} used"
        )
    print(" · ".join(summary))
    print_shareable_section("ETFs", etfs, percentage_by_ticker, market_data, substitutions)
    print_shareable_section("Equities", equities, percentage_by_ticker, market_data, substitutions)


def print_report(
    account_states: Sequence[AccountState],
    market_data: Mapping[str, MarketQuote],
    *,
    substitutions: Mapping[str, str] | None = None,
    shareable: bool = False,
) -> None:
    substitutions = substitutions or {}
    if shareable:
        print_shareable_report(account_states, market_data, substitutions)
        return

    account_totals = [account_value(state, market_data) for state in account_states]
    portfolio_total = sum(account_totals, ZERO)
    gross_exposure = sum((invested_value(state, market_data) for state in account_states), ZERO)
    portfolio_cash = sum((state.free_cash for state in account_states), ZERO)

    print("# Portfolio Allocation\n\n## Portfolio\n")
    print(
        f"**Equity:** {format_money(portfolio_total)} · "
        f"**Gross exposure:** {format_percentage(percentage(gross_exposure, portfolio_total))} · "
        f"**Cash:** {format_money(portfolio_cash)}"
    )

    portfolio_holdings: dict[str, Decimal] = {}
    for state in account_states:
        for ticker, shares in state.holdings.items():
            if shares > ZERO:
                portfolio_holdings[ticker] = portfolio_holdings.get(ticker, ZERO) + shares
    etfs, equities = partition_holdings(portfolio_holdings, market_data)
    print_section("ETFs", etfs, market_data, None, portfolio_total, substitutions)
    print_section("Equities", equities, market_data, None, portfolio_total, substitutions)

    for state, account_total in zip(account_states, account_totals, strict=True):
        broker = format_identifier(state.broker)
        account = format_identifier(state.name)
        print(f"\n## {broker} · {account}\n")
        summary = [f"**Equity:** {format_money(account_total)}", f"**Cash:** {format_money(state.free_cash)}"]
        if state.leverage_rate > 0:
            summary.extend(
                (
                    f"**Leverage budget:** {state.leverage_rate}% ({format_money(state.leverage_limit)})",
                    f"**Borrowed:** {format_money(borrowed_amount(state))}",
                )
            )
        print(" · ".join(summary))

        etfs, equities = partition_holdings(state.holdings, market_data)
        print_section("ETFs", etfs, market_data, account_total, portfolio_total, substitutions)
        print_section("Equities", equities, market_data, account_total, portfolio_total, substitutions)
