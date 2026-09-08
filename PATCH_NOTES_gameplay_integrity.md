# Gameplay integrity hotfix

Build: `3.64.0-gameplay-integrity-3`

## Player-visible changes

- Both faction military resolvers now require established battle evidence. Unknown opposition, defenses, access or supply leave the operation pending, rather than giving it default strength or transferring land by a random roll. Local victory does not erase an entire faction or kill its leader.
- Passive property income uses campaign timestamps and exact fractional carry. Splitting time, retrying a tick or reloading cannot duplicate proceeds; newly acquired holdings cannot earn for time before acquisition.
- Completed plans move into history. Active-plan capacity is independent of completed plans, and compact outcomes retain dependency truth. Reaching the real active-plan limit creates a diagnostic instead of silently discarding an order.
- Skill mentions, failed uses and deferred plans no longer award mastery. Confirmed successful uses and actual training segments do, with duplicate-award protection. Interrupted training receives only the progress and energy cost of its completed segment.
- Infirmaries now improve ordinary local rest recovery by 12% per level. The recovery amount, including shelter bonuses, appears in the existing confirmation description. Special injuries are not cured by this bonus.
- Organization commands use campaign locking, stale-state guards, transaction rollback and persistent retry receipts. Repeated clicks after an unreadable response check the original receipt rather than creating another request.
- Local post-turn subsystems commit independently from isolated copies. A failure preserves that subsystem's prior state and records a bounded, non-sensitive diagnostic. Successful ticks do not repeat on retry. Diagnostics shows affected systems and their status.

## Verification

- 1,256 repository tests passed; 759 subtests passed.
- 44 desktop/mobile-width browser checks passed, including the new repeated-click recovery test.
- All nine built-in worlds passed the structural content audit.
- JavaScript syntax checks, tracked-runtime-data check and Git whitespace check passed.

Existing saves remain supported. Past story entries, payouts and conquests are not retroactively rewritten. No paid model playthrough or physical-phone certification is claimed. This is a source update, not a newly built Windows ZIP; dev/prod deployment remains owner-managed.
