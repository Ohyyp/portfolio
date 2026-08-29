# Portfolio Allocator

Portfolio Allocator is a Python 3.14 CLI for planning a core–satellite portfolio across brokerage accounts. It reads a private TOML snapshot, fetches Yahoo Finance prices and instrument types, and prints proposed holdings. It never connects to a broker or places trades.

## Setup and Usage

```bash
uv sync --locked
uv run portfolio-allocator config.toml
uv run portfolio-allocator config.toml > report.md
```

Progress and errors go to stderr; stdout is a complete Markdown report that can be redirected directly to a file. Configuration and required market-data failures return status 1.

## Configuration

`config.toml` and the generated `report.md` are Git-ignored because they contain personal balances and holdings. Broker and account names use lowercase snake_case; tickers are normalized to uppercase.

```toml
[satellite]
NVDA = 15
SCHG = 10

[core]
IVV = 40
QQQM = 60

[broker.example_broker.taxable]
leverage_rate = 3
money = 100000

[broker.example_broker.taxable.fixed_assets]
NVDA = 100
QQQM = 25.5
```

`[satellite]` contains satellite targets as percentages of total portfolio money. It must be non-empty, each value must be an integer from 0 through 100, and the sum cannot exceed 100. Existing holdings count toward these targets; the allocator only buys deficits and never sells.

`[core]` replaces the old per-account `free_money_to` setting. It describes how actual cash left after satellite purchases is divided among broad-market ETFs. Its integer weights must total exactly 100, its tickers cannot also appear in `[satellite]`, and Yahoo Finance must classify every enabled core asset as an ETF. Core weights apply only to newly allocated residual cash; they do not rebalance existing core holdings.

Each account supports:

- `money`: optional non-negative account equity, not additional cash. If omitted, equity is inferred from fixed holdings.
- `leverage_rate`: optional integer percentage from 0 through 99; `3` means 3%.
- `fixed_assets`: optional current share counts. Decimal shares are accepted.

All configured percentages use TOML integers; decimal percentage literals are rejected. Unknown fields and invalid values are rejected. Required prices must be finite and positive, and a price failure aborts the complete allocation.

## Allocation Rules

1. Compute account money, including leverage, and subtract the market value of fixed holdings to obtain available cash.
2. Aggregate fixed holdings across all accounts and calculate satellite deficits against total portfolio targets.
3. Process satellite stocks first, then regular ETFs. Unknown types count as stocks; tickers within each risk tier use alphabetical order. Buy whole shares only.
4. For each satellite, prefer accounts already holding it, starting with the largest existing position. Fill one account before moving to another; otherwise use the account with the most cash. TOML order breaks ties: broker declaration order comes first, followed by account declaration order within that broker. Earlier accounts receive higher-risk assets first when the stronger preferences are equal.
5. Divide all remaining cash by the global `[core]` weights. Core tickers use alphabetical order and form the final, lowest-risk tier.
6. Put each core ETF into existing holder accounts first and consume account cash in blocks. This keeps each asset in as few accounts as practical without adding a complex optimizer.

Fixed holdings may already be fractional. New satellite purchases are always whole shares; only core ETFs receive newly calculated fractional shares. The block rule usually limits new fractional positions, but an account that already holds several core ETFs or lies on a weight boundary can receive more than one.

Every final share count is truncated, never rounded, to five decimal places. Reported dollar values are truncated to cents. `Final Account Value` is recalculated from the final share counts and current prices, and account and portfolio percentages use those recalculated asset totals. It can therefore be slightly below the input `money` when a sub-five-decimal residual cannot be invested.

Market requests run concurrently with up to eight workers. Only Yahoo `quoteType == "ETF"` is treated as an ETF; missing, unknown, and every other type fall back to equity.

The Markdown report converts broker and account snake_case names to title case and adds current prices and asset names. ETF rows also show annual expense ratio and category from `funds_data`; equity rows show market capitalization and one-year price change from `fast_info`. Optional metadata failures display `—` and do not abort allocation.

## Development

The project uses flat modules under `src/` and deterministic tests that mock Yahoo Finance.

```bash
uv run ruff format .
uv run ruff check .
uv run ruff format --check .
uv run pytest
uv run python -m compileall -q src tests
```

Licensed under GPL-3.0-or-later. See [LICENSE](LICENSE).
