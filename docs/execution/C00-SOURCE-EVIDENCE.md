# C00-06 — Source evidence register

**Rule:** Discovery URLs are not approved evidence. Original bytes, rights, checksums, and human curator approval are non-delegable.

| Obligation | Authority / issue | Required locator | Original bytes + SHA | SourceRevision / curator status | Human owner | Ledger state |
| --- | --- | --- | --- | --- | --- | --- |
| Day 4 official NCF/NCERT/CBSE | Issue [#12](https://github.com/eduvijna-ai/eduvijna-education-intelligence-engine/issues/12) | `D04-NCF-NCERT-CBSE.md` manifest URLs | NOT in public Git (by design) | ACTIVE official PASS **not** independently verified at `8b71aa03`; postmerge CI **42783645367 FAILED** | Founder + curator | SOURCE_PENDING |
| Day 5 Telangana five packages | Issue [#16](https://github.com/eduvijna-ai/eduvijna-education-intelligence-engine/issues/16) | `D05-DS01-TELANGANA-AUTHORITATIVE-SOURCES.md` | NOT in public Git | D5-DS01 DEFERRED_BY_FOUNDER | Founder | SOURCE_PENDING |
| Day 11 NTA 2027 bulletin/syllabus | Issue [#32](https://github.com/eduvijna-ai/eduvijna-education-intelligence-engine/issues/32) | Held PR #31 scope | NOT_VERIFIED | Curator PDF activation blocker per PR #31 | Founder | SOURCE_PENDING |
| Day 12 IIT/JAB 2026 slots (×6) | Issues [#33](https://github.com/eduvijna-ai/eduvijna-education-intelligence-engine/issues/33), [#35](https://github.com/eduvijna-ai/eduvijna-education-intelligence-engine/issues/35) | `D12-SCOPE-MAP.md` | NOT in Git | `official_2026_sources: SOURCE_PENDING`; live CLI DISABLED | Founder | SOURCE_PENDING |
| Day 12 2027 replica availability | Issue #35 | planning docs | NOT_VERIFIED | `official_2027_replica: NOT_VERIFIED` | Founder | NOT_VERIFIED |
| Day 13 CUET/CLAT officials | Issue [#52](https://github.com/eduvijna-ai/eduvijna-education-intelligence-engine/issues/52) | `D13-SCOPE-MAP.md` manifest | URLs only in repo | 2× SOURCE_PENDING rows in scope map | Founder | SOURCE_PENDING |
| Day 14 ICAI / MUR / TGCHE | Issue [#54](https://github.com/eduvijna-ai/eduvijna-education-intelligence-engine/issues/54) | `D14-SCOPE-MAP.md` | NOT_VERIFIED | `official_source_readiness: FALSE` | Founder | SOURCE_PENDING |

## Distinguish discovery vs approved evidence

Official index URLs in Day 4/5/13 specs are **discovery metadata only**. They do not satisfy curator approval, immutable checksum proof, or activation at frozen baseline.

## Prohibited in this audit

No source acquisition, activation, curator impersonation, copyrighted PDF commit, or secrets in repository or this register.