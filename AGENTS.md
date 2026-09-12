# Worldwalker contributor instructions

## Shared main and offline editions

Main and offline now share this repository and release commit. Read
`SHARED_EDITIONS.md` before implementation/release work. Preserve main's normal
AI/freeform behavior; isolate offline choices and guards behind runtime mode.
Never maintain a separate offline copy of the atlas, combat or shared engine.
Review offline behavior for every feature; new POST APIs require an entry in
`assets/data/edition_support.json`. Run main and offline checks and build both
packages with `tools/build_editions.py`. Keep save directories separate. Do not
publish one member of a release pair if the other fails validation.

## Publishing

Approved implementation updates go to BOTH configured GitHub destinations:
`richardmadden1030-dot/worldwalker-rpg` -> `master` and
`Dexsidius/WorldWalkerRPG_Webapp` -> `web_prod`. Richard explicitly restored
dual-repository publishing on September 12, 2026, superseding the September 6
restriction. This is not permission to overwrite divergent work, update every
branch, or directly administer the friend's hosted prod/dev servers.
Read the latest source tip before changes, preserve unrelated work, use non-force
writes, run relevant checks, and verify the actual resulting commit.
Never include credentials, API keys, player saves, or personal data in commits.

## Reliability and presentation

Preserve saves and freeform actions. Report gameplay changes from committed
state, not from prose guesses. A lost HTTP response does not prove a failed
turn: check its request receipt before replaying it. Keep IDs stable on retry.
Do not expose concealed skills, classes, NPC secrets, or request bookkeeping in
player-visible receipts or prompts. Suggested freeform actions remain editable proposals. Explicit location activity
buttons are the approved exception: show authoritative duration/cost, ask for
confirmation, then resolve exactly that time unless a declared interruption
pauses it. Never auto-run an activity on a preview or canceled confirmation. Keep the Chronicle and Map mounted when changing tabs.

## Windows distribution

When an executable is requested, build and verify a Windows package containing
that update, or provide a verified existing download with its limitations.
Do not present a source ZIP or older executable as the new build. Keep the
portable folder, including `_internal`, together. Publish previews separately
from stable releases unless promotion is explicitly requested.

## World dates and player reference

Use the fixed world-calendar profiles for displayed dates. Preserve canon event
IDs/offsets and explicit saved epochs. Never call a projected or conventional
date confirmed canon. The visible Canon timeline is a player reference and must
not alter NPC knowledge merely because it was viewed. Timed location actions
and objective bookkeeping are engine-owned, never narrator-authored patches.
