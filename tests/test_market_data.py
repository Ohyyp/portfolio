# Copyright Ohyyp 2026
# SPDX-License-Identifier: GPL-3.0-or-later

from decimal import Decimal

import pytest

import market_data
from market_data import MarketDataError, MarketQuote, fetch_market_data


def quote(price: str, quote_type: str | None = "EQUITY") -> MarketQuote:
    return MarketQuote(price=Decimal(price), quote_type=quote_type)


def test_fetch_market_data_classifies_only_etfs(monkeypatch, capsys) -> None:
    responses = {
        "AAPL": {"lastPrice": 250.5, "quoteType": "EQUITY"},
        "MYSTERY": {"lastPrice": 10.0, "quoteType": None},
        "QQQM": {"lastPrice": 300.25, "quoteType": "etf"},
    }

    class FakeTicker:
        def __init__(self, ticker: str) -> None:
            self.fast_info = responses[ticker]

    monkeypatch.setattr(market_data.yf, "Ticker", FakeTicker)

    quotes = fetch_market_data(set(responses))

    assert quotes == {
        "AAPL": quote("250.5"),
        "MYSTERY": quote("10.0", quote_type=None),
        "QQQM": quote("300.25", quote_type="ETF"),
    }
    assert "MYSTERY has an unknown quote type" in capsys.readouterr().err


def test_quote_type_failure_keeps_price_and_falls_back_to_stock(
    monkeypatch, capsys
) -> None:
    class FailingQuoteTypeInfo:
        def get(self, key: str):
            if key == "lastPrice":
                return 123.45
            raise RuntimeError("quote type unavailable")

    class FakeTicker:
        fast_info = FailingQuoteTypeInfo()

        def __init__(self, ticker: str) -> None:
            self.ticker = ticker

    monkeypatch.setattr(market_data.yf, "Ticker", FakeTicker)

    quotes = fetch_market_data({"TEST"})

    assert quotes == {"TEST": quote("123.45", quote_type=None)}
    assert "treating as stock" in capsys.readouterr().err


def test_fetch_market_data_includes_optional_stock_and_etf_details(monkeypatch) -> None:
    class FakeIndexer:
        def __getitem__(self, key):
            assert key == ("Annual Report Expense Ratio", "QQQM")
            return 0.0015

    class FakeOperations:
        at = FakeIndexer()

    class FakeFundData:
        def __init__(self) -> None:
            self.fund_overview = {"categoryName": "Large Growth"}
            self.fund_operations = FakeOperations()

    class FakeTicker:
        def __init__(self, ticker: str) -> None:
            self.ticker = ticker
            self.fast_info = {
                "lastPrice": 100,
                "marketCap": 1_250_000_000_000,
                "quoteType": "ETF" if ticker == "QQQM" else "EQUITY",
                "yearChange": 0.125,
            }
            self.history_metadata = {"longName": f"{ticker} Name"}
            self.funds_data = FakeFundData()

    monkeypatch.setattr(market_data.yf, "Ticker", FakeTicker)

    quotes = fetch_market_data({"AAPL", "QQQM"})

    assert quotes["AAPL"] == MarketQuote(
        price=Decimal("100"),
        quote_type="EQUITY",
        name="AAPL Name",
        market_cap=Decimal("1250000000000"),
        year_change=Decimal("0.125"),
    )
    assert quotes["QQQM"] == MarketQuote(
        price=Decimal("100"),
        quote_type="ETF",
        name="QQQM Name",
        expense_ratio=Decimal("0.0015"),
        category="Large Growth",
    )


def test_invalid_optional_name_metadata_does_not_discard_price(monkeypatch) -> None:
    class FakeTicker:
        def __init__(self, ticker: str) -> None:
            self.ticker = ticker
            self.fast_info = {"lastPrice": 100, "quoteType": "EQUITY"}
            self.history_metadata = None

    monkeypatch.setattr(market_data.yf, "Ticker", FakeTicker)

    assert fetch_market_data({"TEST"}) == {"TEST": quote("100")}


@pytest.mark.parametrize("price", [None, 0, -1, float("nan")])
def test_fetch_market_data_rejects_invalid_prices(monkeypatch, price) -> None:
    class FakeTicker:
        def __init__(self, ticker: str) -> None:
            self.fast_info = {"lastPrice": price, "quoteType": "EQUITY"}

    monkeypatch.setattr(market_data.yf, "Ticker", FakeTicker)

    with pytest.raises(MarketDataError, match="Unable to fetch required market prices"):
        fetch_market_data({"TEST"})
