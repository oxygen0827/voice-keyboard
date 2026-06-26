"""Configuration for the intent training server."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ServerConfig:
    database_url: str = "sqlite:///./intent_training.db"
    upload_token: str = ""

    @classmethod
    def from_env(cls) -> "ServerConfig":
        return cls(
            database_url=os.getenv("INTENT_TRAINING_DATABASE_URL", "sqlite:///./intent_training.db"),
            upload_token=os.getenv("INTENT_TRAINING_UPLOAD_TOKEN", ""),
        )


def sqlite_path_from_url(database_url: str) -> Path:
    if database_url.startswith("sqlite:///"):
        return Path(database_url.removeprefix("sqlite:///")).expanduser()
    if database_url.startswith("sqlite://"):
        return Path(database_url.removeprefix("sqlite://")).expanduser()
    raise ValueError("only sqlite URLs are supported by the built-in store")
