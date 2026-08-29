# Copyright Ohyyp 2026
# SPDX-License-Identifier: GPL-3.0-or-later

from decimal import Decimal

from allocation import AccountState
from configuration import AccountConfig
from market_data import MarketQuote
from reporting import print_report


def quote(price: str, quote_type: str | None = "EQUITY") -> MarketQuote:
    return MarketQuote(price=Decimal(price), quote_type=quote_type)


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
    etf_section, equity_section = report.split("### Equities")
    assert report.startswith("# Portfolio Allocation Report")
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


def test_report_uses_final_asset_value_and_truncates_precision(capsys) -> None:
    market = {"FUND": quote("3", "ETF")}
    account = AccountState(
        "account",
        "broker",
        AccountConfig(
            money=Decimal("1"),
            fixed_assets={"FUND": Decimal("0.333333")},
        ),
        market,
    )

    print_report([account], market)

    report = capsys.readouterr().out
    assert "**Final account value:** $0.99" in report
    assert "| FUND | FUND | $3.00 | 0.33333 | $0.99 |" in report
    assert "**Section value:** $0.99" in report
    assert "$1.00" not in report
