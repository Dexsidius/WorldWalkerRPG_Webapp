# Worldwalker RPG — Web/Desktop Rebuild

A from-scratch UI rebuild of Worldwalker RPG on top of the original game engine
logic. Same local-AI-driven, freeform text RPG across eight settings (One Piece,
Naruto, Hunter x Hunter, Solo Max-Level Newbie, Overgeared, Reincarnated as a Slime, Bleach, Custom World) —
now with a real animated HTML/CSS/JS interface instead of Tkinter, running in
a native desktop window via `pywebview`.

Current app/save version: **3.15.0** (schema 16).

Version 3.15 makes combat conditions fully mechanical: hard control consumes
actions, weakening changes real combat values, and both sides can carry timed
conditions. Character creation now reads the degree of the player's language,
so talented, prodigy, immense, godlike, and immeasurable starts produce sharply
different open-ended stats and matching generated powers without extra AI calls.

Version 3.12 separates literal System quests from ordinary story goals.
Overgeared and Solo Max-Level Newbie retain objective progress, completion
conditions, and quest branches. Every other setting now presents missions,
promises, investigations, and personal goals through a world-themed narrative
Agenda with current knowledge, pressures, developments, and possible leads—no
progress bars, mandatory route order, or automatic checklist completion.

Version 3.11 turns the lightweight Solo Max-Level Newbie and Overgeared
profiles into persistent setting simulations. Solo now tracks full floor
scenarios, hidden-condition discovery, copied-ability requirements,
foreknowledge, rivals, artifacts, party roles, achievement chains and clear
reports. Overgeared now separates class development from individual production
disciplines and tracks class quests, NPC affinity, guilds, territory, orders,
economy and public rankings. Crafting in every world remains part of the
Chronicle; routine ore and components no longer clutter the Bag, while named,
reusable and story-important finished items receive readable item cards.

Version 3.10 brings the non-Bleach worlds up to the same mechanical standard
as the Bleach rebuild without adding map nodes or timeline dates. One Piece,
Hunter × Hunter, Naruto, Solo Max-Level Newbie, Overgeared, and Reincarnated
as a Slime now have dedicated world-system records and Journal cards. Existing
canon events are spoiler-safe and causally ordered, canon-character starts use
complete deterministic stat sheets and live opening situations, every ordinary
origin receives a saved role, loadout, progression state, and opening quest,
and non-level settings no longer receive a misleading Level label in Party.
Additional selectable starts use only locations that were already on each map.

Version 3.8.1 adds a fully mechanical Pain canon start immediately after
Yahiko's death, while the Deva Path and transformed Akatsuki are first taking
shape. It also expands One Piece creation from three starting locations to a
broad selection across the Blues, Grand Line, World Government territory and
the New World; every new choice has an opening premise and a matching map node.

Version 3.8.0 makes campaign-start labels mechanically authoritative. Canon
characters and high-status original origins now begin with their promised
rank, affiliation, signature abilities, equipment, knowledge, quests, and
conditions before the opening narration runs. It also adds start-era
consistency warnings and automatic correction for impossible default-era
origins, expands maps and timelines, limits direct messaging of inaccessible
factions, and adds focused new archetypes and eras across the non-Bleach worlds.

Version 3.7.2 unifies current-stat interpretation across the Power Summary,
Advisor, and GM. Extreme specialties remain powerful without being mistaken
for balanced reality-bending capability, and the Power Summary now opens above
the Journal. Focused training develops related and secondary stats, plain
training builds the full sheet, and world-valid accelerated methods can produce
exceptional growth. Configured AI models now author original, canon-balanced
starting classes, bloodlines, abilities, and matching starting techniques;
offline creation retains safe world-valid fallbacks.

Version 3.7.1 makes Story, Adventurer, and Veteran explicitly player-favoring:
possible actions resolve decisively, diplomacy is challenged through NPC and
faction responses instead of abstract failure, and specific world-valid plans
bypass arbitrary gates. Sustained training is faster and broader; six months
of rigorous Naruto combat training can now establish jōnin-level capability
without falsely granting an official village rank. Nightmare remains strict.

Version 3.7.0 reduces AI cost and improves simulation consistency. It sends
task-specific context to each model, uses the secondary model for Advisor and
combat narration when configured, reports cached-token savings, keeps only
useful autosave history, and disables automatic portrait generation by default.
It also improves standing plans, roll/action labeling, training and quest
reports, combat entry, scene-matched artwork, suggestions, mobile Advisor
readability, and moment/time-skip controls.

Version 3.6.3 gives dangerous confrontations one persistent warning instead
of reopening a warning for every difficult choice in the same scene. Normal
moment-to-moment checks continue after the warning is accepted; only a new
credible chance of death warns again. Committed attacks from either side now
enter structured combat immediately through expanded deterministic detection.

Version 3.6.2 moves major/canon events back into the normal Chronicle and
Action Chat: their popup is now a close-only notice, unavoidable violence
opens structured combat immediately, and event importance alone no longer
forces a roll. Challenge minigames can either stop after their result or carry
that result through the remaining requested skip. Phone chats and the Advisor
now reserve most of the screen for readable conversation history.

Version 3.6 adds a local campaign director, persistent NPC motives, optional
relationship scenes, branching quest routes, productive failures, readable
cause-and-effect and training reports, editable/reorderable time-skip plans,
major-event model routing, request/session cost limits, and opt-in same-scenario
model comparisons. These systems reuse state the game already tracks and do
not add routine AI calls.

Version 3.3 reduces simulation bloat: normal Advances use a deterministic
planning pass plus one combined narrator request, while Economy, Balanced,
and Deep detail modes control how much of the wider world stays in focus.
NPC intentions, lore retrieval, event importance, and art reuse are cached or
advanced locally whenever a model call is not necessary.

## Running it

```
pip install -r requirements.txt
python launcher.py
```

or double-click `run_game.bat` on Windows. The desktop launcher chooses an
available local port and opens it in a native window automatically — no
browser tab, no manual server step. The launcher deliberately avoids a fixed
port: an older process can no longer make a new window attach to stale art,
JavaScript, or campaign state. Desktop responses are also marked no-cache.

With no campaign active, startup opens a dedicated welcome screen with two
working choices: **Start New Campaign** or **Load Existing Save**.

## Playing from a phone

Extract the Phone Host package on a Windows PC and double-click
`Start Phone Mode.bat`. Keep the host window open, connect the phone to the
same trusted Wi-Fi, and open the address displayed across the top of the host
window. If Windows Firewall asks, allow access on **Private networks** only.

The phone interface puts the scene and Chronicle first, then Action Chat and
time controls, with character and journal panels below. It uses the same
campaign, autosave, music, AI configuration, and server-side API key as the
host PC. Do not use Phone Mode on public or untrusted Wi-Fi; anyone who can
reach the displayed local address can control that running game. The included
web-app manifest supports home-screen installation when the page is served in
a browser-approved secure context, but ordinary local HTTP play works directly
in the phone browser while the PC host is running.

New Campaign now uses a preview/confirmation step and can start as an original
character or at a curated major-character timeline moment (including Yahiko
founding the original Akatsuki, Naruto's birth or graduation, Gon leaving Whale
Island, and comparable starts in the other supported worlds). The player has
full control of canon characters; the timeline steers through living pressures
and relationships but never forces the source character's decisions.

For local AI (recommended, free, no per-turn cost): open LM Studio, load a
chat/instruct model, Developer → Start Server, then in-game go to
**OPTIONS → AI & Portrait Setup → Detect Models**, pick a model, Save.

Settings and saves live in `%APPDATA%\WorldwalkerRPG\` — the same folder the
original Tkinter build used, so an existing local-AI configuration carries
over automatically.

## Architecture

- `backend/worlds.py` — world data, difficulties, base character state
  (ported 1:1 from the original `worldwalker.py`).
- `backend/ai_client.py` — the local/cloud AI client (Responses API with
  Chat Completions fallback), also ported 1:1.
- `backend/game.py` — `GameSession`: the actual game engine (assess → roll →
  resolve turn loop, time skips, chat/contacts, background world ticks,
  memory management, save/load). All Tkinter UI code has been removed; every
  method returns plain dicts.
- `backend/app.py` — Flask routes exposing `GameSession` as a small JSON API,
  plus static file serving for the frontend and game assets.
- `frontend/` — the actual UI: `index.html` + `css/style.css` +
  `js/app.js`. Pure vanilla JS, no build step.
- `launcher.py` — runs the Flask app on a background thread and opens it in
  a `pywebview` window.

## About the artwork

The generated art library contains the original landmark/environment set plus
five new optimized location-specific banners for merchant shops, taverns,
academy classrooms, ship decks, and arena floors. This prevents broad fallback
art—especially battlefields—from appearing inside ordinary local places.

Version 2.2 replaced the old mislabeled placeholder set with 38 original,
generated environment paintings in `assets/generated_scenes/`. Twenty-four
are recognizable location anchors across the supported worlds—including
Hidden Leaf Village, Heaven's Arena, Water 7, Skypiea, Tempest, and more;
the rest cover live scene types such as towns, caves,
dungeons, duels, monster battlefields, castles, forests, harbors, and night
skies. `backend/util.py` selects art from the player's current physical
location first, then a landmark, then the closest environment category.
Concrete places such as merchant stalls and markets outrank old battlefield
references in the story log. A canvas fallback prevents blank loads.

## Version 2.5 progression rules

- Every uncertain action uses a contextual d100 check. The application samples a difficulty from the GM's lore-grounded range, rolls once, adds world-relative stats, skills and titles, and succeeds only when the modified roll is strictly greater than the difficulty.
- Stats are open-ended and meaningful only inside their current world/era. D&D modifiers and the former 20/99 caps are gone.
- Health and the setting's energy pool are derived from starting stats and grow with them.
- Long training counts accumulated daily sessions. A month of uninterrupted training is approximately 30 days of progress, with a persistent chance of a lore-explained breakthrough.
- XP and levels appear only in settings that canonically expose them as an in-fiction system (Overgeared and Solo Max-Level Newbie).
- Evolutions, transformations, climactic confrontations and other major turning points pause for an animated manual Fate Check.
- Advance stops at major canon events and asks whether the player wants to intervene moment-to-moment.
- The Advisor provides deeper briefings and canon countdowns; optional Fourth-Wall mode may explain simulation mechanics and legitimate exploits without changing state.

Version 2.5.4 makes XP authoritative in literal-System worlds: every meaningful
action receives a contextual award, sustained training scales with its actual
elapsed time, and level-ups spend carried XP and raise world-relative base
stats. The Progress journal explains each award and level gain. Non-System
worlds continue to grow directly through training, techniques, knowledge,
titles, ranks, and proficiency rather than artificial XP.

D100 results now use one compact action-linked line: raw roll out of 100 plus
the combined bonus, final total, required number, and outcome. Individual
calculation boxes have been removed from the Chronicle.

## Version 2.6 simulation and campaign tools

Before a difficult uncertain action resolves, the game shows the contextual
d100 target, applicable bonuses, and risk without moving time. The player may
roll normally, use the Timing Clash reaction challenge, use the Tactical
Approach decision challenge, or cancel and revise the queued actions.

**Skip to next major event** advances through routine developments while still
recording world updates, then ends naturally at the first major personal or
canon turning point. It does not create a separate intervention prompt.

The Journal now includes chapter summaries, persistent NPC and faction clocks,
relationship snapshots, quest objective/branch states, lore-source imports,
progression tuning, campaign-health diagnostics, and an interactive map that
can estimate and queue travel routes. The main cloud GM defaults to GPT-5.6
Luna while the cheaper background simulation remains on GPT-4o mini; existing
model selections are never silently replaced.

## Guided journeys and world music

The GM ends every resolved scene or time skip with three optional, contextual
leads: the strongest current story lead, a useful growth/preparation option,
and an alternate exploration, social, or travel hook. These are guidance rather
than restrictions. Clicking one copies it into the Action Chat for editing; it
does not resolve anything until the player presses **ADVANCE**.

The story log now uses the full center column. Active Quest and World Feed are
compact left-side buttons that open their complete journal pages, while the
persistent Action Chat occupies the right rail. Queued actions remain visible
there until the player confirms the next turn.

An Advance with no new action continues the previous standing orders when
possible while still moving NPCs, factions, markets, travel, rumors, and canon
pressures. Goal-worded orders can end a skip early: if an ability is mastered
on day 13 of a requested month, the simulation stops on day 13. If the deadline
arrives first, the story explains the in-world obstacle and offers a relevant
next step. Major-event stops use a non-blurred context panel and end with a
specific character-named intervention question.

The **moment** unit is event-driven rather than a literal one-minute step. It
resolves only the next immediate meaningful story beat, allows that beat to use
the believable minutes or hours it needs, and never advances more than 24 hours.
Any later queued actions remain deferred for another Advance.

Moment is always exactly one beat and therefore has no quantity field. Numeric
skip amounts are shown only for days, weeks, and months. Routine Advances now
proceed directly after their hidden mechanical assessment; interrupting panels
are reserved for lethal warnings, major events, and animated major d100 rolls.

The center Chronicle groups each response into a clearly labelled story beat.
Narration, player decisions, world updates, checks, and urgent consequences use
separate visual levels, while routine system information stays compact. A
Latest button returns directly to the newest beat. Its complete flex/overflow
chain is constrained so the feed always scrolls through its final entry.

Major-event intervention is an inline Chronicle decision instead of a modal.
**Yes — Stop Here** leaves the simulation at the event for player input;
**No — Keep Simulating** resumes the unspent portion of the original skip as if
the pause had not become a player turn. The event context remains visible while
the choice is made.

Portable music folders sit beside the source launcher or packaged EXE under
`music/`, with one folder per supported world plus `Shared`. Drop MP3 or MP4
files into the matching world folder, then use the music rescan/folder controls
under World Systems. MP3 is recommended for the broadest playback support.

The left Skills & Titles summary displays names only. Clicking it opens the
full journal view, where each skill is presented as a short effect summary plus
rank/check bonus, use, origin, cost or limitation, and growth path when known.
Raw object notation and internal calculation fields are not shown.

An explicit request to start or accept a quest always creates a structured
quest and a Chronicle briefing. The Quests journal now surfaces its giver or
cause, objective, known locations and risks, first actionable step, completion
conditions, deadline, and rewards whenever those facts are known.

The shipped build uses quality-86 WebP versions (about 88% smaller than the
master PNGs). Lightweight canvas overlays animate only appropriate details—torch flicker,
embers, stars, fireflies, leaves, cave drips, crowds, and water shimmer—so the
painted backgrounds stay sharp and the desktop build remains responsive. GIF
and WebP scene files are also supported automatically if added later.

The Journal's Map tab uses seven generated world atlases from
`assets/generated_maps/`, with every important landmark from `WORLD_DATA`
overlaid, route guides, discovery status, and a pulsing current-location pin.

## Lore, canon timeline, and prerequisite tracking

`backend/lore.py` is an offline-first retrieval layer. Every GM request receives
only the setting notes relevant to the current action, plus live state/codex
context. Optional JSON lore packs can be added under `assets/lore/`. The game
does not claim to live-browse wikis from the packaged EXE.

Every source world begins three to seven days before its protagonist's opening
story event. The Journal → Timeline tab shows relative Canon Day dates and
important scheduled events. Advance is the only control that moves this clock;
events fire when crossed, while prior player actions can create recorded canon
divergences instead of being railroaded.

When the player pursues a notable canon feat, class, item, transformation, or
position, the GM creates a Journal → Prerequisites track showing requirements
met, missing requirements, next steps, and why something is currently blocked.

Autosave writes atomically to one rolling recovery file per campaign, replacing
that campaign's prior autosave instead of filling the Load screen with numbered
copies. Manual saves remain separate, and both appear in the Load screen.

## Background completion and starting potential

The campaign preview now turns vague background claims into usable world data.
For example, “I have some kind of fire ability” produces a randomly selected,
setting-valid named ability with an origin, practical effect, limitation, and
growth path. It appears in the starting loadout and Skills journal, and the GM
must preserve it as an authoritative fact rather than asking the player to
define it again.

Missing upbringing, training, relationship, formative-event, motivation, and
complication details are filled in without replacing facts the player supplied.
The completed background creates a visible Growth Profile. Its aptitude rate
affects sustained training, while time, repetition, recovery, current mastery,
teachers, resources, and rolls continue to determine the actual result.

Character portraits are AI-generated square illustrations. The prompt uses the
player's description, age, origin, archetype, visible traits, equipment, form,
and position; missing details are filled in coherently. Each world has its own
broad visual language without requesting an exact living-artist imitation or a
canon character likeness. Portraits default to low-quality 1024×1024 generation
for speed, are cached under `%APPDATA%\WorldwalkerRPG\portraits`, and regenerate
only when a visually relevant trait changes. Later updates edit the previous
portrait to preserve identity. A manual Regenerate button is also available.

Cloud portraits use the OpenAI image model configured under **OPTIONS → AI &
Portrait Setup** (default `gpt-image-2`) and have separate image-API usage costs.
Local portrait generation is optional and requires an OpenAI-compatible image
endpoint/model. When neither is configured, the game immediately shows one of
seven lightweight bundled world-style portraits instead of a broken image.

Time is explicitly player-controlled. Typing an action adds it to a persistent
ordered queue and produces no GM or world response. Chat messages are queued in
the same way. Choose a duration and press **ADVANCE** to review time estimates,
checks, rushing penalties, and likely deferred actions; only confirmation rolls,
moves the clock, or lets the world respond. The result is emitted as separate,
detailed chronological updates for each major action, NPC/faction reaction,
consequence, interruption, and due canon event.

Campaign Library shows each save's app version, supports import/export, rolling
autosave recovery, and guarded permanent deletion. Developer Diagnostics exposes
the last action assessment, scene-selection reason, state-patch validation,
continuity warnings, lore context, world-pack status, and an exportable report.

The GM treats canon feats as evidence of what the setting permits, not as
abilities reserved for canon protagonists. A player who meets the same
world-specific prerequisites can attempt, learn, reproduce, obtain, or build
toward the same result. If an action is currently impossible, the GM must name
the exact missing prerequisite or lore conflict and explain what can change.
Lore comes from the selected model's available source knowledge plus the live
campaign state/codex; the desktop build does not silently live-browse websites.

To override the shipped art, drop a `background.png` into
`assets/user/<World>/` (e.g. `assets/user/One_Piece/background.png`) — the
game already checks there first and will use it for every scene in that
world.

## Per-world UI skins

Each world reskins the whole interface, not just accent colors — different
display fonts, panel corner treatments, and motifs, defined in
`frontend/css/style.css` under `body[data-world="..."]`:

- **One Piece** — nautical poster look, `Pirata One` display font.
- **Naruto** — ink/scroll panels with clipped corners, `Yuji Syuku` font, a
  small red seal mark on panel headers.
- **Hunter x Hunter** — license-card angled panel corners, clean modern
  green/gold.
- **Solo Max-Level Newbie** — sci-fi system UI: `Orbitron`/mono fonts, neon
  cyan glow, animated scanline overlay, octagon-cut panels.
- **Overgeared** — forge/MMO fantasy: `Cinzel Decorative`, riveted bronze
  corner studs.
- **Custom World** — the ornate default theme.
