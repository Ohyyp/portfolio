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
- Money and shares are non-negative. `leverage_rate` is a strict integer percentage from 0 through 99 and may be non-zero in at most one account. It sets that account's modeled borrowing budget based on total portfolio base equity; actual borrowing appears as negative cash and cannot exceed the budget. Never imply that this budget is broker-approved buying power.
- New purchases are whole shares. Fixed holdings may be fractional and are truncated to five decimals; reported dollar values are truncated to cents. Derive final account and portfolio values and percentages from final holdings plus cash, not input money.
- Omitted account money is inferred from fixed holdings. If fixed holdings exceed configured money at current prices, use their current value as effective base equity. Never expose the real config in tests or docs.
- Prices use `Decimal(str(value))` and must be finite and positive. Aggregate all price failures before aborting.
- The model assumes every account amount and market price is USD and performs no FX conversion. Keep those limitations and the required `money` snapshot semantics in README rather than repeating them in every report.
- `fetch_market_data()` is the only batch network boundary, uses at most eight threads, and reuses one `fast_info` object per ticker.
- Outside explicitly configured core and substitution assets, only normalized `quoteType == "ETF"` is an ETF. Type failures retain valid prices and fall back to equity; configured ETF type mismatches warn and use the config declaration.
- Reuse history metadata for asset names. ETF expense ratio and category come from `funds_data`; equity market cap and one-year change come from `fast_info`. Optional metadata failures return missing values without aborting.
- Reports use one compact summary line before their tables. The full report includes a portfolio-level section aggregating shares and values by actual ticker, followed by the existing account-level sections. Portfolio tables omit the account-percentage column; account tables retain it. `--shareable` emits aggregate ETF and equity sections with public market metadata, substitution targets, gross exposure, portfolio percentages, cash percentage, and leverage percentages. It never emits brokers, account names, shares, position values, portfolio equity, borrowing dollars, or account-level sections.

## Allocation Semantics

1. Calculate the one permitted account's configured borrowing budget from total portfolio base equity. Targets use total leveraged portfolio money, but the budget is modeled buying power rather than positive cash or a claim about broker margin eligibility; purchases draw it as negative cash only in that account.
2. Process `[satellite]` first and `[core]` second. Within each table, preserve ticker declaration order; asset order is allocation priority.
3. Satellite targets are percentages of total leveraged portfolio money. Subtract existing target and substitute values across all accounts, never sell surpluses, and buy only whole-share target deficits.
4. After satellite purchases, the core pool is grouped core holdings plus remaining cash and borrowing power. Iteratively freeze overweight core groups and renormalize the remaining weights over the remaining pool until every unfrozen target is reachable without sales; then buy only whole-share target deficits.
5. For each asset, process holders of the target or a configured substitute first in TOML account order, then non-holders in TOML account order. Fill each account's available buying power before continuing to the next account.
6. Preserve deterministic broker declaration order, then account declaration order within each broker. Retain uninvestable or unallocated money as account cash, represent drawn leverage as negative cash, and include it in the report.

Schema or algorithm changes require matching README, private config, and focused-test updates.

## Engineering

Use modern Python 3.14 syntax and `Decimal` for all financial arithmetic. Prefer typed boundaries and immutable slotted value objects. Keep stdout as valid standalone Markdown and stderr for diagnostics. Domain failures return 1 without a traceback; unexpected errors remain visible.

Tests must mock yfinance and remain independent of networks, market hours, ordering, and rate limits. Preserve unrelated working-tree changes. Avoid discretionary code comments, but retain mandatory licensing headers.

Preserve `LICENSE`, `.copywrite.hcl`, and every Python header:

```text
# Copyright Ohyyp 2026
# SPDX-License-Identifier: GPL-3.0-or-later
```
