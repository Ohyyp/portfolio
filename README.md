# Portfolio Allocator

Portfolio Allocator is a Python 3.14 CLI for planning a core–satellite portfolio across brokerage accounts. It reads a private TOML snapshot, fetches Yahoo Finance prices and instrument types, and prints proposed holdings. It never connects to a broker or places trades.

## Setup and Usage

```bash
uv sync --locked
uv run portfolio-allocator config.toml
uv run portfolio-allocator config.toml > report.md
uv run portfolio-allocator --shareable config.toml > allocation.md
```

Progress and errors go to stderr; stdout is a complete Markdown report that can be redirected directly to a file. Configuration and required market-data failures return status 1.

## Configuration

`config.toml`, `report.md`, and `allocation.md` are Git-ignored because they contain private portfolio information. Broker and account names use lowercase snake_case; tickers are normalized to uppercase.

```toml
[satellite]
NVDA = 15
SCHG = 10

[core]
SPYM = 40
QNDX = 60

[substitutions]
IVV = "SPYM"
QQQM = "QNDX"

[broker.example_broker.taxable]
leverage_rate = 3
money = 100000

[broker.example_broker.taxable.fixed_assets]
NVDA = 100
QQQM = 25.5
```

`[satellite]` contains satellite targets as percentages of total leveraged portfolio money. It must be non-empty, each value must be an integer from 0 through 100, and the sum cannot exceed 100. Existing holdings count toward these targets; the allocator only buys whole-share deficits and never sells. Tickers are processed in declaration order, so the first entry has the highest purchase priority.

`[core]` is a dynamic ordered mapping of broad-market ETF weights; it is not limited to any built-in ticker list. Its integer weights must total exactly 100, and its tickers cannot also appear in `[satellite]`. A ticker listed in `[core]` is an explicit declaration that the asset is an ETF. If Yahoo's instrument type disagrees, the CLI prints a warning and continues to treat the configured core asset as an ETF because Yahoo metadata can lag new launches and ticker changes.

`[substitutions]` defines directional ETF equivalence for existing holdings. Each key is an older substitute holding and each value is the configured allocation target it counts toward. For example, `QQQM = "QNDX"` means existing QQQM and QNDX values both satisfy the QNDX target, while every new share is still QNDX. A substitute also makes its account an existing holder for placement priority. Targets must appear in `[satellite]` or `[core]`; a substitute cannot itself be an allocation target. Tickers declared on either side are treated as ETFs, with a warning if Yahoo disagrees.

After satellite purchases, the allocator treats existing configured core and substitute holdings plus remaining cash and unused borrowing power as one core pool. If an existing core group is above its target, the allocator freezes it instead of selling it, removes its current value and weight from the calculation, and redistributes the remaining pool across the remaining core weights. This repeats if redistribution exposes another overweight group. The final positive deficits therefore fit within available buying power before whole-share truncation; declaration order controls execution, not which core target is sacrificed.

Each account supports:

- `money`: optional non-negative account equity, not additional cash. If omitted, equity is inferred from fixed holdings. If current fixed holdings are worth more than this snapshot, their current value becomes the effective base equity and the CLI emits a warning.
- `leverage_rate`: optional integer percentage from 0 through 99. It may be non-zero in at most one account. It sets that account's borrowing budget equal to this percentage of total base equity across every account. Borrowing is drawn only when purchases take the account below zero cash, so the actual debt may be lower than the budget because purchases use whole shares. For example, `3` permits the plan to borrow up to 3% of the whole portfolio in that account.
- `fixed_assets`: optional current share counts. Decimal shares are accepted.

All configured percentages use TOML integers; decimal percentage literals are rejected. Unknown fields and invalid values are rejected. Required prices must be finite and positive, and a price failure aborts the complete allocation.

## Allocation Rules

1. Value every account before leverage. If an account omits `money`, infer its base equity from its fixed holdings; if fixed holdings exceed configured money, use their current value rather than creating negative cash.
2. Calculate the one permitted account's configured borrowing budget from total portfolio base equity. The budget increases that account's modeled buying power without appearing as positive cash; purchases beyond its cash create a negative cash balance up to the budget.
3. Aggregate existing holdings and their configured substitutes across all accounts, then calculate satellite deficits against total leveraged portfolio targets. Process satellite tickers exactly in `[satellite]` declaration order and only buy the target ticker.
4. After satellite purchases, form the core pool from current core groups plus remaining account cash and unused borrowing power. Freeze overweight core groups, repeatedly renormalize the remaining weights over the remaining value, deduct grouped existing holdings from the reachable targets, and process positive deficits exactly in `[core]` declaration order.
5. For each ticker, first visit accounts that already hold either the target or one of its substitutes, preserving their TOML order. Then visit all other accounts in TOML order. Broker declaration order comes first, followed by account declaration order within each broker. Buy as many whole shares as the current account can hold before moving on.
6. Never sell a surplus position and never create a fractional purchase. Uninvested cash remains in its account; borrowing appears as negative cash in the leveraged account. Both appear in the report.

Fixed holdings may already be fractional. They are preserved to five decimal places, and an integer purchase added to a fractional fixed position remains fractional only because of that original fixed holding. Every newly purchased satellite or core position uses whole shares.

Reported dollar values are truncated, never rounded, to cents. Each displayed amount is truncated independently, so displayed line items, account totals, and the portfolio total can differ by a few cents even though the underlying `Decimal` values reconcile exactly. Portfolio and account `Equity` are recalculated from final holdings plus cash, including a leveraged account's debit balance. `Gross exposure` excludes cash and debt, so it can exceed 100% of equity while cash is negative.

Market requests run concurrently with up to eight workers. Outside `[core]` and `[substitutions]`, only Yahoo `quoteType == "ETF"` is treated as an ETF; missing, unknown, and every other type fall back to equity. Configured core and substitution tickers use the explicit ETF declarations described above. Instrument type does not change allocation order; the TOML order does.

The full Markdown report shows a `Portfolio` section first, followed by each account in configuration order. Portfolio tables aggregate shares and values by actual ticker across all accounts and show portfolio percentages; account tables retain both account and portfolio percentages. Substitutes remain separate ticker rows with their `Counts Toward` target, so shares of different ETFs are never combined. Each level has a compact equity and cash summary. The portfolio summary also shows gross exposure, and the borrowing account shows its budget and actual debt. Broker and account snake_case names are converted to title case. ETF rows include current prices, asset names, expense ratios and categories from `funds_data`, and substitution targets from configuration; equity rows include prices, asset names, market capitalization, and one-year price change from `fast_info`. Optional metadata failures display `—` and do not abort allocation.

For a shareable report, use `--shareable`. This mode aggregates each ticker across the portfolio and keeps the useful public metadata from the full report: asset names, current prices, ETF/equity sections, substitution targets, expense ratios, categories, market capitalizations, one-year changes, gross exposure, portfolio percentages, net cash percentage, and borrowing percentages. It omits brokers, account names, share counts, position values, portfolio equity, borrowing dollars, and all account-level sections. Public prices and market capitalizations remain because they do not directly disclose position size. The ticker mix and percentages can still be sensitive, so `allocation.md` remains Git-ignored. Diagnostics stay on stderr, allowing stdout to be redirected into standalone Markdown.

`leverage_rate` is a planning budget, not a representation of actual broker buying power or regulatory approval. The allocator does not check whether an account or security is margin-eligible, model initial or maintenance requirements, apply broker house rules, accrue margin interest, simulate margin calls, or include taxes, commissions, bid–ask spreads, slippage, or price movement between planning and execution. Yahoo Finance values can be delayed or incomplete. The allocator assumes that every account amount and market price is in USD and performs no foreign-exchange conversion. `money` must be a current account-equity snapshot consistent with the configured holdings; otherwise the derived cash balance will not match the broker. Confirm the proposed trades and debit balance against the current brokerage statement before acting.

## Development

The project uses flat modules under `src/` and deterministic tests that mock Yahoo Finance.

```bash
uv run ruff format .
uv run ruff check .
uv run ruff format --check .
uv run pytest
uv run python -m compileall -q src tests
```

All new commit messages follow Conventional Commits: `type(scope): description` (scope optional), for example `feat(reporting): add portfolio-level holdings`. Use `!` or a `BREAKING CHANGE:` footer for breaking changes. See [AGENTS.md](AGENTS.md) for the commit and cleanup workflow.

A full cleanup includes the regenerable `.venv` directory along with test caches, bytecode, and build artifacts; keep the private configuration and requested reports. Run `uv sync --locked` to recreate the development environment.

Licensed under GPL-3.0-or-later. See [LICENSE](LICENSE).
