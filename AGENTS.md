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

## Commits and Cleanup

All new commit messages must follow Conventional Commits: `type(scope): description`, with an optional scope. Use `feat` for features, `fix` for bug fixes, and appropriate types such as `docs`, `refactor`, `test`, `ci`, or `chore` otherwise. Mark breaking changes with `!` or a `BREAKING CHANGE:` footer. Example: `feat(reporting): add portfolio-level holdings`.

Before committing, run the required checks and inspect the staged diff. Commit only when requested, and push only with explicit authorization. Do not rewrite existing commit history to change message formatting unless separately requested.

When asked to remove all temporary files, finish validation first, then remove regenerable project artifacts including `.venv`, test and lint caches, bytecode, build outputs, and egg-info. Preserve `config.toml` and requested report files. Recreate the environment with `uv sync --locked` when needed.

## Contracts

- Models forbid unknown fields. Broker and account names are lowercase snake_case; tickers are normalized uppercase without duplicates.
- `[satellite]` is non-empty, contains strict integer percentages from 0 through 100, and totals at most 100.
- `[core]` uses strict integer percentages, is non-empty, totals exactly 100, and cannot overlap `[satellite]`. Configured core tickers are treated as ETFs; warn rather than abort when Yahoo metadata disagrees.
- `[substitutions]` maps an existing ETF ticker to one configured target ticker. Existing substitute value counts toward that target, new purchases use only the target, and substitute holders receive existing-holder placement priority. Sources cannot be allocation targets; all declared substitution tickers are treated as ETFs.
- Money and shares are non-negative. An account may set either `leverage_rate`, a strict integer percentage from 0 through 99 based on total portfolio base equity, or `leverage_amount`, a fixed non-negative USD amount. They are mutually exclusive, and at most one account may have positive leverage. `leverage_mode` is `max` by default (actual debt cannot exceed the amount) or `min` (actual debt must reach it). Minimum mode requires a rate or amount. Borrowing appears only as negative cash in that account. Never imply that the configured amount is broker-approved buying power.
- `blocked_assets` is an optional normalized, duplicate-free account ticker list. Existing positions remain and count toward targets, but the account receives no new purchases of those exact tickers.
- New purchases are whole shares. Fixed holdings may be fractional and are truncated to five decimals; reported dollar values are truncated to cents. Derive final account and portfolio values and percentages from final holdings plus cash, not input money.
- Omitted account money is inferred from fixed holdings. If fixed holdings exceed configured money at current prices, use their current value as effective base equity. Never expose the real config in tests or docs.
- Prices use `Decimal(str(value))` and must be finite and positive. Aggregate all price failures before aborting.
- The model assumes every account amount and market price is USD and performs no FX conversion. Keep those limitations and the required `money` snapshot semantics in README rather than repeating them in every report.
- `fetch_market_data()` is the only batch network boundary, uses at most eight threads, and reuses one `fast_info` object per ticker.
- Outside explicitly configured core and substitution assets, only normalized `quoteType == "ETF"` is an ETF. Type failures retain valid prices and fall back to equity; configured ETF type mismatches warn and use the config declaration.
- Reuse history metadata for asset names. ETF expense ratio and category come from `funds_data`; equity market cap and one-year change come from `fast_info`. Optional metadata failures return missing values without aborting.
- Reports use one compact summary line before their tables. The full report includes a portfolio-level section aggregating shares and values by actual ticker, followed by the existing account-level sections, including configured blocked purchases. Portfolio tables omit the account-percentage column; account tables retain it. `--shareable` emits aggregate ETF and equity sections with public market metadata, substitution targets, gross exposure, portfolio percentages, cash percentage, and leverage percentages. It never emits brokers, account names, shares, position values, portfolio equity, borrowing dollars, blocked-purchase settings, or account-level sections.

## Allocation Semantics

1. Calculate the one permitted account's borrowing budget from either its percentage of total portfolio base equity or its fixed dollar amount. Targets use total leveraged portfolio money, but the budget is modeled buying power rather than positive cash or a claim about broker margin eligibility; purchases draw it as negative cash only in that account.
2. Process `[satellite]` first and `[core]` second. Within each table, preserve ticker declaration order; asset order is allocation priority.
3. Satellite targets are percentages of total leveraged portfolio money. Subtract existing target and substitute values across all accounts, never sell surpluses, and buy only whole-share target deficits.
4. After satellite purchases, the core pool is grouped core holdings plus remaining cash and borrowing power. Iteratively freeze overweight core groups and renormalize the remaining weights over the remaining pool until every unfrozen target is reachable without sales; then buy only whole-share target deficits.
5. For each asset, exclude accounts that block new purchases of that exact ticker. Process eligible holders of the target or a configured substitute first in TOML account order, then eligible non-holders in TOML account order. Fill each account's available buying power before continuing to the next account.
6. Preserve deterministic broker declaration order, then account declaration order within each broker. Retain uninvestable or unallocated money as account cash, represent drawn leverage as negative cash, and include it in the report.
   Independently round target purchase counts down; do not sweep combined rounding remainders into extra purchases merely to spend cash. Minimum-borrowing enforcement is the explicit exception.
7. During ordinary allocation, positive minimum leverage rounds the borrower's remaining share capacity up at the current asset boundary, without exceeding requested shares. Once debt reaches the minimum, never reopen the account for later purchases, even existing positions. Clamp remaining buying power to zero so overshoot does not reduce other accounts' core pool. If still below the minimum after ordinary allocation, reassign only new purchases in asset/account order, rounding the final lot up; never move fixed holdings. If necessary, buy extra eligible positive-weight target shares, preferring positions already held, then the smallest change in summed squared dollar target deviations, then overshoot, then declaration order. Include substitutes in deviations and retain original targets. Stop at the minimum; overshoot is less than the last share's price. With no eligible asset, raise a domain error before emitting Markdown. Preserve declaration order rather than sorting assets by price. Reports label minimum/maximum; shareable output exposes only percentages.

Schema or algorithm changes require matching README, private config, and focused-test updates.

## Engineering

Use modern Python 3.14 syntax and `Decimal` for all financial arithmetic. Prefer typed boundaries and immutable slotted value objects. Keep stdout as valid standalone Markdown and stderr for diagnostics. Domain failures return 1 without a traceback; unexpected errors remain visible.

Tests must mock yfinance and remain independent of networks, market hours, ordering, and rate limits. Preserve unrelated working-tree changes. Avoid discretionary code comments, but retain mandatory licensing headers.

Preserve `LICENSE`, `.copywrite.hcl`, and every Python header:

```text
# Copyright Ohyyp 2026
# SPDX-License-Identifier: GPL-3.0-or-later
```
