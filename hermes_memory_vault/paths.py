from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .config import VaultConfig, from_mapping


def resolve_paths(data: Mapping[str, Any] | None = None, *, hermes_home: str | Path | None = None) -> dict[str, Path]:
    """Return resolved vault/index/cache paths for compatibility with the design brief."""
    cfg: VaultConfig = from_mapping(data, hermes_home=hermes_home)
    return {
        "vault_path": cfg.vault_path,
        "index_path": cfg.index_path,
        "cache_path": cfg.vault_path / ".memory-vault",
        "locks_path": cfg.vault_path / ".memory-vault" / "locks",
        "migrations_path": cfg.vault_path / ".memory-vault" / "migrations",
    }
