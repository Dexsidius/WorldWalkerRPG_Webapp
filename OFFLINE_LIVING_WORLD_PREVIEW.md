# Offline living world — first playable release

This paired preview ships the first playable release of the local engine.
It is **not full canon coverage or a completed autonomous political campaign**.
The broader requested update remains incomplete; the content below is the
tested release scope, not a claim that every planned milestone is finished.

## Implemented in this pass

- Offline-only appointment ownership before the legacy canon backstop.
- One authored intervention per world: Duy's retreat, Arlong Park civilian
  protection, and covering Rukia/Renji's retreat at Sokyoku Hill.
- Existing timeline IDs and dates preserved. A two-hour intervention window
  and one-day preparation/travel window are gameplay approximations.
- Timed activities at the event location stop at the intervention window.
- Existing signed activity previews, atomic resolution and request receipts.
- Protection objectives use the shared tactical battle. A failed/abandoned
  attempt does not immediately kill somebody before the scheduled deadline.
- Completed interventions cannot be overwritten by the normal canon backstop.
- Local event markers are selectable. Distant routes require both companion
  membership and a confirmed tracking report; viewing the calendar is not a
  tracking report. Legal graph routes are used; unavailable routes stay hidden.
- User-selectable instant/animated movement. Touch devices default to instant;
  reduced-motion preference overrides animation. Neither stops simulation.
- Civic support among three world-specific constituencies; 8-hour activities,
  server-owned costs, weekly repetition limit, support capped at 60.
- Local advisory petitions reviewed after seven days. A mandate is not a
  country, military command, or new national office.
- Offline military victories with the existing required evidence create a
  stable one-hex occupation claim, not national annexation. Replays cannot
  multiply land. Government formation requires separate support and a charter.
- Council/protectorate charters establish civil administration and public
  accounts in that holding only. These are institutional state, not yet a
  complete tax/policy/elections simulation.
- Existing recorded governments make weekly budget decisions for services,
  local order and reserves. These abstract civilian budget units are not
  currency, troops, canon power estimates or automatic territorial expansion.
  Controlled local budgets can prioritize services or security. Only local
  reports are disclosed; private government bookkeeping is excluded from state.
- Offline military planning: muster present organization members with explicit
  power records, survey established garrisons, buy supplies and commit local
  available forces through the shared evidence-based resolver. Unknown defense
  or force data does not become fabricated military strength. Committed forces
  cannot be reused immediately or teleported to a different location.
- Organization members with an explicit route report can use event tracking.
  Reports can be obtained from an actual present participant before departure.
- Canon rescue and aftermath are separate. Protecting villagers does not itself
  defeat Arlong; later liberation changes only recorded Arlong-controlled places,
  without overwriting another campaign owner. Cancelled events cannot resurrect
  dead participants. Duy's default death also synchronizes companion status.
- Repeat captures retain an established local government; malformed optional
  politics dictionaries are repaired when written. Global animation settings
  now also disable map-piece motion.

## Important limitations / next milestones

1. Author additional event branches, prerequisites and canon-specific combat
   rosters. Current encounter strengths are fixed **gameplay estimates** and
   use shared attack templates; no claim that these are precise canon stats.
2. Extend weekly civic budgets into succession, negotiations, competing
   coalitions and independently selected strategic military goals.
3. Author additional world garrison/force records and withdrawal/redeployment
   flows. Military planning intentionally remains unavailable where campaign
   evidence is missing; a declined or failed operation does not invent casualties.
4. Extend tracked travel to organization parties, route reports and player
   interception. Current map enrollment is conservative and does not reveal
   every NPC or simulate every named character's itinerary.
5. Expand canonical territorial outcomes beyond the initial Arlong liberation
   adapter. Protecting civilians is not receiving their territory.
6. Add event-specific objectives and allied participants to tactical boards.
   The initial encounters currently reuse the generic protection objective.
7. Long-skip intervention at intermediate travel waypoints, save/load replay
   tests across complete campaigns, and representative low-end phone profiling.
8. Continue expanding this explicitly limited paired preview. Main and offline
   packages must always pass validation together before publication.

## User decisions preserved

- Capture first; establish government afterward.
- Naruto countries and hidden-village authority remain distinct.
- One Piece actual control, kingdom and protector are separate concepts.
- Canon outcomes are defaults, not destiny; prerequisites may change.
- Mobile can disable visual motion, never the world simulation.
- Main AI/freeform behavior must remain available.

## References and concessions

- [Might Duy](https://naruto.fandom.com/wiki/Might_Duy) and
  [Eight Gates](https://naruto.fandom.com/wiki/Eight_Gates): the proposed rescue
  prevents opening the Eighth Gate; it is not ordinary healing afterward.
- [Arlong Park](https://onepiece.fandom.com/wiki/Arlong_Park): occupation and
  liberation context. The civilian protection branch is campaign-original.
- [Rukia's execution](https://bleach.fandom.com/wiki/Rukia%27s_Execution): the
  retreat branch does not automatically defeat Aizen or end his conspiracy.
- Canon references establish story context. Precise travel routes, encounter
  windows, support thresholds and tactical statistics are authored game rules.
