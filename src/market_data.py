# Copyright Ohyyp 2026
# SPDX-License-Identifier: GPL-3.0-or-later

import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

import yfinance as yf

from configuration import ZERO

MAX_FETCH_WORKERS = 8


class MarketDataError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class MarketQuote:
    price: Decimal
    quote_type: str | None
    name: str | None = None
    expense_ratio: Decimal | None = None
    category: str | None = None
    market_cap: Decimal | None = None
    year_change: Decimal | None = None

    @property
    def is_etf(self) -> bool:
        return self.quote_type == "ETF"


def parse_price(ticker: str, value: object) -> Decimal:
    try:
        price = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise MarketDataError(
            f"{ticker} returned an invalid price: {value!r}"
        ) from error
    if not price.is_finite() or price <= ZERO:
        raise MarketDataError(f"{ticker} returned a non-positive price: {value!r}")
    return price


def parse_optional_decimal(value: object) -> Decimal | None:
    try:
        result = Decimal(str(value))
    except InvalidOperation, ValueError:
        return None
    return result if result.is_finite() else None


def parse_text(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def fetch_name(instrument: yf.Ticker) -> str | None:
    try:
        metadata = instrument.history_metadata
        return parse_text(metadata.get("longName")) or parse_text(
            metadata.get("shortName")
        )
    except Exception:
        return None


def fetch_etf_details(
    instrument: yf.Ticker, ticker: str
) -> tuple[Decimal | None, str | None]:
    try:
        fund_data = instrument.funds_data
        category = parse_text(fund_data.fund_overview.get("categoryName"))
        operations = fund_data.fund_operations
        expense_ratio = parse_optional_decimal(
            operations.at["Annual Report Expense Ratio", ticker]
        )
    except Exception:
        return None, None
    if expense_ratio is not None and expense_ratio < ZERO:
        expense_ratio = None
    return expense_ratio, category


def fetch_stock_details(fast_info: object) -> tuple[Decimal | None, Decimal | None]:
    try:
        market_cap = parse_optional_decimal(fast_info.get("marketCap"))
    except Exception:
        market_cap = None
    try:
        year_change = parse_optional_decimal(fast_info.get("yearChange"))
    except Exception:
        year_change = None
    if market_cap is not None and market_cap <= ZERO:
        market_cap = None
    return market_cap, year_change


def fetch_ticker_quote(ticker: str) -> tuple[MarketQuote, str | None]:
    try:
        instrument = yf.Ticker(ticker)
        fast_info = instrument.fast_info
        price = parse_price(ticker, fast_info.get("lastPrice"))
    except MarketDataError:
        raise
    except Exception as error:
        raise MarketDataError(f"{ticker} price request failed: {error}") from error

    warning = None
    try:
        raw_quote_type = fast_info.get("quoteType")
        quote_type = (
            raw_quote_type.strip().upper()
            if isinstance(raw_quote_type, str) and raw_quote_type.strip()
            else None
        )
    except Exception as error:
        quote_type = None
        warning = f"{ticker} quote type request failed: {error}; treating as stock."

    if quote_type in {None, "UNKNOWN"} and warning is None:
        warning = f"{ticker} has an unknown quote type; treating as stock."

    name = fetch_name(instrument)
    if quote_type == "ETF":
        expense_ratio, category = fetch_etf_details(instrument, ticker)
        market_cap = None
        year_change = None
    else:
        expense_ratio = None
        category = None
        market_cap, year_change = fetch_stock_details(fast_info)

    return (
        MarketQuote(
            price=price,
            quote_type=quote_type,
            name=name,
            expense_ratio=expense_ratio,
            category=category,
            market_cap=market_cap,
            year_change=year_change,
        ),
        warning,
    )


def fetch_ticker_result(ticker: str) -> tuple[MarketQuote | None, str | None]:
    try:
        return fetch_ticker_quote(ticker)
    except Exception as error:
        return None, str(error)


def fetch_market_data(
    tickers: set[str], max_workers: int = MAX_FETCH_WORKERS
) -> dict[str, MarketQuote]:
    symbols = sorted(tickers)
    if not symbols:
        return {}
    if max_workers < 1:
        raise ValueError("max_workers must be positive")

    print(f"Fetching market data for: {', '.join(symbols)}...", file=sys.stderr)
    results: dict[str, MarketQuote] = {}
    errors: list[str] = []
    worker_count = min(max_workers, len(symbols))

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        outcomes = executor.map(fetch_ticker_result, symbols)
        for ticker, (quote, message) in zip(symbols, outcomes, strict=True):
            if quote is None:
                errors.append(message or f"{ticker} market data request failed")
                continue
            results[ticker] = quote
            if message is not None:
                print(f"Warning: {message}", file=sys.stderr)

    if errors:
        raise MarketDataError(
            f"Unable to fetch required market prices: {'; '.join(errors)}"
        )

    return results
