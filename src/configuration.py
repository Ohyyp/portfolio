# Copyright Ohyyp 2026
# SPDX-License-Identifier: GPL-3.0-or-later

import re
import tomllib
from collections.abc import Mapping
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

ZERO = Decimal("0")
ONE = Decimal("1")
HUNDRED = Decimal("100")
PERCENT_MAX = 100
SNAKE_CASE = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")

NonNegativeDecimal = Annotated[Decimal, Field(ge=ZERO)]
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
    leverage_rate: LeveragePercentage = 0

    @field_validator("fixed_assets")
    @classmethod
    def normalize_fixed_assets(
        cls, assets: dict[str, NonNegativeDecimal]
    ) -> dict[str, NonNegativeDecimal]:
        return normalize_ticker_mapping(assets)


class Config(StrictModel):
    broker: dict[str, dict[str, AccountConfig]]
    core: dict[str, Percentage]
    satellite: dict[str, Percentage]

    @field_validator("satellite")
    @classmethod
    def normalize_satellite(
        cls, satellite: dict[str, Percentage]
    ) -> dict[str, Percentage]:
        if not satellite:
            raise ValueError("satellite cannot be empty")
        return normalize_ticker_mapping(satellite)

    @field_validator("core")
    @classmethod
    def normalize_core(cls, core: dict[str, Percentage]) -> dict[str, Percentage]:
        if not core:
            raise ValueError("core cannot be empty")
        return normalize_ticker_mapping(core)

    @field_validator("broker")
    @classmethod
    def validate_brokers(
        cls, brokers: dict[str, dict[str, AccountConfig]]
    ) -> dict[str, dict[str, AccountConfig]]:
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
    def validate_percentages(self) -> Self:
        satellite_total = sum(self.satellite.values())
        if satellite_total > PERCENT_MAX:
            raise ValueError(
                f"satellite total cannot exceed 100%, got {satellite_total}%"
            )
        core_total = sum(self.core.values())
        if core_total != PERCENT_MAX:
            raise ValueError(f"core total must equal 100%, got {core_total}%")
        overlap = self.satellite.keys() & self.core.keys()
        if overlap:
            symbols = ", ".join(sorted(overlap))
            raise ValueError(f"satellite and core tickers must be distinct: {symbols}")
        return self


def get_all_tickers(config: Config) -> set[str]:
    tickers = {
        ticker for ticker, percentage in config.satellite.items() if percentage > 0
    }
    tickers.update(
        ticker for ticker, percentage in config.core.items() if percentage > 0
    )
    for accounts in config.broker.values():
        for account in accounts.values():
            tickers.update(
                ticker
                for ticker, shares in account.fixed_assets.items()
                if shares > ZERO
            )
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
