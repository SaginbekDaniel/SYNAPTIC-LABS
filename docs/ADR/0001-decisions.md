# Architecture decisions (implemented subset)

Each entry: decision → consequence → exit criterion / rollback.

| ADR | Decision | Consequence | Exit / rollback |
|---|---|---|---|
| 001 | Modular monolith, one Python image for api/worker/migrate | Simple deploy, one lockfile | Split only with measured need |
| 002 | Postgres is the system of record; graph is a derived snapshot | Snapshot reproducible from `max_ingest_seq` + config | Recompute from ledger |
| 003 | Money = integer minor units (`NUMERIC(38,0)`, decimal strings in JSON); IDs = strings | No float drift; IDs > 2^53 survive JS | — |
| 004 | One typed `Evidence`/`Signal` contract for every detector | UI renders any detector generically | — |
| 005 | Priority is triage ranking 0–100, not probability | No "AI confidence" meter in UI | Calibrate only with labelled data |
| 006 | Chronology at the coarsest precision of a pair; equal day = ambiguous | No intraday claims from day data | — |
| 007 | Coverage limitations propagate; subject at boundary ⇒ abstain | Unresolved cases visible as `insufficient_evidence` | Policy list in `risk_policy.yaml` |
| 008 | Immutable transactions and snapshots; deterministic ids | Idempotent publish, late data ⇒ new snapshot | — |
| 009 | Synthetic labels never stored in runtime DB | Detectors cannot leak truth | — |
| 010 | Human decisions only; no enforcement API | Case actions write audit only | — |
| 011 | Batch snapshots per job, no per-event centrality | Bounded cost | Debounced incremental later |
| 012 | One React app, one OpenAPI-generated type file | No API/UI drift | `npm run gen:api` + diff in CI |
| 013 | No third-party code without verified licence | Independent implementation | See REFERENCE_AUDIT.md |
| 014 | No LLM in the evidence pipeline | Demo works offline | Optional narrator later, read-only |
| 015 | Peer statistics as a separate family; counter-evidence caps, never clears | Steady hubs drop to *medium* but stay reviewable | `peer.enabled: false` / policy v1 |
| 016 | Two-way relationships are not consolidation or dispersal | Loan books no longer alert; token repayments are a known evasion route | `exclude_returning_*: false` |
| 017 | Benchmark artifact committed and served read-only | Every displayed metric traces to a commit + config + dataset hashes | Re-run `scripts/run_benchmark.py` |
| 018 | No GNN in the MVP | No independent labels; leakage and explainability risk | Revisit with licensed labelled data |
| 019 | Test/E2E databases are reset by schema drop, not migration downgrade | Downgrade 0002 refuses to discard published analyses | `scripts/reset_disposable_db.py` (refuses non-`_test`/`_e2e` names) |
| 020 | Named accounts with Argon2id + server-side PostgreSQL sessions behind the existing gateway, instead of an external OIDC provider | No browser Basic prompt; per-analyst audit; logout and revocation are real. Local passwords remain the weakest factor (no MFA) | Assessed OIDC/SSO first: it would be safer (MFA, central revocation) but this deployment has no identity provider, and an identity-aware proxy needs a custom domain we do not control. Replace `nexora.auth.service.sign_in` with an OIDC callback when an IdP exists; sessions, CSRF and the route guard stay. Rollback: `NEXORA_GATEWAY_AUTH=basic` puts the shared credential back in front |

