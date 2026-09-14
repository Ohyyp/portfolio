# Copyright Ohyyp 2026
# SPDX-License-Identifier: GPL-3.0-or-later

from decimal import Decimal

import pytest

import portfolio_allocator
from configuration import Config
from market_data import MarketQuote


def quote(price: str, quote_type: str = "EQUITY") -> MarketQuote:
    return MarketQuote(price=Decimal(price), quote_type=quote_type)


def test_run_executes_the_complete_offline_allocation(monkeypatch, capsys) -> None:
    config = Config(
        core={"CORE_A": 40, "CORE_B": 60},
        broker={
            "test_broker": {
                "test_account": {
                    "money": 1000,
                }
            }
        },
        satellite={"TARGET": 50},
    )
    market = {
        "TARGET": quote("100"),
        "CORE_A": quote("100", "ETF"),
        "CORE_B": quote("50", "ETF"),
    }
    monkeypatch.setattr(
        portfolio_allocator,
        "fetch_market_data",
        lambda tickers: market,
    )

    portfolio_allocator.run(config)

    report = capsys.readouterr().out
    assert "| TARGET | TARGET | $100.00 | 5 |" in report
    assert "| CORE_A | CORE_A | $100.00 | 2 |" in report
    assert "| CORE_B | CORE_B | $50.00 | 6 |" in report


def test_main_returns_failure_for_invalid_config(tmp_path, capsys) -> None:
    config_path = tmp_path / "invalid.toml"
    config_path.write_text("satellite = {}", encoding="utf-8")

    exit_code = portfolio_allocator.main([str(config_path)])

    assert exit_code == 1
    assert "Error: Invalid config" in capsys.readouterr().err


def test_parser_supports_shareable_report() -> None:
    args = portfolio_allocator.build_parser().parse_args(["--shareable", "config.toml"])

    assert args.shareable is True
    assert args.config.name == "config.toml"


def test_main_passes_shareable_to_report(monkeypatch) -> None:
    config = object()
    received: list[tuple[object, bool]] = []
    monkeypatch.setattr(portfolio_allocator, "load_config", lambda path: config)
    monkeypatch.setattr(portfolio_allocator, "run", lambda value, *, shareable: received.append((value, shareable)))

    exit_code = portfolio_allocator.main(["--shareable", "config.toml"])

    assert exit_code == 0
    assert received == [(config, True)]


def test_run_treats_configured_core_assets_as_etfs_when_yahoo_disagrees(monkeypatch, capsys) -> None:
    config = Config(
        core={"UNKNOWN": 100},
        broker={"broker": {"account": {"money": 1000}}},
        satellite={"TARGET": 50},
    )
    market = {
        "TARGET": quote("100"),
        "UNKNOWN": quote("50", quote_type="UNKNOWN"),
    }
    monkeypatch.setattr(portfolio_allocator, "fetch_market_data", lambda tickers: market)

    portfolio_allocator.run(config)

    captured = capsys.readouterr()
    assert "Yahoo did not classify configured ETF assets as ETFs: UNKNOWN" in captured.err
    account_report = captured.out.split("## Broker · Account\n", maxsplit=1)[1]
    etf_section, equity_section = account_report.split("### Equities", maxsplit=1)
    assert "UNKNOWN" in etf_section
    assert "UNKNOWN" not in equity_section


def test_run_uses_config_account_order_for_risk_priority(monkeypatch, capsys) -> None:
    config = Config(
        core={"CORE": 100},
        broker={
            "broker": {
                "preferred": {"money": 100},
                "later": {"money": 100},
            }
        },
        satellite={"STOCK": 50},
    )
    market = {
        "CORE": quote("100", "ETF"),
        "STOCK": quote("100"),
    }
    monkeypatch.setattr(portfolio_allocator, "fetch_market_data", lambda tickers: market)

    portfolio_allocator.run(config)

    report = capsys.readouterr().out
    account_reports = report.split("## Broker · Preferred\n", maxsplit=1)[1]
    preferred, later = account_reports.split("## Broker · Later\n", maxsplit=1)
    assert "STOCK" in preferred
    assert "CORE" not in preferred
    assert "CORE" in later
    assert "STOCK" not in later


def test_run_calculates_account_leverage_from_total_portfolio_equity(monkeypatch, capsys) -> None:
    config = Config(
        core={"CORE": 100},
        broker={
            "broker": {
                "leveraged": {"money": 100, "leverage_rate": 10},
                "other": {"money": 900},
            }
        },
        satellite={"STOCK": 10},
    )
    market = {
        "CORE": quote("100", "ETF"),
        "STOCK": quote("10"),
    }
    monkeypatch.setattr(portfolio_allocator, "fetch_market_data", lambda tickers: market)

    portfolio_allocator.run(config)

    report = capsys.readouterr().out
    assert "| STOCK | STOCK | $10.00 | 11 |" in report
    assert "**Leverage maximum:** 10% ($100.00)" in report
    assert "**Borrowed:** $10.00" in report
    assert "**Cash:** -$10.00" in report
    assert "**Equity:** $1,000.00" in report


def test_run_counts_existing_substitutes_but_only_buys_the_target(monkeypatch, capsys) -> None:
    config = Config(
        core={"NEW": 50, "OTHER": 50},
        broker={
            "broker": {
                "account": {
                    "money": 1000,
                    "fixed_assets": {"OLD": 4},
                }
            }
        },
        satellite={"STOCK": 0},
        substitutions={"OLD": "NEW"},
    )
    market = {
        "NEW": quote("100", "ETF"),
        "OLD": quote("100", "ETF"),
        "OTHER": quote("100", "ETF"),
    }
    monkeypatch.setattr(portfolio_allocator, "fetch_market_data", lambda tickers: market)

    portfolio_allocator.run(config)

    report = capsys.readouterr().out
    assert "| OLD | OLD | $100.00 | 4 |" in report
    assert "| NEW | NEW | $100.00 | 1 |" in report
    assert "| OTHER | OTHER | $100.00 | 5 |" in report


def test_run_counts_a_substitute_toward_a_satellite_target(monkeypatch, capsys) -> None:
    config = Config(
        core={"CORE": 100},
        broker={
            "broker": {
                "account": {
                    "money": 1000,
                    "fixed_assets": {"OLD": 4},
                }
            }
        },
        satellite={"NEW": 50},
        substitutions={"OLD": "NEW"},
    )
    market = {
        "CORE": quote("100", "ETF"),
        "NEW": quote("100", "ETF"),
        "OLD": quote("100", "ETF"),
    }
    monkeypatch.setattr(portfolio_allocator, "fetch_market_data", lambda tickers: market)

    portfolio_allocator.run(config)

    report = capsys.readouterr().out
    assert "| OLD | OLD | $100.00 | 4 |" in report
    assert "| NEW | NEW | $100.00 | 1 |" in report
    assert "| CORE | CORE | $100.00 | 5 |" in report


def test_run_treats_substitution_sources_as_configured_etfs(monkeypatch, capsys) -> None:
    config = Config(
        core={"CORE": 100},
        broker={"broker": {"account": {"fixed_assets": {"OLD": 1}}}},
        satellite={"STOCK": 0},
        substitutions={"OLD": "CORE"},
    )
    market = {
        "CORE": quote("100", "ETF"),
        "OLD": quote("100", "EQUITY"),
    }
    monkeypatch.setattr(portfolio_allocator, "fetch_market_data", lambda tickers: market)

    portfolio_allocator.run(config)

    captured = capsys.readouterr()
    assert "configured ETF assets as ETFs: OLD" in captured.err
    assert "### ETFs" in captured.out
    assert "### Equities" not in captured.out


@pytest.mark.parametrize("leverage", [{"leverage_amount": 20}, {"leverage_rate": 20}])
def test_minimum_mode_runs_end_to_end_and_shareable_hides_amounts(monkeypatch, capsys, leverage) -> None:
    config = Config(
        core={"CORE": 100},
        satellite={"UNUSED": 0},
        broker={
            "private_broker": {
                "private_account": {
                    "money": 100,
                    "leverage_mode": "min",
                    **leverage,
                }
            }
        },
    )
    market = {"CORE": quote("70", "ETF")}
    monkeypatch.setattr(portfolio_allocator, "fetch_market_data", lambda tickers: market)
    portfolio_allocator.run(config)
    full = capsys.readouterr().out
    assert "**Leverage minimum:**" in full
    assert "**Borrowed:** $40.00" in full
    assert "| CORE | CORE | $70.00 | 2 | $140.00 |" in full
    portfolio_allocator.run(config, shareable=True)
    shareable = capsys.readouterr().out
    assert "minimum / 40.00% used" in shareable
    for private in ("Private Broker", "Private Account", "$20.00", "$40.00", "| Shares |", "| Value |"):
        assert private not in shareable


def test_infeasible_minimum_returns_domain_failure_without_markdown(monkeypatch, capsys) -> None:
    config = Config(
        core={"CORE": 100},
        satellite={"UNUSED": 0},
        broker={
            "broker": {
                "account": {
                    "money": 100,
                    "leverage_amount": 20,
                    "leverage_mode": "min",
                    "blocked_assets": ["CORE"],
                }
            }
        },
    )
    monkeypatch.setattr(portfolio_allocator, "load_config", lambda path: config)
    monkeypatch.setattr(portfolio_allocator, "fetch_market_data", lambda tickers: {"CORE": quote("10", "ETF")})
    assert portfolio_allocator.main(["unused.toml"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Cannot satisfy minimum borrowing" in captured.err


def test_borrowing_cannot_create_portfolio_equity(monkeypatch, capsys) -> None:
    config = Config(
        core={"CORE": 100},
        satellite={"UNUSED": 0},
        broker={"broker": {"account": {"money": 0, "leverage_amount": 20, "leverage_mode": "min"}}},
    )
    monkeypatch.setattr(portfolio_allocator, "load_config", lambda path: config)
    monkeypatch.setattr(portfolio_allocator, "fetch_market_data", lambda tickers: {"CORE": quote("10", "ETF")})
    assert portfolio_allocator.main(["unused.toml"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "base equity must be greater than zero" in captured.err
