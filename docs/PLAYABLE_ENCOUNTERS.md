# Playable encounters — first shared content batch

The shared source now includes 54 authored original situations: six each for
Naruto, One Piece, Bleach, Hunter x Hunter, Jujutsu Kaisen, Overgeared,
Solo Max-Level Newbie, Reincarnated as a Slime and Custom World.

This is an expandable local encounter engine, **not a claim that every canon
timeline entry has a complete branching adventure**. The existing three offline
canon interventions (Duy, Arlong Park civilians, Sokyoku retreat) now share the
encounter presentation and support withdrawal preparation and a recorded
follow-up. Main mode retains its existing AI canon scheduler.

## Discovery and causality

Only completed, server-confirmed activities contribute evidence. Two relevant
local actions unlock a matching family; a completed assignment can unlock an
investigation. Reading, quoting, cancelling and partial completion do not count.

| Situation | Evidence | Choices |
| --- | --- | --- |
| Training | Local training or mastery sessions | Verify the exercise, coordinate, or practice independently |
| Exploration | Surveys, preparation, completed arrivals | Verify a local report or prepare a conservative route |
| Work | Shifts, purchases, production, property activity | Reconcile records or return an uncertain order |
| Social | Visits, shared work, recruitment steps, mutual promises | Help host or make a brief visit |
| Community | Completed civic/government/local-story activities | Organize an agreed public rest point or connect helpers |
| Investigation | A completed local assignment | Verify and report the account, or protect a withdrawal in tactical combat |

Old saves can also use structured local property, current companion, completed
journey and assignment records. Unstructured AI narration is not parsed into
invented triggers. A battle or refusal is never forced just to create a plot.

Only accessible mapped settlements in the current location receive these first
packs. Bleach's hostile realms are excluded from settlement stories. Tower
stories stay on the current floor. Generated contacts do not resurrect or
teleport if their campaign record says they are unavailable.

## Gameplay and presentation

The Encounters card sits in the action column (Actions on mobile), with at most
two invitations. The map's local activity view and the offline Encounters
category also provide entry points. Opening a scene or a confirmation is read-only.
The established Chronicle and map are never unmounted or replaced.

Scenes show only observed facts, present choices, durations and the recorded
aftermath. Investigation unlocks its prepared branch. Leaving has no extra
penalty. Closing the window alone does not end the encounter or stop world time.
The first original stories use a compact opening / investigation / resolution
structure; the combat branch uses the existing four-round protection objective.

Outcomes write actual local contact, preparation or shelter state. They do not
invent rare powers, annex territory or claim that reporting an enemy defeats it.
Enemies have authored threat power independent of player stats. Failed tactical
objectives do not receive success benefits. Completed/declined content IDs are
permanently remembered, with a one-day invitation cooldown after an outcome.

## Architecture / extension

- `encounter_content.py`: authored world-specific scenes and outcomes.
- `campaign_encounters.py`: evidence, availability, current stage, observed
  history, local effects and combat callback.
- `living_adventures.py`: existing signed preview/confirm, clock boundaries,
  request receipts, recoverable interruptions and atomic commits.
- `campaign-encounters.js`: read-only presentation and delegation to the existing
  confirmation dialog; no client-authored rewards or stage skipping.
- `adventures.encounters`: private save-owned state. Public views and AI context
  contain only observed scene information, not future branches or counters.

No new POST endpoint or model call is introduced. New story families should
add concrete eligibility and effects with tests; do not provide generic success
prose for unsupported actions. Larger future arcs can extend the state graph,
but must retain receipt idempotency, interrupted-action validation, local NPC
availability and separate combat results from political ownership.
