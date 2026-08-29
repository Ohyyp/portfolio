# Copyright Ohyyp 2026
# SPDX-License-Identifier: GPL-3.0-or-later

from decimal import Decimal

import pytest

import portfolio_allocator
from configuration import Config, ConfigError
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


def test_run_requires_core_assets_to_be_etfs(monkeypatch) -> None:
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

    with pytest.raises(ConfigError, match="Core assets must be ETFs: UNKNOWN"):
        portfolio_allocator.run(config)


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
    preferred, later = report.split("## Broker · Later")
    assert "## Broker · Preferred" in preferred
    assert "STOCK" in preferred
    assert "CORE" not in preferred
    assert "CORE" in later
    assert "STOCK" not in later
