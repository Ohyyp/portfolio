# Copyright Ohyyp 2026
# SPDX-License-Identifier: GPL-3.0-or-later

import re
import tomllib
from collections.abc import Mapping
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

ZERO = Decimal("0")
HUNDRED = Decimal("100")
PERCENT_MAX = 100
SNAKE_CASE = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")

NonNegativeDecimal = Annotated[Decimal, Field(ge=ZERO, allow_inf_nan=False)]
Percentage = Annotated[int, Field(strict=True, ge=0, le=PERCENT_MAX)]
LeveragePercentage = Annotated[int, Field(strict=True, ge=0, lt=PERCENT_MAX)]


class ConfigError(Exception):
    pass


def normalize_ticker(ticker: str) -> str:
    normalized = ticker.strip().upper()
    if not normalized:
        raise ValueError("ticker symbols cannot be empty")
    return normalized


def normalize_ticker_mapping[T](values: Mapping[str, T]) -> dict[str, T]:
    normalized: dict[str, T] = {}
    for ticker, value in values.items():
        symbol = normalize_ticker(ticker)
        if symbol in normalized:
            raise ValueError(f"duplicate ticker after normalization: {symbol}")
        normalized[symbol] = value
    return normalized


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AccountConfig(StrictModel):
    money: NonNegativeDecimal | None = None
    fixed_assets: dict[str, NonNegativeDecimal] = Field(default_factory=dict)
    leverage_rate: LeveragePercentage | None = None
    leverage_amount: NonNegativeDecimal | None = None
    leverage_mode: Literal["max", "min"] = "max"
    blocked_assets: list[str] = Field(default_factory=list)

    @field_validator("fixed_assets")
    @classmethod
    def normalize_fixed_assets(cls, assets: dict[str, NonNegativeDecimal]) -> dict[str, NonNegativeDecimal]:
        return normalize_ticker_mapping(assets)

    @field_validator("blocked_assets")
    @classmethod
    def normalize_blocked_assets(cls, assets: list[str]) -> list[str]:
        normalized = [normalize_ticker(ticker) for ticker in assets]
        if len(normalized) != len(set(normalized)):
            raise ValueError("blocked_assets contains duplicate tickers after normalization")
        return normalized

    @model_validator(mode="after")
    def validate_leverage(self) -> Self:
        if self.leverage_rate is not None and self.leverage_amount is not None:
            raise ValueError("leverage_rate and leverage_amount are mutually exclusive")
        if self.leverage_mode == "min" and self.leverage_rate is None and self.leverage_amount is None:
            raise ValueError("leverage_mode=min requires leverage_rate or leverage_amount")
        return self


class Config(StrictModel):
    broker: dict[str, dict[str, AccountConfig]]
    core: dict[str, Percentage]
    satellite: dict[str, Percentage]
    substitutions: dict[str, str] = Field(default_factory=dict)

    @field_validator("satellite")
    @classmethod
    def normalize_satellite(cls, satellite: dict[str, Percentage]) -> dict[str, Percentage]:
        if not satellite:
            raise ValueError("satellite cannot be empty")
        return normalize_ticker_mapping(satellite)

    @field_validator("core")
    @classmethod
    def normalize_core(cls, core: dict[str, Percentage]) -> dict[str, Percentage]:
        if not core:
            raise ValueError("core cannot be empty")
        return normalize_ticker_mapping(core)

    @field_validator("substitutions")
    @classmethod
    def normalize_substitutions(cls, substitutions: dict[str, str]) -> dict[str, str]:
        normalized: dict[str, str] = {}
        for substitute, target in substitutions.items():
            symbol = normalize_ticker(substitute)
            if symbol in normalized:
                raise ValueError(f"duplicate ticker after normalization: {symbol}")
            normalized[symbol] = normalize_ticker(target)
        return normalized

    @field_validator("broker")
    @classmethod
    def validate_brokers(cls, brokers: dict[str, dict[str, AccountConfig]]) -> dict[str, dict[str, AccountConfig]]:
        if not brokers:
            raise ValueError("broker cannot be empty")
        for broker_name, accounts in brokers.items():
            if not SNAKE_CASE.fullmatch(broker_name):
                raise ValueError(f"broker name must be snake_case: {broker_name}")
            if not accounts:
                raise ValueError(f"broker has no accounts: {broker_name}")
            for account_name in accounts:
                if not SNAKE_CASE.fullmatch(account_name):
                    raise ValueError(f"account name must be snake_case: {account_name}")
        return brokers

    @model_validator(mode="after")
    def validate_portfolio(self) -> Self:
        satellite_total = sum(self.satellite.values())
        if satellite_total > PERCENT_MAX:
            raise ValueError(f"satellite total cannot exceed 100%, got {satellite_total}%")
        core_total = sum(self.core.values())
        if core_total != PERCENT_MAX:
            raise ValueError(f"core total must equal 100%, got {core_total}%")
        overlap = self.satellite.keys() & self.core.keys()
        if overlap:
            symbols = ", ".join(sorted(overlap))
            raise ValueError(f"satellite and core tickers must be distinct: {symbols}")
        allocation_tickers = self.satellite.keys() | self.core.keys()
        invalid_targets = set(self.substitutions.values()) - allocation_tickers
        if invalid_targets:
            symbols = ", ".join(sorted(invalid_targets))
            raise ValueError(f"substitution targets must be configured allocation tickers: {symbols}")
        conflicting_sources = self.substitutions.keys() & allocation_tickers
        if conflicting_sources:
            symbols = ", ".join(sorted(conflicting_sources))
            raise ValueError(f"substitution sources cannot also be allocation targets: {symbols}")
        leveraged_accounts = [
            f"{broker_name}.{account_name}"
            for broker_name, accounts in self.broker.items()
            for account_name, account in accounts.items()
            if (account.leverage_rate or 0) > 0 or (account.leverage_amount or ZERO) > ZERO
        ]
        if len(leveraged_accounts) > 1:
            accounts = ", ".join(leveraged_accounts)
            raise ValueError(f"leverage can be configured on at most one account: {accounts}")
        return self


def get_all_tickers(config: Config) -> set[str]:
    tickers = {ticker for ticker, percentage in config.satellite.items() if percentage > 0}
    tickers.update(ticker for ticker, percentage in config.core.items() if percentage > 0)
    for accounts in config.broker.values():
        for account in accounts.values():
            tickers.update(ticker for ticker, shares in account.fixed_assets.items() if shares > ZERO)
    return tickers


def load_config(path: Path) -> Config:
    try:
        with path.open("rb") as config_file:
            data = tomllib.load(config_file)
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ConfigError(f"Unable to read config {path}: {error}") from error

    try:
        return Config.model_validate(data)
    except ValidationError as error:
        raise ConfigError(f"Invalid config {path}:\n{error}") from error
