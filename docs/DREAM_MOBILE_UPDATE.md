# Dream scenery and device-local graphics

Build: `3.64.0-dream-mobile-1` (shared main/offline source).

## Player-facing changes

- Approved Naruto and One Piece terrain/architecture artwork now renders inside the real campaign map, with world-specific panel styling. Existing controls, markers, route overlays, authority data, actions and save information remain available.
- Graphics selectors in the map toolbar and tactical battle controls offer Auto / High / Low. Auto defaults narrow phone layouts to Low. Preferences are local to each browser, so changing a phone does not change a PC or another player's device.
- Low removes 3D scenery, decorative activity thumbnails and heavy tactical attack sheets. It retains the map, targeting cells, brief impact feedback, portraits and combat outcomes.
- Both editions use the same implementation; no AI requests or additional gameplay endpoints were added.

## Performance measures

- Static architecture is batched by material; forests use instancing. Terrain sampling and ocean geometry are reduced from the standalone studies.
- Map drawing is capped to 2048px desktop / 1280px phone High, throttled and paused offscreen. Hidden pages stop ambient rendering. Disposing a scene frees meshes, textures and its WebGL context.
- Tactical canvas long edge is capped to 768px Low, 1024px phone High and 1800px desktop. Logical tile coordinates remain unchanged.
- Unchanged combat polls do not rebuild portraits or terrain. Background polling pauses in hidden tabs, avoids overlapping requests and checks every five seconds. Mutations discard stale responses and explicitly fetch fresh state.
- Low bypasses Unity sprite-sheet loading and clears cached sheets when selected; high-quality sheets use corrected root-relative asset URLs.
- The 26 Unity-authored sprite sheets previously present only in the combat prototype are now included in both packages. A real High-mode asset test prevents silent fallback from masking a missing library.

## Asset provenance and boundaries

The three raster atlases under `assets/dream-map` are generated artwork from the user's approved Naruto/One Piece Dream Loop previews. Scene geometry was adapted from those previews, not from third-party game assets. Naruto biome configuration and One Piece landmark positions come from the existing project geography. Political control still comes from current campaign atlas cells, not baked artwork. The bundled Three.js library retains its existing MIT license. `assets/unity-attack-library` contains the existing project-authored, approved Unity 6000.3.23f1 exports from `work/battle-comparison/assets/unity-attack-library`; only the manifest and animation sheets are shipped, not editor caches or redundant stills.

The standalone studies' fake campaign controls and static ownership were not integrated. These changes introduce no new canon claims or changes to territory ownership rules.

## Verification

Run the shared main/offline commands in `SHARED_EDITIONS.md`. Dedicated browser tests exercise both scenery worlds, context loss, ownership refresh, mobile quality switching, and Low-mode targeting for Naruto / One Piece / Bleach. General gameplay browser fixtures choose Low; dedicated scenery tests explicitly choose High so GPU rendering is still tested.

Responsive checks use a 390×844 browser viewport. They establish layout and functional behavior, not a physical-phone FPS or battery guarantee. Keep Low as the default phone path and test a representative iPhone and Android before promising specific High-mode performance.
