# Scripts

Ingestion and maintenance utilities are added as their owning execution days become active. Scripts must preserve source provenance and never embed credentials.

## D12 private official source intake (CORE #35)

**MERGE SAFETY RESTRICTION (21 Nov 2026):** Live `--output-dir` downloads are **disabled** pending security review of atomic private-vault publication and document-year completeness. The command returns exit 3 without network or writes. Only `--list-only` may be used. Do not bypass the CLI by calling the `run_intake` Python API or activating official source records. The source-intake tests are synthetic/offline. This restriction is separate from Founder Day12 milestone signoff and can be lifted only after independently verified remediation.\n\n`scripts/d12_official_source_intake.py` is an **opt-in operator CLI** for capturing the six public `jeeadv.ac.in` 2026 discovery PDFs into a **private folder outside Git**. It writes an `EDUVIJNA_D12_2026_PRIVATE_INTAKE_UNAPPROVED` JSON receipt only.

- **Not** curator approval, copyright permission, or Day3 `SourceRevision` activation.
- **Never** run in CI or from application routes.

```bash
# List discovery URLs only (no network, no files):
python scripts/d12_official_source_intake.py --list-only

# BLOCKED until security remediation; shown for future operator reference only:
python scripts/d12_official_source_intake.py --output-dir /absolute/private/vault
```

Optional: `pip install pypdf` for structural parse checks (still **not** approval). `--output-dir` must be an **absolute** path outside any Git worktree. Existing PDFs with identical SHA-256 are reused; differing bytes or an existing receipt cause **CONFLICT** (no overwrite). `REQUIRES_HUMAN_REVIEW` / exit code `2` means hash captured only — complete legal/curator steps separately.