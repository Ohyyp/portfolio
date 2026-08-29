# Repository Guide

## Scope

Keep this repository a focused Python 3.14 CLI. Use flat modules under `src/`; do not add a nested package, framework, or service layer without a feature that requires it. The program plans trades but never places them.

## Layout

- `src/portfolio_allocator.py`: CLI and orchestration
- `src/configuration.py`: strict TOML models and normalization
- `src/market_data.py`: concurrent Yahoo Finance boundary
- `src/allocation.py`: account state and allocation engine
- `src/reporting.py`: deterministic Markdown report
- `tests/`: offline tests matching those responsibilities
- `config.toml`: private, Git-ignored portfolio snapshot

## Workflow

Use `uv`; never edit `uv.lock` manually.

```bash
uv sync --locked
uv run portfolio-allocator config.toml
uv run ruff format .
uv run ruff check .
uv run ruff format --check .
uv run pytest
uv run python -m compileall -q src tests
```

## Contracts

- Models forbid unknown fields. Broker and account names are lowercase snake_case; tickers are normalized uppercase without duplicates.
- `[satellite]` is non-empty, contains strict integer percentages from 0 through 100, and totals at most 100.
- `[core]` uses strict integer percentages, is non-empty, totals exactly 100, and cannot overlap `[satellite]`. Enabled core tickers must be Yahoo-classified ETFs.
- Money and shares are non-negative. `leverage_rate` is a strict integer percentage from 0 through 99.
- Truncate final shares to five decimals and reported dollar values to cents; never round them. Derive final account values and report percentages from final holdings, not input money.
- Omitted account money is inferred from fixed holdings. Never expose the real config in tests or docs.
- Prices use `Decimal(str(value))` and must be finite and positive. Aggregate all price failures before aborting.
- `fetch_market_data()` is the only batch network boundary, uses at most eight threads, and reuses one `fast_info` object per ticker.
- Only normalized `quoteType == "ETF"` is an ETF. Type failures retain valid prices and fall back to equity.
- Reuse history metadata for asset names. ETF expense ratio and category come from `funds_data`; equity market cap and one-year change come from `fast_info`. Optional metadata failures return missing values without aborting.

## Allocation Semantics

1. Targets use total leveraged portfolio money; fixed values aggregate across accounts.
2. Satellite deficits never cause sales and are bought as whole shares. Process equities before regular ETFs and alphabetically within each tier; unknown types are equities.
3. Prefer accounts with an existing fixed position, then larger positions, free cash, and TOML declaration order. Fill an account before opening the same asset elsewhere.
4. Apply `[core]` weights to actual cash remaining after satellite purchases, not total portfolio value. Process core tickers alphabetically as the final risk tier.
5. Core allocations may be fractional. Prefer existing holders and consume account cash in blocks to limit account and fractional-position sprawl.
6. Preserve deterministic broker declaration order, then account declaration order within each broker, plus heap-based account selection.

Schema or algorithm changes require matching README, private config, and focused-test updates.

## Engineering

Use modern Python 3.14 syntax and `Decimal` for all financial arithmetic. Prefer typed boundaries and immutable slotted value objects. Keep stdout as valid standalone Markdown and stderr for diagnostics. Domain failures return 1 without a traceback; unexpected errors remain visible.

Tests must mock yfinance and remain independent of networks, market hours, ordering, and rate limits. Preserve unrelated working-tree changes. Avoid discretionary code comments, but retain mandatory licensing headers.

Preserve `LICENSE`, `.copywrite.hcl`, and every Python header:

```text
# Copyright Ohyyp 2026
# SPDX-License-Identifier: GPL-3.0-or-later
```
