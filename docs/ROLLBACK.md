# Hermes Memory Vault rollback note

Created: 2026-06-04T04:26:04.035855+00:00
Hermes home: /Users/apple/.hermes
Config path: /Users/apple/.hermes/config.yaml
Current memory.provider: ''
Current memory.memory_enabled: True
Current memory.user_profile_enabled: True
Plugin install target for this Hermes build: /Users/apple/.hermes/plugins/hermes_memory_vault
Vault target: /Users/apple/.hermes/memory-vault

## Disable / rollback

```bash
# restore previous provider; empty/None means built-in only
hermes config set memory.provider 
# or disable external memory entirely
hermes memory off

# remove plugin symlink/copy if installed
mv ~/.hermes/plugins/hermes_memory_vault ~/.hermes/plugins/hermes_memory_vault.disabled

# archive vault data if desired, do not delete first
mv ~/.hermes/memory-vault ~/.hermes/memory-vault.disabled
```

Notes:
- This implementation must not modify Hermes core files.
- The Markdown vault is the source of truth.
- SQLite files under `.memory-vault/` are rebuildable index/cache files.
