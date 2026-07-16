# Autobench Implementation Plans

Generated on 2026-07-16. Execute plans in the order below. Each executor must
read the complete plan, honor its STOP conditions, and update the status row
when finished.

## Execution order and status

| Plan | Title | Priority | Effort | Depends on | Status |
|------|-------|----------|--------|------------|--------|
| 001 | Mirror the Dispatch shared global runtime architecture | P1 | L | - | DONE |

Status values: `TODO`, `IN PROGRESS`, `DONE`, `BLOCKED: <reason>`, or
`REJECTED: <reason>`.

## Dependency notes

- Plan 001 is intentionally one end-to-end migration plan. Its internal commit
  sequence keeps the repository valid while moving from the per-user runtime to
  the shared runtime.
- Do not split ownership of this migration across concurrent executors. The
  installer, launcher, deployment profile, production harness, tests, and docs
  encode one operating contract and must evolve together.

## Findings considered and rejected

- Reuse `/ads_storage/autobench/.venv` as one mutable environment: rejected
  because it lacks content-addressed identity, failure atomicity, safe rollback,
  and process pinning to a physical runtime.
- Keep per-user virtual environments as a fallback: rejected because it
  preserves two production architectures and prevents full parity. Existing
  personal environments may remain on disk during migration, but no supported
  launcher may use them.
- Fold shared telemetry ownership into the runtime installer: rejected because
  Autobench already has a hardened, operator-owned telemetry provisioning seam
  in `update.sh`. Runtime installation must not weaken or duplicate it.
