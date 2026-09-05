# Copyright Ohyyp 2026
# SPDX-License-Identifier: GPL-3.0-or-later

from decimal import Decimal

from allocation import AccountState, apply_portfolio_leverage, distribute_shares
from configuration import AccountConfig
from market_data import MarketQuote
from reporting import format_money, print_report


def quote(price: str, quote_type: str | None = "EQUITY") -> MarketQuote:
    return MarketQuote(price=Decimal(price), quote_type=quote_type)


def test_money_format_does_not_expose_negative_zero() -> None:
    assert format_money(Decimal("-0.001")) == "$0.00"


def test_report_treats_non_etf_quote_types_as_equities(capsys) -> None:
    market = {
        "FUND": MarketQuote(
            price=Decimal("100"),
            quote_type="ETF",
            name="Fund Name",
            expense_ratio=Decimal("0.0015"),
            category="Large Growth",
        ),
        "UNKNOWN": MarketQuote(
            price=Decimal("200"),
            quote_type=None,
            name="Mystery | Corp",
            market_cap=Decimal("1234567890000"),
            year_change=Decimal("0.1234"),
        ),
    }
    account = AccountState(
        "roth_401k",
        "charles_schwab",
        AccountConfig(
            money=Decimal("300"),
            fixed_assets={"FUND": Decimal("1"), "UNKNOWN": Decimal("1")},
        ),
        market,
    )

    print_report([account], market)

    report = capsys.readouterr().out
    account_report = report.split("## Charles Schwab · Roth 401(k)\n", maxsplit=1)[1]
    etf_section, equity_section = account_report.split("### Equities")
    assert report.startswith("# Portfolio Allocation")
    assert "**Equity:** $300.00 · **Gross exposure:** 100.00% · **Cash:** $0.00" in report
    assert "Prices are the latest" not in report
    assert "This plan excludes" not in report
    assert "## Charles Schwab · Roth 401(k)" in report
    assert "### ETFs" in etf_section
    assert "FUND" in etf_section
    assert "Fund Name" in etf_section
    assert "0.15%" in etf_section
    assert "Large Growth" in etf_section
    assert "UNKNOWN" in equity_section
    assert "Mystery \\| Corp" in equity_section
    assert "$1.23T" in equity_section
    assert "12.34%" in equity_section


def test_report_includes_cash_in_final_values_and_percentages(capsys) -> None:
    market = {"FUND": quote("3", "ETF")}
    account = AccountState(
        "account",
        "broker",
        AccountConfig(
            money=Decimal("1.5"),
            fixed_assets={"FUND": Decimal("0.333333")},
        ),
        market,
    )

    print_report([account], market)

    report = capsys.readouterr().out
    assert report.count("**Equity:** $1.50") == 2
    assert "**Cash:** $0.50" in report
    assert "| FUND | FUND | $3.00 | 0.33333 | $0.99 |" in report
    assert "**Section value:** $0.99" in report
    assert "66.67%" in report


def test_report_aggregates_positions_across_accounts_and_preserves_account_details(capsys) -> None:
    market = {
        "FUND": quote("10", "ETF"),
        "STOCK": quote("20"),
        "OLD": quote("25", "ETF"),
        "NEW": quote("50", "ETF"),
    }
    accounts = [
        AccountState(
            "first",
            "broker",
            AccountConfig(money=500, fixed_assets={"FUND": Decimal("1.12567"), "STOCK": 3, "OLD": 2}),
            market,
        ),
        AccountState(
            "second",
            "broker",
            AccountConfig(money=500, fixed_assets={"FUND": Decimal("2.5"), "STOCK": 4, "NEW": 1}),
            market,
        ),
    ]

    print_report(accounts, market, substitutions={"OLD": "NEW"})

    report = capsys.readouterr().out
    portfolio, account_reports = report.split("## Broker · First\n", maxsplit=1)
    first, second = account_reports.split("## Broker · Second\n", maxsplit=1)
    assert "## Portfolio\n" in portfolio
    assert "**Equity:** $1,000.00 · **Gross exposure:** 27.63% · **Cash:** $723.74" in portfolio
    assert "| FUND | FUND | $10.00 | 3.62567 | $36.25 | — | — | — | 3.63% |" in portfolio
    assert "| STOCK | STOCK | $20.00 | 7 | $140.00 | — | — | 14.00% |" in portfolio
    assert "| OLD | OLD | $25.00 | 2 | $50.00 | — | — | NEW | 5.00% |" in portfolio
    assert "| NEW | NEW | $50.00 | 1 | $50.00 | — | — | — | 5.00% |" in portfolio
    assert portfolio.count("| FUND |") == 1
    assert "| Account |" not in portfolio
    assert "**Account:**" not in portfolio
    assert "| FUND | FUND | $10.00 | 1.12567 | $11.25 | — | — | — | 2.25% | 1.13% |" in first
    assert "| FUND | FUND | $10.00 | 2.50000 | $25.00 | — | — | — | 5.00% | 2.50% |" in second


def test_portfolio_summary_accounts_for_borrowing_without_double_counting(capsys) -> None:
    market = {"FUND": quote("5", "ETF")}
    account = AccountState(
        "leveraged", "broker", AccountConfig(money=100, fixed_assets={"FUND": 20}, leverage_rate=10), market
    )
    apply_portfolio_leverage([account])
    distribute_shares({"FUND": 1}, [account], market)

    print_report([account], market)

    portfolio = capsys.readouterr().out.split("## Broker · Leveraged\n", maxsplit=1)[0]
    assert "**Equity:** $100.00 · **Gross exposure:** 105.00% · **Cash:** -$5.00" in portfolio
    assert "| FUND | FUND | $5.00 | 21 | $105.00 | — | — | — | 105.00% |" in portfolio


def test_report_explains_portfolio_based_leverage(capsys) -> None:
    market = {"FUND": quote("5", "ETF")}
    accounts = [
        AccountState(
            "leveraged",
            "broker",
            AccountConfig(money=100, fixed_assets={"FUND": 20}, leverage_rate=1),
            market,
        ),
        AccountState("other", "broker", AccountConfig(money=900), market),
    ]
    apply_portfolio_leverage(accounts)
    distribute_shares({"FUND": 1}, accounts, market)

    print_report(accounts, market)

    report = capsys.readouterr().out
    assert "**Leverage budget:** 1% ($10.00)" in report
    assert "**Borrowed:** $5.00" in report
    assert "**Cash:** -$5.00" in report
    assert "**Equity:** $1,000.00 · **Gross exposure:** 10.50% · **Cash:** $895.00" in report


def test_shareable_report_keeps_public_metadata_and_omits_private_positions(capsys) -> None:
    market = {
        "FUND": MarketQuote(
            price=Decimal("100"),
            quote_type="ETF",
            name="Fund Name",
            expense_ratio=Decimal("0.0015"),
            category="Large Growth",
        ),
        "STOCK": MarketQuote(
            price=Decimal("200"),
            quote_type="EQUITY",
            name="Stock Name",
            market_cap=Decimal("1000000000"),
            year_change=Decimal("0.1"),
        ),
    }
    account = AccountState(
        "private_account",
        "private_broker",
        AccountConfig(money=1000, fixed_assets={"FUND": 2, "STOCK": 1}),
        market,
    )

    print_report([account], market, shareable=True)

    report = capsys.readouterr().out
    assert report.startswith("# Portfolio Allocation — Shareable")
    assert "**Gross exposure:** 40.00% · **Cash:** 60.00%" in report
    assert "| FUND | Fund Name | $100.00 | 0.15% | Large Growth | — | 20.00% |" in report
    assert "| STOCK | Stock Name | $200.00 | $1.00B | 10.00% | 20.00% |" in report
    assert "## ETFs" in report
    assert "## Equities" in report
    assert "Shares" not in report
    assert "Value" not in report
    assert "private_broker" not in report
    assert "private_account" not in report
    assert "Private Broker" not in report
    assert "Private Account" not in report
    assert "## Portfolio\n" not in report


def test_shareable_report_apportions_rounding_to_exactly_one_hundred(capsys) -> None:
    market = {ticker: quote("1") for ticker in ("A", "B", "C")}
    account = AccountState(
        "account",
        "broker",
        AccountConfig(fixed_assets={"A": 1, "B": 1, "C": 1}),
        market,
    )

    print_report([account], market, shareable=True)

    report = capsys.readouterr().out
    assert "| A | A | $1.00 | — | — | 33.34% |" in report
    assert "| B | B | $1.00 | — | — | 33.33% |" in report
    assert "| C | C | $1.00 | — | — | 33.33% |" in report
    assert "**Cash:** 0.00%" in report


def test_shareable_report_does_not_confuse_a_cash_ticker_with_cash(capsys) -> None:
    market = {"CASH": quote("25")}
    account = AccountState(
        "account",
        "broker",
        AccountConfig(money=100, fixed_assets={"CASH": 1}),
        market,
    )

    print_report([account], market, shareable=True)

    report = capsys.readouterr().out
    assert "| CASH | CASH | $25.00 | — | — | 25.00% |" in report
    assert "**Cash:** 75.00%" in report


def test_report_marks_account_percentages_undefined_for_zero_equity(capsys) -> None:
    market = {"FUND": quote("10", "ETF")}
    leveraged = AccountState(
        "leveraged",
        "broker",
        AccountConfig(money=0, leverage_rate=10),
        market,
    )
    other = AccountState("other", "broker", AccountConfig(money=100), market)
    apply_portfolio_leverage([leveraged, other])
    distribute_shares({"FUND": 1}, [leveraged, other], market)

    print_report([leveraged, other], market)

    leveraged_report = capsys.readouterr().out.split("## Broker · Other", maxsplit=1)[0]
    assert "**Equity:** $0.00" in leveraged_report
    assert "**Section value:** $10.00 · **Account:** — · **Portfolio:** 10.00%" in leveraged_report
    assert "| FUND | FUND | $10.00 | 1 | $10.00 | — | — | — | — | 10.00% |" in leveraged_report


def test_shareable_report_supports_negative_cash_and_hides_borrowing_amount(capsys) -> None:
    market = {"FUND": quote("5", "ETF")}
    account = AccountState(
        "private_account",
        "private_broker",
        AccountConfig(money=100, fixed_assets={"FUND": 20}, leverage_rate=10),
        market,
    )
    apply_portfolio_leverage([account])
    distribute_shares({"FUND": 1}, [account], market)

    print_report([account], market, shareable=True)

    report = capsys.readouterr().out
    assert "**Gross exposure:** 105.00% · **Cash:** -5.00% · **Leverage:** 10% budget / 5.00% used" in report
    assert "**Leverage budget:**" not in report
    assert "**Borrowed:**" not in report
    assert "private_account" not in report
    assert "private_broker" not in report


def test_reports_show_which_target_a_substitute_counts_toward(capsys) -> None:
    market = {
        "NEW": MarketQuote(price=Decimal("100"), quote_type="ETF"),
        "OLD": MarketQuote(price=Decimal("100"), quote_type="ETF"),
    }
    account = AccountState(
        "account",
        "broker",
        AccountConfig(fixed_assets={"OLD": 1}),
        market,
    )

    print_report([account], market, substitutions={"OLD": "NEW"})
    full_report = capsys.readouterr().out
    print_report([account], market, substitutions={"OLD": "NEW"}, shareable=True)
    shareable_report = capsys.readouterr().out

    assert "| OLD | OLD | $100.00 | 1 | $100.00 | — | — | NEW |" in full_report
    assert "| OLD | OLD | $100.00 | — | — | NEW | 100.00% |" in shareable_report
