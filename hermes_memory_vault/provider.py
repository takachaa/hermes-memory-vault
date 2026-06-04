from __future__ import annotations

from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
import json
import logging

try:
    from agent.memory_provider import MemoryProvider  # type: ignore
except Exception:  # pragma: no cover - only for standalone unit tests outside Hermes
    class MemoryProvider:  # type: ignore
        @property
        def name(self) -> str:
            raise NotImplementedError

from .config import VaultConfig, load_config
from .db import ensure_database
from .health import run_health
from .ingest import ingest_turn
from .queue import enqueue_job
from .summaries import create_daily_summary
from .retrieval import fetch_chunks, search_chunks
from .tools import handle_tool, schemas

logger = logging.getLogger(__name__)


class HermesMemoryVaultProvider(MemoryProvider):
    def __init__(self, config: VaultConfig | None = None):
        self._explicit_config = config
        self._config: VaultConfig | None = config
        self._session_id = ""
        self._platform = ""
        self._turn_seq = 0
        self._source_ref = ""

    @property
    def name(self) -> str:
        return "hermes_memory_vault"

    def is_available(self) -> bool:
        return True

    def get_config_schema(self):
        return [
            {"key": "vault_path", "description": "Markdown vault path", "default": "$HERMES_HOME/memory-vault"},
            {"key": "index_path", "description": "SQLite FTS index path", "default": "$HERMES_HOME/memory-vault/.memory-vault/index.sqlite"},
            {"key": "prefetch_enabled", "description": "Inject FTS recall before each turn", "default": "true", "choices": ["true", "false"]},
            {"key": "prefetch_max_chunks", "description": "Maximum chunks to prefetch", "default": "5"},
            {"key": "prefetch_max_chars", "description": "Maximum prefetch characters", "default": "6000"},
        ]

    def initialize(self, session_id: str, **kwargs) -> None:
        hermes_home = kwargs.get("hermes_home")
        self._config = self._explicit_config or load_config(hermes_home=hermes_home)
        self._session_id = session_id or ""
        self._platform = str(kwargs.get("platform") or "")
        user_id = str(kwargs.get("user_id") or kwargs.get("user_id_alt") or "")
        self._source_ref = f"{self._platform}:{user_id}" if user_id else self._platform
        run_health(self._config, deep=False)
        ensure_database(self._config.index_path).close()

    def system_prompt_block(self) -> str:
        return (
            "# Hermes Memory Vault\n"
            "Local Markdown-backed memory provider is active. Markdown files are the source of truth; "
            "SQLite is a rebuildable FTS index/cache. Use memory_vault_search and memory_vault_fetch "
            "for explicit deep recall when needed."
        )

    def prefetch(self, query: str, *, session_id: str = "") -> str:
        cfg = self._require_config()
        if not cfg.prefetch_enabled or not query.strip():
            return ""
        conn = ensure_database(cfg.index_path)
        try:
            hits = search_chunks(conn, query, vault_path=cfg.vault_path, limit=cfg.prefetch_max_chunks)
            if not hits:
                return ""
            ids = [h["id"] for h in hits]
            chunks = fetch_chunks(conn, ids, vault_path=cfg.vault_path, max_chars_per_chunk=1200)
        finally:
            conn.close()
        lines = ["## Memory Vault Context", "", "Relevant past notes from the local memory vault:", ""]
        used = 0
        for i, chunk in enumerate(chunks, 1):
            body = chunk["body"].strip()
            snippet = body[:1200]
            item = f"{i}. [{chunk['source_kind']}] {chunk['path']}\n   Snippet: {snippet}"
            if used + len(item) > cfg.prefetch_max_chars:
                break
            lines.append(item)
            used += len(item)
        lines.append("")
        lines.append("Use this only as contextual memory; the current user request has priority.")
        return "\n".join(lines).strip()

    def sync_turn(
        self,
        user_content: str,
        assistant_content: str,
        *,
        session_id: str = "",
        messages: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        cfg = self._require_config()
        if not cfg.auto_ingest_sessions:
            return
        sid = session_id or self._session_id
        self._turn_seq += 1
        ingest_turn(
            cfg,
            user_content,
            assistant_content,
            session_id=sid,
            seq_in_source=self._turn_seq,
            source_ref=self._source_ref,
        )

    def on_session_switch(self, new_session_id: str, *, reset: bool = False, rewound: bool = False, **kwargs) -> None:
        self._session_id = new_session_id or self._session_id
        if reset or rewound:
            self._turn_seq = 0

    def on_session_end(self, messages: List[Dict[str, Any]]) -> None:
        cfg = self._require_config()
        if not (cfg.summaries_enabled and cfg.summaries_on_session_end):
            return
        date = self._summary_date_from_messages(messages)
        if cfg.queue_enabled:
            enqueue_job(cfg, "summary_daily", {"date": date, "session_id": self._session_id})
        else:
            create_daily_summary(cfg, date)

    @staticmethod
    def _summary_date_from_messages(messages: List[Dict[str, Any]]) -> str:
        for message in reversed(messages or []):
            ts = message.get("timestamp_ms") or message.get("created_at_ms")
            if ts is not None:
                try:
                    return datetime.fromtimestamp(int(ts) / 1000, tz=timezone.utc).date().isoformat()
                except Exception:
                    pass
            iso = message.get("timestamp") or message.get("created_at")
            if isinstance(iso, str) and iso.strip():
                try:
                    text = iso.strip()
                    if text.endswith("Z"):
                        text = text[:-1] + "+00:00"
                    dt = datetime.fromisoformat(text)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    return dt.astimezone(timezone.utc).date().isoformat()
                except Exception:
                    pass
        return datetime.now(timezone.utc).date().isoformat()

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        return schemas()

    def handle_tool_call(self, tool_name: str, args: Dict[str, Any], **kwargs) -> str:
        return handle_tool(self._require_config(), tool_name, args or {})

    def shutdown(self) -> None:
        return None

    def _require_config(self) -> VaultConfig:
        if self._config is None:
            self._config = load_config()
        return self._config
