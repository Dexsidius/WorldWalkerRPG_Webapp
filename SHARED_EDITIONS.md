# One Worldwalker source, two editions

Develop future updates on `richardmadden1030-dot/worldwalker-rpg` master. Main and offline are built from the same commit; do not update the old Preview 6 copy as a separate game.

- Main is the default. Its AI, freeform actions, accounts and multiplayer remain available.
- `python launcher.py --offline` or `WORLDWALKER_MODE=offline` selects offline before settings or saves are loaded.
- `offline_launcher.py` is the packaged offline entry point. It calls the same launcher and imports the same game, map, combat, progression and simulation code.
- Default saves remain `WorldwalkerRPG` for main and `WorldwalkerRPGOfflinePrototype` for offline. An explicit `WORLDWALKER_DATA_DIR` overrides this for tests/hosting. Do not point both editions at the same live data directory.
- Offline UI is injected by the server only in offline mode. Do not fork the shared HTML, atlas, Chronicle, tactical UI, assets or engine. Keep offline-specific choices in the adapter modules.

## Every update

1. Pull current master before editing; preserve unrelated work.
2. Implement shared rules and presentation once. A new AI-dependent feature needs a listed local alternative or an explicit limitation.
3. Update `assets/data/edition_support.json` for every new POST API. The route coverage test fails on an unreviewed addition or stale entry. This flags omissions; it does not prove narrative parity. For changes within an existing endpoint, review offline behavior and add the relevant regression.
4. Run the full main suite and the offline suite. Never globally disable AI/freeform routes to implement offline mode.
5. Commit the change and build both packages with `python tools/build_editions.py --output <directory>`. The script rejects tracked uncommitted changes, verifies all bundled frontend/artwork bytes, runs each executable's self-test in fresh temporary storage, and records matching source commits plus hashes.

The Windows workflow builds and publishes a paired preview on master pushes. Both packages must succeed before either is published. Its release manifest identifies the exact common source commit. Stable releases are not automatically promoted. Workflow failures are visible in GitHub Actions and must be fixed before calling the update available for both editions.

## Tests

Set `PYTHONPATH` to `backend`, `tests`, and `tools` (use the platform path separator).

Main: `python -m pytest tests tools/check_workspace_tabs.py tools/check_reliability_browser.py tools/check_adventures_browser.py -q`

Offline: set `WORLDWALKER_MODE=offline`, then run `python -m pytest tests/test_offline_current.py tests/test_shared_editions.py tests/test_living_adventures.py tools/check_offline_browser.py -q`.

Main-only features are deliberately absent offline where they require arbitrary text, account/network services, or AI generation. The support manifest documents those gaps. Sharing source automatically carries shared fixes; it cannot automatically author a local equivalent of a new AI feature.
