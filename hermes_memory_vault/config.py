from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
import os


@dataclass(slots=True)
class VaultConfig:
    vault_path: Path
    index_path: Path
    auto_ingest_sessions: bool = True
    prefetch_enabled: bool = True
    prefetch_max_chunks: int = 5
    prefetch_max_chars: int = 6000
    prefetch_preferred_source_kinds: list[str] | None = None
    prefetch_raw_fallback: bool = True
    fts_enabled: bool = True
    embeddings_enabled: bool = False
    embeddings_provider: str = "none"
    embeddings_model: str = "none"
    embeddings_base_url: str = ""
    embeddings_dimensions: int = 0
    queue_enabled: bool = False
    summaries_enabled: bool = False
    summaries_on_session_end: bool = False
    path_scope: str = "default"


def _expand_path(value: str | Path, hermes_home: str | Path | None = None) -> Path:
    text = str(value)
    if hermes_home:
        hh = str(hermes_home)
        text = text.replace("$HERMES_HOME", hh).replace("${HERMES_HOME}", hh)
    return Path(os.path.expandvars(os.path.expanduser(text))).resolve()


def _bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _str_list(value: Any, default: list[str]) -> list[str]:
    if value is None:
        return list(default)
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    if isinstance(value, (list, tuple)):
        return [str(part).strip() for part in value if str(part).strip()]
    return list(default)


def from_mapping(data: Mapping[str, Any] | None, *, hermes_home: str | Path | None = None) -> VaultConfig:
    data = data or {}
    if hermes_home is None:
        hermes_home = Path.home() / ".hermes"
    vault_path = _expand_path(data.get("vault_path", "$HERMES_HOME/memory-vault"), hermes_home)
    index_path = _expand_path(data.get("index_path", str(vault_path / ".memory-vault/index.sqlite")), hermes_home)
    embeddings = data.get("embeddings", {}) if isinstance(data.get("embeddings", {}), dict) else {}
    queue = data.get("queue", {}) if isinstance(data.get("queue", {}), dict) else {}
    summaries = data.get("summaries", {}) if isinstance(data.get("summaries", {}), dict) else {}
    preferred_kinds = _str_list(
        data.get("prefetch_preferred_source_kinds"),
        ["note", "document", "summary_daily", "summary_source", "summary_topic", "summary_global"],
    )
    return VaultConfig(
        vault_path=vault_path,
        index_path=index_path,
        auto_ingest_sessions=_bool(data.get("auto_ingest_sessions"), True),
        prefetch_enabled=_bool(data.get("prefetch_enabled"), True),
        prefetch_max_chunks=max(1, min(_int(data.get("prefetch_max_chunks"), 5), 20)),
        prefetch_max_chars=max(500, min(_int(data.get("prefetch_max_chars"), 6000), 50000)),
        prefetch_preferred_source_kinds=preferred_kinds,
        prefetch_raw_fallback=_bool(data.get("prefetch_raw_fallback"), True),
        fts_enabled=_bool(data.get("fts_enabled"), True),
        embeddings_enabled=_bool(embeddings.get("enabled"), False),
        embeddings_provider=str(embeddings.get("provider") or "none"),
        embeddings_model=str(embeddings.get("model") or "none"),
        embeddings_base_url=str(embeddings.get("base_url") or ""),
        embeddings_dimensions=_int(embeddings.get("dimensions"), 0),
        queue_enabled=_bool(queue.get("enabled"), False),
        summaries_enabled=_bool(summaries.get("enabled"), False),
        summaries_on_session_end=_bool(summaries.get("on_session_end"), False),
        path_scope=str(data.get("path_scope", "default") or "default"),
    )


def load_config(*, hermes_home: str | Path | None = None, explicit: Mapping[str, Any] | None = None) -> VaultConfig:
    if explicit is not None:
        return from_mapping(explicit, hermes_home=hermes_home)
    if hermes_home is None:
        try:
            from hermes_constants import get_hermes_home
            hermes_home = get_hermes_home()
        except Exception:
            hermes_home = Path.home() / ".hermes"
    config_path = Path(hermes_home) / "config.yaml"
    data: dict[str, Any] = {}
    if config_path.exists():
        try:
            import yaml  # type: ignore
            all_config = yaml.safe_load(config_path.read_text(encoding="utf-8-sig")) or {}
            memory = all_config.get("memory", {}) if isinstance(all_config, dict) else {}
            data = memory.get("hermes_memory_vault", {}) or {}
            if not data:
                data = (all_config.get("plugins", {}) or {}).get("hermes_memory_vault", {}) or {}
        except Exception:
            data = {}
    return from_mapping(data, hermes_home=hermes_home)
