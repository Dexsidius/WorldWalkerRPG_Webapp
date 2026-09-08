# Simulation reliability fixes and follow-up review

Reviewed against source commit `3feb85a7742a8c9c9174c7e4d85c8917b27c2c19` (v3.64), September 7, 2026.

## Implemented in this patch

- Faction operations now accumulate preparation from elapsed campaign minutes, including saved fractional time. Reprocessing the same interval cannot credit it twice. Removed the duplicate operation updater in the legacy world-clock tick.
- Explicitly concealed operations are excluded from player snapshots, panels, location intervention choices, operation history/news and associated causal audit rows. Simulation records remain intact.
- Military operation preparation at 100% becomes `awaiting_resolution`, without automatic territory capture. The existing GM request receives bounded pending-resolution context requiring established forces, defenses, access and supplies. Unknown targets no longer fall back to the first map location. This does not replace the separate legacy opponent-clock battle resolver; see finding 1 below.
- Assignments revalidate the roster, command authority and member availability before awarding results. Invalid assignments stop without invented returns or rewards, including on old saves.
- Mentor selection distinguishes an empty location from an unspecified list. Dead/unavailable or delegated mentors cannot be used. Resuming and completing training revalidates the mentor.
- `.build-test-data/` is ignored. CI rejects tracked test-runtime files and signing keys. Existing historical Git objects were not rewritten; if a previously committed test key was ever reused on a real server, its owner should rotate it.

Existing saves acquire the new timing ledger automatically. Historical Chronicle text and past rewards/conquests are not retroactively rewritten. Restart/redeploy the updated application to use the fixes; servers and installed executables were not modified.

## Additional findings: proposed fixes, not silently implemented

### 1. Legacy background battles can still award unsupported conquest (high)

`backend/systems.py:resolve_clock_conflicts` is a separate resolver from the operation updater fixed above. Once an explicitly opposed clock reaches its threshold, it rolls rough 1–100 power and may set `controlling_faction`. It does not check fortification, actual garrisons or access, and a missing opponent defaults to power 50. The GM rules in `backend/engine_core.py` explicitly advertise that behavior.

**Player effect:** a background conflict can still transfer a defended location without sufficient military evidence through this older path.

**Fix:** route both legacy opposed clocks and military operations through one outcome resolver. Require established belligerents and defenses; unresolved facts remain pending. Replace the old prompt instruction. Add tests for missing opponents, fortified locations, hidden conflict reporting, and mutual-clock idempotency. This changes older battle rules, so it is listed for the next approved patch rather than silently removed here.

### 2. Property income depends on batching and can repeat (high, reproduced)

`backend/property_economy.py:advance` trusts a passed duration even when the absolute clock has not moved. It also rounds every increment instead of preserving fractions.

**Reproduction:** a test shop earned 1.67 for an hour and 3.34 after processing the same hour twice. Sixty one-minute updates earned 1.80 versus 1.67 for one hour.

**Fix:** use the same absolute-time watermark/remainder pattern as faction operations; accrue in fixed-point units. Newly acquired properties need acquisition timestamps so they cannot earn income for time before ownership. Test retries, pauses, split intervals and save/reload.

### 3. Completed plans eventually block new plans (high for long campaigns, reproduced)

`backend/world_plans.py:advance` only accepts a new plan while the entire dictionary contains fewer than 80 entries. Completed/cancelled entries remain in that dictionary.

**Reproduction:** after seeding 80 completed plans, a valid new player plan was silently rejected.

**Fix:** cap active plans independently; compact finished plans into bounded history while retaining dependency outcomes. Return a diagnostic when a genuine active-plan limit is reached instead of silently dropping the GM command.

### 4. Mastery is awarded from mentions, not confirmed performance (medium, reproduced)

`backend/character_paths.py:record_turn` matches a technique name and words such as “use,” without checking success or negation. `process_organizations` also feeds narrative text into that detector.

**Reproduction:** “You could not use Wind Step; the technique was suppressed” awarded +1 mastery.

**Fix:** award practice and field-use mastery from structured, committed activity/combat outcomes. Give each award a stable event ID. Failed practice can award learning only when that outcome explicitly establishes learning, not simply because the skill was mentioned. Ensure timed sessions are not credited twice.

### 5. Organization controls bypass turn transaction protection (high concurrency risk; code inspection)

`backend/app.py:api_organization_command` mutates state and autosaves directly. Unlike adventure/combat resolution, it does not use `atomic_game_call` for locking, receipts, stale-state guards or rollback.

**Player effect:** a concurrent Advance and organization order could overwrite one another or produce a partial result; this review did not claim to reproduce a real multi-user race.

**Fix:** route organization mutations through the existing transaction wrapper, pass stable request IDs and guards from the client, and test retries/concurrent commands/autosave failures. Apply the same audit to other new mutation endpoints.

### 6. Infirmary upgrades have no connected recovery benefit (medium; code inspection)

`backend/property_economy.py:recovery_multiplier` defines +12% recovery per infirmary level, but has no caller. Timed rest in `backend/living_adventures.py:resolve` only checks adventure shelter.

**Player effect:** spending supplies or currency on an infirmary does not apply its defined bonus during these rest actions.

**Fix:** connect the multiplier to supported local recovery, leave special injuries unaffected, and show the actual bonus before confirmation. Audit other facilities for advertised versus consumed effects.

### 7. New subsystem errors are silently swallowed (medium; code inspection)

`backend/organizations.py:process_organizations` wraps paths, conflicts, reputation, property and assignment progression in separate `except Exception: pass` blocks.

**Player effect:** a subsystem can stop updating while the turn appears successful, with no useful explanation or diagnostic for repair.

**Fix:** log a bounded structured diagnostic with subsystem and turn, preserve the failed subsystem's prior state, and make recovery retry-safe. Do not expose credentials or private GM state. Test malformed legacy values and partial failures.

## Scope and limitations

Validation: the full run completed with 1,282 passing tests and 759 passing subtests, with one stale asset-version assertion caught after the build-ID change. After updating the cache references, the failing test, all 14 new regressions and all 43 browser checks passed together (58/58). All nine worlds passed the structural content audit; JavaScript syntax checks and the tracked-runtime-data guard passed. No failing test remains from these runs.

The review combined the full repository regression suite, desktop/mobile-width browser checks, all-world structural content audit, JavaScript syntax validation, targeted saved-state reproductions, and code inspection of the linked simulation/action paths. Passing the structural audit is not proof of every canon fact or every possible generated narrative. No paid AI campaign was run, no physical phone test was claimed, and no dev/prod deployment was changed. The latest downloadable stable executable is a separate release from source; this patch does not manufacture a new ZIP.
