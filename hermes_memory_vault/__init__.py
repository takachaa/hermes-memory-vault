"""Hermes Memory Vault memory provider plugin.

Install this directory as ``$HERMES_HOME/plugins/hermes_memory_vault`` and set
``memory.provider: hermes_memory_vault`` to activate it.
"""

from .provider import HermesMemoryVaultProvider


def register(ctx):
    """Hermes plugin entrypoint used by plugins.memory discovery."""
    ctx.register_memory_provider(HermesMemoryVaultProvider())


__all__ = ["HermesMemoryVaultProvider", "register"]
