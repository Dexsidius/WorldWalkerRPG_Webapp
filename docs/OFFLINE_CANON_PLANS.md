# Offline canon appointments

## Research and design

Research preceded implementation. These sources support design patterns, not
claims that Worldwalker now reproduces another game's complete AI:

- TaleWorlds, [Campaign AI, 20 December 2019](https://www.taleworlds.com/en/Games/Bannerlord/Blog/133):
  campaign actors choose priorities in light of abilities, limits and needs.
  Here a calendar appointment is a default plan with availability checks, not
  permission to ignore a changed campaign.
- Paradox, [Royal Modding, diary 87](https://www.paradoxinteractive.com/games/crusader-kings-iii/news/dev-diary-87-royal-modding):
  explicit role eligibility, trigger evaluation, scope diagnostics and event
  cooldowns. Here casts are authored, settlement is once-only, and cancellation
  reasons are recorded privately for inspection. A character in an unresolved
  battle is not simultaneously assigned to a scene in another location.
- inkle, [Writing with ink](https://github.com/inkle/ink/blob/master/Documentation/WritingWithInk.md)
  and [web tutorial](https://www.inklestudios.com/ink/web-tutorial/): authored choices,
  variables and branches can rejoin shared story passages. Here observation,
  contribution, refusal, rescue and aftermath are saved states; preparation is
  not confused with winning the encounter.

## Coverage

| World | Authored calendar entries | Existing rescue packs | New runnable appointments | Historical references |
| --- | ---: | ---: | ---: | ---: |
| Naruto | 52 | 1 | 46 | 5 |
| One Piece | 40 | 1 | 31 | 8 |
| Bleach | 27 | 1 | 23 | 3 |

Every current timeline title is explicitly covered by `canon_event_plans.py`.
Tests fail if a timeline entry is added without an authored plan. Existing
historical-only flags, IDs, offsets and saved epochs are unchanged. Historical
reference entries are **not newly playable historical starts**. Old saves
enroll future appointments; they do not replay unrecorded past events.

The original Duy, Arlong and Sokyoku intervention packs are retained. Seven
additional rescue branches use real tactical protection objectives: Obito at
Kannabi Bridge, Yahiko, Asuma, Jiraiya, Ace, Rukia's detention and Orihime's
departure. Their enemy benchmarks are game tuning, not canonical numeric stats.

Other entries have authored local premises and bounded thirty-minute tasks,
ten-minute observation and a no-penalty refusal. They are not all equally deep
campaign arcs. Helping with supplies does not defeat a villain, award a power,
alter a rank, create a relationship, or annex territory. The contribution is
recorded in that appointment's history; rescue preparation shortens protection
from four rounds to three. Non-rescue contributions currently do not have a
broader economy or relationship reward.

## Execution and safety

- `offline_schedule.advance` resolves departure, encounter and deadline
  boundaries in game-time order. No real-time agent loop or model call.
- `offline_canon_plans` owns covered offline events, including the backstop
  exclusion needed to prevent old-save replay. Main AI/freeform behavior is
  unchanged. Existing signed activity APIs handle preview, confirmation, time,
  transactions and receipts; there is no new POST API.
- Unknown canon participants are assumed available until campaign evidence
  contradicts that. Known death, captivity or sealing blocks the original plan.
  Exact saved event changes override the default. Only authored causal links
  propagate cancellation; chronological neighbors are not prerequisites.
- An unresolved player-controlled canon role waits for the player instead of
  following its script automatically. Refusal records divergence. There is no
  button that automatically plays an entire hero's canon arc for the player.
- Actual appointment positions and origins are stored privately. Known NPC
  location information updates only when the player witnesses that encounter.
  Distant markers require eligible allies/group members and confirmed tracking;
  interpolation uses legal graph edges, never a straight ocean/realm shortcut.
  Where no legal route exists, there is no animated route marker. Arrival at an
  authored site is still a calendar convention, not a full logistical simulation.
- Secret encounters require explicit local access (or the player being in the
  cast). A city-wide location match alone does not grant access. The planner
  does not invent permissions or disclose future secret outcomes through public
  state. Private schedules remain under the already-filtered `offline_world`.
- Cancellation reasons are internal. Canon remains a player-reference timeline,
  not automatic NPC knowledge. Unwritten alternate arcs are suspended rather
  than replaced with fabricated victories.

## Best next improvements

1. Author alternate arcs after successful rescues (Ace surviving Marineford,
   Yahiko retaining leadership, etc.), rather than just suspending incompatible
   continuations. These need meaningful choices and distinct consequences.
2. Add contact-mediated invitations/access and scene-specific discovery clues
   for private appointments. Currently explicit encounter access or a canon
   participant role is needed; knowledge must not be granted by proximity alone.
3. Replace conventional one-day departure windows with authored itineraries,
   travel durations and explicit realm crossings for major parties. Current map
   motion is bounded presentation of the schedule, not Bannerlord-scale logistics.
4. Extend civilian contributions into carefully bounded reputation, material
   and political consequences. Do not grant rewards simply for clicking through.

## Verification

The timeline summary corrections were checked against the official
[Obito retrospective](https://naruto-official.com/en/news/01_1706),
[Kaguya revival episode](https://naruto-official.com/anime/naruto2/list/01_903),
[One Piece episode 483](https://one-piece.com/anime/483/index.html) and
[episode 485](https://one-piece.com/anime/485/index.html).
The Summit cast uses Danzo, checked against the
[official Five Kage arc retrospective](https://naruto-official.com/en/news/01_1321).
Only the summaries/cast changed, not their calendar IDs or dates.
Same-day appointments are spaced by three game hours in timeline order.
That intraday spacing is a game convention, not an asserted canonical time.

`tests/test_offline_canon_plans.py` exercises every runnable new entry, exact
time accounting, repeat protection, privacy, player agency, dead/captured cast,
explicit dependencies, real rescue transactions, old saves, map tracking and
split-time/save-reload equivalence. Existing Duy/Arlong/Sokyoku tests remain.
Full main and offline suites and paired executable self-tests are release gates.
