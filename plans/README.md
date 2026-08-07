# Autobench Implementation Plans

Generated on 2026-07-16. Use the dependency and isolation notes below. Each
executor must read the complete plan, honor its STOP conditions, and update the
status row when finished.

## Execution order and status

| Plan | Title | Priority | Effort | Depends on | Status |
|------|-------|----------|--------|------------|--------|
| 001 | Mirror the Dispatch shared global runtime architecture | P1 | L | - | IN PROGRESS |
| 002 | Add the Maximum Safe Coverage privacy release mode | P0 | L | - | DONE |
| 003 | Scale the Maximum Safe Coverage solver | P0 | L | 002 | BLOCKED: Getnet 2025Q1 Stage 1 exceeds the 15-minute STOP limit |
| 004 | Prove Maximum Safe Coverage with direct HiGHS | P0 | L | 003 | BLOCKED: neither exact strategy proves 2025Q1 Stage 1 in 15 minutes |
| 005 | Replace maximum proof with Verified Safe Coverage | P0 | L | 004 | IN PROGRESS: five local Getnet quarter gates passed; full feed needs the Edge SoW source stages |

Status values: `TODO`, `IN PROGRESS`, `DONE`, `BLOCKED: <reason>`, or
`REJECTED: <reason>`.

## Dependency notes

- Plan 001 is intentionally one end-to-end migration plan. Its internal commit
  sequence keeps the repository valid while moving from the per-user runtime to
  the shared runtime.
- Do not split ownership of this migration across concurrent executors. The
  installer, launcher, deployment profile, production harness, tests, and docs
  encode one operating contract and must evolve together.
- Plan 002 has no functional dependency on Plan 001. Use a separate branch and
  worktree. Do not combine runtime migration and privacy feature changes.
- Plan 003 depends on Plan 002. Use a separate branch and worktree. Do not
  combine solver-scale work with the shared runtime migration.
- Plan 004 starts from the complete Plan 003 branch. It replaces only the
  Maximum Safe Coverage solver transport after exact proof succeeds.
- Plan 005 starts from the Plan 004 branch. It replaces the blocked maximum
  contract with the operator-approved verified-safe contract.

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
