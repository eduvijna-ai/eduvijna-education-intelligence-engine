# Scripts

Ingestion and maintenance utilities are added as their owning execution days become active. Scripts must preserve source provenance and never embed credentials.

## D12 private official source intake (CORE #35)

`scripts/d12_official_source_intake.py` is an **opt-in operator CLI** for capturing the six public `jeeadv.ac.in` 2026 discovery PDFs into a **private folder outside Git**. It writes an `EDUVIJNA_D12_2026_PRIVATE_INTAKE_UNAPPROVED` JSON receipt only.

- **Not** curator approval, copyright permission, or Day3 `SourceRevision` activation.
- **Never** run in CI or from application routes.

```bash
# List discovery URLs only (no network, no files):
python scripts/d12_official_source_intake.py --list-only

# Download to a private absolute path on an access-controlled host:
python scripts/d12_official_source_intake.py --output-dir /absolute/private/vault
```

Optional: `pip install pypdf` for non-authoritative page header warnings. Human legal and visual review remain required.